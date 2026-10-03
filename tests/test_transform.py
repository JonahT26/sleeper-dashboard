"""Tests for the teams table, built from the anonymised rosters fixture plus made-up users."""

import json
from pathlib import Path

import pandas as pd
import pytest

from sleeper_dash.transform import (
    PLAYER_WEEKS_COLUMNS,
    TEAM_WEEKS_COLUMNS,
    TEAMS_COLUMNS,
    TRANSACTIONS_COLUMNS,
    build_player_weeks,
    build_team_weeks,
    build_teams,
    build_transactions,
    save_table,
    season_start_date,
)

FIXTURES = Path(__file__).parent / "fixtures"
LEAGUE = {"season": "2026"}


@pytest.fixture
def rosters():
    return json.loads((FIXTURES / "rosters.json").read_text(encoding="utf-8"))


def make_users(rosters):
    """One user per roster owner, each with a custom team name."""
    return [
        {"user_id": r["owner_id"], "display_name": f"user{r['roster_id']}", "metadata": {"team_name": f"Team {r['roster_id']}"}}
        for r in rosters
    ]


def test_one_row_per_roster_with_spec_columns_and_types(rosters):
    teams = build_teams(LEAGUE, rosters, make_users(rosters))
    assert list(teams.columns) == TEAMS_COLUMNS
    assert len(teams) == 12
    assert teams["roster_id"].tolist() == list(range(1, 13))
    assert (teams["season"] == 2026).all()
    assert str(teams["owner_id"].dtype) == "string"
    assert teams["co_owners"].map(lambda v: v == []).all()  # null in raw becomes an empty list


def test_team_name_prefers_metadata_and_strips_spaces(rosters):
    users = make_users(rosters)
    users[0]["metadata"]["team_name"] = "  Padded Name "
    teams = build_teams(LEAGUE, rosters, users)
    row = teams.set_index("owner_id").loc[users[0]["user_id"]]
    assert row["team_name"] == "Padded Name"
    assert row["display_name"] == users[0]["display_name"]


@pytest.mark.parametrize("metadata", [{}, {"team_name": ""}, {"team_name": "   "}, None])
def test_team_name_falls_back_to_display_name(rosters, metadata):
    users = make_users(rosters)
    users[0]["metadata"] = metadata
    teams = build_teams(LEAGUE, rosters, users)
    row = teams.set_index("owner_id").loc[users[0]["user_id"]]
    assert row["team_name"] == users[0]["display_name"]


def test_team_without_owner_keeps_its_row(rosters):
    users = make_users(rosters)
    del users[4]  # the departed owner is no longer a league user
    rosters[4]["owner_id"] = None
    teams = build_teams(LEAGUE, rosters, users)
    orphan = teams.set_index("roster_id").loc[5]
    assert len(teams) == 12
    assert pd.isna(orphan["owner_id"]) and pd.isna(orphan["display_name"]) and pd.isna(orphan["team_name"])


# --- team_weeks ---

MEDIAN_LEAGUE = {"season": "2026", "settings": {"playoff_week_start": 15, "league_average_match": 1}}
NO_MEDIAN_LEAGUE = {"season": "2026", "settings": {"playoff_week_start": 15, "league_average_match": 0}}


def game(roster_id, matchup_id, points):
    return {"roster_id": roster_id, "matchup_id": matchup_id, "points": points}


@pytest.fixture
def week_1():
    return json.loads((FIXTURES / "matchups_week_01.json").read_text(encoding="utf-8"))


def test_week_1_fixture_invariants(week_1):
    tw = build_team_weeks(MEDIAN_LEAGUE, {1: week_1})
    assert list(tw.columns) == TEAM_WEEKS_COLUMNS
    assert len(tw) == 12 and tw["roster_id"].is_unique
    assert (tw["result"] == "W").sum() == 6 and (tw["result"] == "L").sum() == 6
    assert (tw["median_result"] == "W").sum() == 6  # 12 teams: 6 above the median, 6 below
    assert (tw["margin"].sum()) == pytest.approx(0)  # every margin is offset by its opponent's
    paired = tw.set_index("roster_id")
    for row in tw.itertuples():
        opp = paired.loc[row.opponent_roster_id]
        assert opp.opponent_roster_id == row.roster_id and opp.points == row.opponent_points
    assert not tw["is_playoff"].any()


def test_tie_and_margin():
    tw = build_team_weeks(NO_MEDIAN_LEAGUE, {3: [game(1, 1, 100.0), game(2, 1, 100.0), game(3, 2, 90.5), game(4, 2, 80.25)]})
    r = tw.set_index("roster_id")
    assert r.loc[1, "result"] == "T" and r.loc[2, "result"] == "T"
    assert r.loc[3, "result"] == "W" and r.loc[3, "margin"] == 10.25
    assert r.loc[4, "result"] == "L" and r.loc[4, "margin"] == -10.25


