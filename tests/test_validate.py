"""Tests for validate.py: every check passes on fixture data and fails when that data is broken."""

import copy
import json
import statistics
from pathlib import Path

import pandas as pd
import pytest

from sleeper_dash import validate as v
from sleeper_dash.transform import (build_player_weeks, build_schedule, build_team_weeks, build_teams, build_transactions,
                                    build_winners_bracket)

FIXTURES = Path(__file__).parent / "fixtures"
ROSTER_POSITIONS = ["QB", "RB", "RB", "WR", "WR", "FLEX", "REC_FLEX", "SUPER_FLEX", "K", "DEF"] + ["BN"] * 6


def make_league(median=True):
    return {
        "season": "2026",
        "roster_positions": ROSTER_POSITIONS,
        "settings": {"num_teams": 12, "start_week": 1, "playoff_week_start": 15, "league_average_match": int(median),
                     "playoff_teams": 6, "playoff_round_type": 0, "playoff_seed_type": 0},
    }


@pytest.fixture
def week_1():
    return json.loads((FIXTURES / "matchups_week_01.json").read_text(encoding="utf-8"))


def week_1_settings(week_1, median=True):
    """Sleeper-style season settings after week 1, computed straight from the raw matchups."""
    points = {m["roster_id"]: m["points"] for m in week_1}
    opponent = {}
    for m in week_1:
        for other in week_1:
            if other["matchup_id"] == m["matchup_id"] and other["roster_id"] != m["roster_id"]:
                opponent[m["roster_id"]] = other["roster_id"]
    week_median = statistics.median(points.values())
    settings = {}
    for rid, pts in points.items():
        opp = points[opponent[rid]]
        wins = (pts > opp) + (median and pts > week_median)
        losses = (pts < opp) + (median and pts < week_median)
        settings[rid] = {
            "wins": int(wins), "losses": int(losses), "ties": int(pts == opp),
            "fpts": int(pts), "fpts_decimal": round((pts - int(pts)) * 100),
            "fpts_against": int(opp), "fpts_against_decimal": round((opp - int(opp)) * 100),
        }
    return settings


def sleeper_bracket(rosters):
    """Sleeper's provisional winners bracket, seeded straight from the roster standings (wins, then points for)."""
    def key(r):
        s = r["settings"]
        return s["wins"] + s["ties"] / 2, s["fpts"] + s["fpts_decimal"] / 100
    s = [r["roster_id"] for r in sorted(rosters, key=key, reverse=True)]
    return [
        {"r": 1, "m": 1, "t1": s[3], "t2": s[4]}, {"r": 1, "m": 2, "t1": s[2], "t2": s[5]},
        {"r": 2, "m": 3, "t1": s[0], "t2": None, "t2_from": {"w": 1}},
        {"r": 2, "m": 4, "t1": s[1], "t2": None, "t2_from": {"w": 2}},
        {"r": 3, "m": 6, "p": 1, "t1": None, "t2": None, "t1_from": {"w": 3}, "t2_from": {"w": 4}},
    ]


@pytest.fixture
def rosters(week_1):
    rosters = json.loads((FIXTURES / "rosters.json").read_text(encoding="utf-8"))
    settings = week_1_settings(week_1)
    for r in rosters:
        r["settings"].update(settings[r["roster_id"]])
    return rosters


@pytest.fixture
def tables(week_1, rosters):
    league = make_league()
    users = [{"user_id": r["owner_id"], "display_name": f"user{r['roster_id']}"} for r in rosters]
    return {
        "teams": build_teams(league, rosters, users),
        "team_weeks": build_team_weeks(league, {1: week_1}),
        "player_weeks": build_player_weeks(league, {1: week_1}, players={}),
        "transactions": build_transactions(league, {}, {}, "2026-09-09"),
        # Weeks 2-14 not played yet: Sleeper publishes their pairings ahead of time (reused from week 1 here).
        "schedule": build_schedule(league, {1: week_1}, {week: week_1 for week in range(2, 15)}),
        "winners_bracket": build_winners_bracket(league, sleeper_bracket(rosters)),
    }


def failed(results):
    return [r.name for r in results if not r.passed]


def test_settings_helper_matches_a_known_result(week_1):
    # Roster 1 scored 195.12 vs 108.82 in week 1, above the 126.49 median: two wins.
    s = week_1_settings(week_1)[1]
    assert (s["wins"], s["losses"], s["fpts"], s["fpts_decimal"]) == (2, 0, 195, 12)


def test_all_checks_pass_on_fixture_data(tables, rosters):
    results = v.run_checks(tables, make_league(), rosters)
    assert len(results) == 8  # the 7 data checks plus seeding vs Sleeper's bracket
    assert failed(results) == []


def test_missing_team_row_fails(tables, rosters):
    tables["team_weeks"] = tables["team_weeks"].iloc[1:]
    assert "Every week has one row per team" in failed(v.run_checks(tables, make_league(), rosters))