def test_no_median_column_when_league_has_no_median_game():
    tw = build_team_weeks(NO_MEDIAN_LEAGUE, {1: [game(1, 1, 100.0), game(2, 1, 90.0)]})
    assert "median_result" not in tw.columns


def test_playoff_week_with_bye():
    week = [game(1, 1, 120.0), game(2, 1, 110.0), game(3, None, 130.0), game(4, None, 70.0)]
    tw = build_team_weeks(MEDIAN_LEAGUE, {15: week})
    r = tw.set_index("roster_id")
    assert tw["is_playoff"].all()
    assert pd.isna(r.loc[3, "opponent_roster_id"]) and pd.isna(r.loc[3, "result"]) and pd.isna(r.loc[3, "margin"])
    assert pd.isna(r.loc[3, "matchup_id"])
    assert tw["median_result"].isna().all()  # no median game in the playoffs (assumption)


def test_median_tie_stops_the_run():
    week = [game(1, 1, 100.0), game(2, 1, 110.0), game(3, 2, 110.0), game(4, 2, 120.0), game(5, 3, 110.0), game(6, 3, 90.0)]
    with pytest.raises(ValueError, match="median"):
        build_team_weeks(MEDIAN_LEAGUE, {2: week})


def test_unpaired_matchup_stops_the_run():
    with pytest.raises(ValueError, match="matchup_id 2 has 1 team"):
        build_team_weeks(NO_MEDIAN_LEAGUE, {1: [game(1, 1, 100.0), game(2, 1, 90.0), game(3, 2, 80.0)]})


# --- player_weeks ---

ROSTER_POSITIONS = ["QB", "RB", "RB", "WR", "WR", "FLEX", "REC_FLEX", "SUPER_FLEX", "K", "DEF"] + ["BN"] * 6
LINEUP_LEAGUE = {"season": "2026", "roster_positions": ROSTER_POSITIONS}


def make_players(matchups):
    """A stand-in players cache: every numeric ID is a WR, every team abbreviation a defense."""
    ids = {pid for m in matchups for pid in m["players"]}
    return {
        pid: {"position": "WR", "full_name": f"Player {pid}", "team": "XX"} if pid.isdigit()
        else {"position": "DEF", "full_name": None, "first_name": "City", "last_name": pid, "team": pid}
        for pid in ids
    }


def test_week_1_fixture_rows_slots_and_points(week_1):
    pw = build_player_weeks(LINEUP_LEAGUE, {1: week_1}, make_players(week_1))
    assert list(pw.columns) == PLAYER_WEEKS_COLUMNS
    assert len(pw) == sum(len(m["players"]) for m in week_1)  # no empty slots in the fixture
    for m in week_1:
        team = pw[pw["roster_id"] == m["roster_id"]]
        starters = team[team["is_starter"]]
        assert starters["lineup_slot"].tolist() == ROSTER_POSITIONS[:10]
        assert starters["player_id"].tolist() == m["starters"]
        assert starters["points"].sum() == pytest.approx(m["points"])
        assert team["slot_order"].tolist() == list(range(len(m["players"])))
        assert (team.loc[~team["is_starter"], "lineup_slot"] == "BN").all()
    assert pw.loc[pw["lineup_slot"] == "DEF", "full_name"].str.startswith("City ").all()


def test_empty_starting_slot_is_kept_with_zero_points():
    m = {
        "roster_id": 1, "points": 20.0, "players": ["101", "102"], "players_points": {"101": 20.0, "102": 5.0},
        "starters": ["101", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
        "starters_points": [20.0] + [0.0] * 9,
    }
    pw = build_player_weeks(LINEUP_LEAGUE, {4: [m]}, make_players([m]))
    empty = pw[pw["is_empty_slot"]]
    assert len(empty) == 9 and (empty["points"] == 0).all() and empty["is_starter"].all()
    assert empty["position"].isna().all() and empty["full_name"].isna().all()
    assert empty["lineup_slot"].tolist() == ROSTER_POSITIONS[1:10]
    bench = pw[~pw["is_starter"]]
    assert bench["player_id"].tolist() == ["102"] and bench["slot_order"].tolist() == [10]


def test_player_missing_from_cache_keeps_its_row(week_1):
    players = make_players(week_1)
    missing = week_1[0]["starters"][0]
    del players[missing]
    pw = build_player_weeks(LINEUP_LEAGUE, {1: week_1}, players)
    row = pw[pw["player_id"] == missing].iloc[0]
    assert pd.isna(row["position"]) and row["points"] == week_1[0]["starters_points"][0]


def test_starter_count_mismatch_stops_the_run(week_1):
    week_1[0]["starters"] = week_1[0]["starters"][:9]
    with pytest.raises(ValueError, match="starting slots"):
        build_player_weeks(LINEUP_LEAGUE, {1: week_1}, make_players(week_1))


# --- transactions ---

PLAYERS = {"101": {"full_name": "Player One"}, "102": {"full_name": "Player Two"},
           "103": {"full_name": "Player Three"}, "KC": {"first_name": "Kansas City", "last_name": "Chiefs"}}
SEP_15_8PM_ET = 1789516800000  # 2026-09-16 00:00 UTC
AUG_30_NOON_ET = 1788105600000  # 2026-08-30 16:00 UTC


def txn(tid, type_, adds, drops, week=2, status="complete", created=SEP_15_8PM_ET, bid=None):
    settings = {"waiver_bid": bid} if type_ == "waiver" else None
    return {"transaction_id": tid, "type": type_, "status": status, "leg": week, "created": created,
            "adds": adds, "drops": drops, "settings": settings}


def build(transactions_by_week):
    return build_transactions({"season": "2026"}, transactions_by_week, PLAYERS, "2026-09-09")


def test_waiver_claim_is_an_add_and_a_drop_with_the_bid_on_the_add():
    moves = build({2: [txn("t1", "waiver", {"101": 3}, {"KC": 3}, bid=17)]})
    assert list(moves.columns) == TRANSACTIONS_COLUMNS
    assert moves["action"].tolist() == ["drop", "add"]
    add, drop = moves.set_index("action").loc["add"], moves.set_index("action").loc["drop"]
    assert add["player_name"] == "Player One" and add["waiver_bid"] == 17 and add["roster_id"] == 3
    assert drop["player_name"] == "Kansas City Chiefs" and pd.isna(drop["waiver_bid"])


def test_trade_of_three_players_is_six_rows():
    trade = txn("t2", "trade", adds={"101": 1, "102": 1, "103": 2}, drops={"101": 2, "102": 2, "103": 1})
    moves = build({2: [trade]})
    assert len(moves) == 6
    assert sorted(moves.loc[moves["action"] == "add", "roster_id"]) == [1, 1, 2]
    assert moves["waiver_bid"].isna().all()


def test_failed_transactions_are_dropped_and_null_adds_or_drops_are_fine():
    moves = build({2: [txn("t3", "waiver", {"101": 4}, None, status="failed", bid=50),
                       txn("t4", "free_agent", {"102": 4}, None),
                       txn("t5", "free_agent", None, {"103": 4})]})
    assert sorted(moves["transaction_id"]) == ["t4", "t5"]
    assert moves["waiver_bid"].isna().all()


def test_created_at_is_us_eastern_and_preseason_is_flagged():
    moves = build({1: [txn("t6", "free_agent", {"101": 5}, None, week=1, created=AUG_30_NOON_ET),
                       txn("t7", "free_agent", {"102": 5}, None, week=1, created=SEP_15_8PM_ET)]})
    rows = moves.set_index("transaction_id")
    assert str(rows.loc["t6", "created_at"]) == "2026-08-30 12:00:00-04:00"  # daylight time: UTC-4
    assert rows.loc["t6", "is_preseason"] and not rows.loc["t7", "is_preseason"]


def test_week_2_moves_are_never_preseason():
    moves = build({2: [txn("t8", "free_agent", {"101": 5}, None, week=2, created=AUG_30_NOON_ET)]})
    assert not moves["is_preseason"].any()


def state(season, start):
    return {"season": season, "season_type": "regular", "season_start_date": start}


def test_season_start_date_agrees_with_sleeper_in_season():
    assert season_start_date(state("2026", "2026-09-09"), LEAGUE, "2026-09-09") == "2026-09-09"


def test_season_start_date_that_disagrees_with_sleeper_stops_the_run():
    with pytest.raises(ValueError, match="Sleeper says season 2026 started 2026-09-09"):
        season_start_date(state("2026", "2026-09-09"), LEAGUE, "2026-09-10")


def test_season_start_date_survives_sleeper_moving_to_the_next_season():
    # Off-season: /state/nfl describes 2027, so config.yaml's date is used without a check.
    assert season_start_date(state("2027", "2027-09-08"), LEAGUE, "2026-09-09") == "2026-09-09"


def test_leg_that_disagrees_with_file_week_stops_the_run():
    with pytest.raises(ValueError, match="leg 3"):
        build({2: [txn("t9", "free_agent", {"101": 5}, None, week=3)]})


def test_save_table_writes_lists_as_json(rosters, tmp_path):
    rosters[0]["co_owners"] = ["999"]
    teams = build_teams(LEAGUE, rosters, make_users(rosters))
    path = save_table(teams, "teams", processed_dir=tmp_path)
    saved = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    assert list(saved.columns) == TEAMS_COLUMNS
    assert json.loads(saved.loc[0, "co_owners"]) == ["999"]
    assert saved.loc[1, "co_owners"] == "[]"
    assert saved.loc[0, "owner_id"] == rosters[0]["owner_id"]