def test_missing_week_fails(tables):
    week_3 = tables["team_weeks"].assign(week=3)
    result = v.check_team_rows_per_week(pd.concat([tables["team_weeks"], week_3]), make_league())
    assert not result.passed and "weeks missing entirely: [2]" in result.detail


def test_unpaired_matchup_fails(tables):
    tw = tables["team_weeks"].copy()
    tw.loc[0, "matchup_id"] = 99
    result = v.check_matchup_pairs(tw)
    assert not result.passed and "matchup 99: 1 teams" in result.detail


def test_starter_points_respect_the_tolerance(tables):
    pw = tables["player_weeks"].copy()
    pw.loc[0, "points"] += 0.004
    assert v.check_starter_points(pw, tables["team_weeks"]).passed
    pw.loc[0, "points"] += 0.5
    result = v.check_starter_points(pw, tables["team_weeks"])
    assert not result.passed and "roster 1" in result.detail


def test_record_mismatch_names_the_team(tables, rosters):
    rosters[2]["settings"]["wins"] += 1
    result = v.check_records(tables["team_weeks"], rosters, make_league())
    assert not result.passed and result.detail.startswith("roster 3:")


def test_median_games_are_counted_only_when_the_league_plays_them(week_1, tables, rosters):
    h2h_only = copy.deepcopy(rosters)
    for r in h2h_only:
        r["settings"].update(week_1_settings(week_1, median=False)[r["roster_id"]])
    tw_no_median = build_team_weeks(make_league(median=False), {1: week_1})
    assert v.check_records(tw_no_median, h2h_only, make_league(median=False)).passed
    assert not v.check_records(tables["team_weeks"], h2h_only, make_league(median=True)).passed


def test_playoff_weeks_are_left_out_of_reconciliation(tables, rosters):
    playoff = tables["team_weeks"].assign(week=15, is_playoff=True)
    combined = pd.concat([tables["team_weeks"], playoff])
    assert v.check_records(combined, rosters, make_league()).passed
    assert v.check_points_for_against(combined, rosters).passed


def test_points_mismatch_fails(tables, rosters):
    rosters[0]["settings"]["fpts_decimal"] += 5
    rosters[1]["settings"]["fpts_against"] += 1
    result = v.check_points_for_against(tables["team_weeks"], rosters)
    assert not result.passed
    assert "roster 1: points for" in result.detail and "roster 2: points against" in result.detail


@pytest.mark.parametrize("name", v.BASE_TABLES)  # lineup tables: tests/test_lineup.py
def test_duplicate_keys_fail(tables, name):
    table = tables[name]
    if table.empty:  # no transactions in the fixture; make one row to duplicate
        table = pd.DataFrame([{"transaction_id": "1", "player_id": "101", "action": "add"}])
    tables[name] = pd.concat([table, table.iloc[[0]]])
    result = v.check_unique_keys(tables)
    assert not result.passed and result.detail.startswith(name)


def test_validate_raises_with_the_full_table(tables, rosters):
    rosters[0]["settings"]["wins"] += 1
    with pytest.raises(v.ValidationError) as error:
        v.validate(tables, make_league(), rosters)
    message = str(error.value)
    assert "Validation: 1 check(s) failed" in message and "FAIL" in message and "Records match Sleeper" in message


# --- seeding vs Sleeper's bracket (METRICS_SPEC.md section 8, sanity check 8) -------------------

def test_seeding_matches_sleepers_bracket(tables, rosters):
    result = v.check_seeding_matches_sleeper(tables["winners_bracket"], tables["team_weeks"], make_league())
    assert result.passed and "through week 1: byes and first-round pairings agree" in result.detail


def test_a_different_seeding_in_sleepers_bracket_fails(tables, rosters):
    bracket = sleeper_bracket(rosters)
    bracket[2]["t1"], bracket[3]["t1"] = bracket[3]["t1"], bracket[2]["t1"]  # seeds 1 and 2 swapped
    result = v.check_seeding_matches_sleeper(build_winners_bracket(make_league(), bracket), tables["team_weeks"], make_league())
    assert not result.passed and "but Sleeper's bracket has" in result.detail


def test_no_bracket_yet_is_not_a_failure(tables):
    empty = build_winners_bracket(make_league(), [])
    result = v.check_seeding_matches_sleeper(empty, tables["team_weeks"], make_league())
    assert result.passed and "no bracket yet" in result.detail


def test_an_unverified_playoff_format_fails_the_seeding_check(tables):
    league = make_league()
    league["settings"]["playoff_seed_type"] = 1
    result = v.check_seeding_matches_sleeper(tables["winners_bracket"], tables["team_weeks"], league)
    assert not result.passed and "playoff_seed_type is 1" in result.detail
