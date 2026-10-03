"""Tests for the schedule table and strength of schedule (METRICS_SPEC.md section 5)."""

import pandas as pd
import pytest

from sleeper_dash.metrics import build_metric_tables
from sleeper_dash.metrics.schedule import SEASON_COLUMNS, strength_of_schedule
from sleeper_dash.transform import build_schedule, build_team_weeks
from sleeper_dash.validate import check_consistency_and_sos, check_schedule, check_season_efficiency

# A 4-team league with a 4-week regular season (playoffs from week 5).
LEAGUE = {"season": "2026", "settings": {"num_teams": 4, "start_week": 1, "playoff_week_start": 5, "league_average_match": 0}}
PAIRS = {1: [(1, 2), (3, 4)], 2: [(1, 3), (2, 4)], 3: [(1, 4), (2, 3)], 4: [(1, 2), (3, 4)], 5: [(1, 4)]}
# Every team scores the same each week, so its strength is that number: 100, 120, 80, 140.
SCORES = {1: 100.0, 2: 120.0, 3: 80.0, 4: 140.0}


def week_records(week, scores=SCORES):
    matchup = {rid: i + 1 for i, pair in enumerate(PAIRS[week]) for rid in pair}
    return [{"roster_id": rid, "matchup_id": matchup.get(rid), "points": pts if scores else 0.0} for rid, pts in SCORES.items()]


def tables_through(last_week, scores=SCORES):
    """team_weeks and schedule after `last_week` completed weeks; later regular-season weeks come from the published schedule."""
    played = {w: week_records(w, scores) for w in range(1, last_week + 1)}
    future = {w: week_records(w, None) for w in range(last_week + 1, 5)}
    return build_team_weeks(LEAGUE, played), build_schedule(LEAGUE, played, future)


def sos(last_week, min_weeks=1):
    team_weeks, schedule = tables_through(last_week)
    return strength_of_schedule(team_weeks, schedule, {"min_weeks": min_weeks}).set_index(["through_week", "roster_id"])


# --- schedule table -----------------------------------------------------------------------------

def test_schedule_combines_played_and_future_weeks_and_skips_playoffs():
    team_weeks, schedule = tables_through(2)
    assert sorted(schedule["week"].unique()) == [1, 2, 3, 4]
    assert schedule.groupby("week")["is_completed"].first().to_dict() == {1: True, 2: True, 3: False, 4: False}
    assert schedule.set_index(["week", "roster_id"]).loc[(3, 1), "opponent_roster_id"] == 4

    _, with_playoffs = tables_through(5)
    assert 5 not in set(with_playoffs["week"])


def test_schedule_rejects_overlapping_weeks_and_broken_pairings():
    with pytest.raises(ValueError, match="both"):
        build_schedule(LEAGUE, {1: week_records(1)}, {1: week_records(1, None)})
    broken = week_records(1)
    broken[0]["matchup_id"] = 2  # three teams in matchup 2
    with pytest.raises(ValueError, match="matchup_id 2 has 3"):
        build_schedule(LEAGUE, {1: broken}, {})


def test_schedule_validation_passes_and_catches_problems():
    team_weeks, schedule = tables_through(2)
    assert check_schedule(schedule, team_weeks, LEAGUE).passed

    missing_week = schedule[schedule["week"] != 4]
    assert "week 4: 0 schedule rows" in check_schedule(missing_week, team_weeks, LEAGUE).detail

    one_sided = schedule.copy()
    one_sided.loc[(one_sided["week"] == 3) & (one_sided["roster_id"] == 1), "opponent_roster_id"] = 3
    assert "doesn't list it back" in check_schedule(one_sided, team_weeks, LEAGUE).detail

    wrong_flag = schedule.assign(is_completed=True)
    assert "is_completed is wrong" in check_schedule(wrong_flag, team_weeks, LEAGUE).detail


# --- strength of schedule -----------------------------------------------------------------------

def test_hand_worked_example():
    # Through week 2, team 1 has played teams 2 (120) and 3 (80): mean 100.
    # Baseline = mean of the other three teams = (120 + 80 + 140) / 3 = 113.33, so SOS played = -13.33.
    # Still to play: team 4 (140) and team 2 (120): mean 130, so SOS remaining = +16.67.
    row = sos(2).loc[(2, 1)]
    assert row["sos_played"] == pytest.approx(100 - 340 / 3, abs=0.005)
    assert row["sos_remaining"] == pytest.approx(130 - 340 / 3, abs=0.005)
    assert (row["sos_games_played"], row["sos_games_remaining"]) == (2, 2)


def test_an_opponent_faced_twice_counts_twice():
    row = sos(4).loc[(4, 1)]                                   # opponents 2, 3, 4, 2
    assert row["sos_played"] == pytest.approx((120 + 80 + 140 + 120) / 4 - 340 / 3, abs=0.005)
    assert pd.isna(row["sos_remaining"]) and row["sos_games_remaining"] == 0


def test_baseline_excludes_the_team_itself():
    # Team 4 is the strongest. Against the plain league average (110) its opponents would look
    # weaker partly because it can't play itself; against the other three teams (100) they don't.
    row = sos(4).loc[(4, 4)]                                   # opponents 3, 2, 1, 3: mean 95
    assert row["sos_played"] == pytest.approx(95 - 100, abs=0.005)


def test_equal_teams_give_zero_sos():
    team_weeks, schedule = tables_through(2)
    flat = team_weeks.assign(points=110.0)
    result = strength_of_schedule(flat, schedule, {"min_weeks": 1})
    assert (result["sos_played"] == 0).all() and (result["sos_remaining"] == 0).all()


def test_hidden_until_min_weeks_but_game_counts_always_shown():
    result = sos(3, min_weeks=3)
    assert result.loc[[1, 2], ["sos_played", "sos_remaining"]].isna().all().all()
    assert result.loc[3, "sos_played"].notna().all()
    assert (result["sos_games_played"] + result["sos_games_remaining"] == 4).all()


def test_playoff_weeks_count_toward_strength_but_not_the_schedule():
    played = {w: week_records(w) for w in range(1, 6)}
    played[5] = [dict(r, points=r["points"] + (100 if r["roster_id"] == 2 else 0)) for r in played[5]]  # team 2 scores 220 in week 5
    team_weeks = build_team_weeks(LEAGUE, played)
    schedule = build_schedule(LEAGUE, played, {})
    result = strength_of_schedule(team_weeks, schedule, {"min_weeks": 1}).set_index(["through_week", "roster_id"])
    row = result.loc[(5, 1)]
    assert row["sos_games_played"] == 4 and pd.isna(row["sos_remaining"])
    strength_2 = (120 * 4 + 220) / 5                           # week 5 raises team 2's strength
    assert row["sos_played"] == pytest.approx((strength_2 + 80 + 140 + strength_2) / 4 - (strength_2 + 80 + 140) / 3, abs=0.005)


def test_output_columns():
    team_weeks, schedule = tables_through(2)
    assert list(strength_of_schedule(team_weeks, schedule, {"min_weeks": 1}).columns) == SEASON_COLUMNS


# --- combined metric tables ---------------------------------------------------------------------

def test_metric_tables_combine_every_module_and_pass_validation():
    team_weeks, schedule = tables_through(3)
    params = {"consistency": {"min_weeks": 2, "floor_pct": 0.1, "ceiling_pct": 0.9, "boom_margin": 20, "bust_margin": 20},
              "schedule": {"min_weeks": 1},
              "power": {"weights": {"season_scoring": 0.35, "recent_form": 0.25, "roster_strength": 0.2, "results": 0.2},
                        "recent_weeks": 3, "scale": 15, "shrink_weeks": 3}}
    params["awards"] = {"enabled": ["top_score", "blowout"]}
    lineups = team_weeks[["season", "week", "roster_id"]].assign(
        actual_points=team_weeks["points"], optimal_points=team_weeks["points"] + 5, bench_points_lost=5.0, efficiency=team_weeks["points"] / (team_weeks["points"] + 5))
    players = team_weeks[["season", "week", "roster_id", "points"]].assign(
        player_id=team_weeks["roster_id"].astype(str), full_name="Player", is_starter=True, is_empty_slot=False)
    moves = pd.DataFrame(columns=["transaction_id", "season", "week", "type", "roster_id", "player_id", "action", "created_at", "is_preseason"])
    teams = pd.DataFrame({"roster_id": [1, 2, 3, 4], "team_name": ["A", "B", "C", "D"]})
    tables = build_metric_tables({"team_weeks": team_weeks, "schedule": schedule, "lineups_optimal": lineups,
                                  "player_weeks": players, "transactions": moves, "teams": teams}, params)
    assert len(tables["power_rankings"]) == 3 * 4
    # Constant scores make both games in weeks 2 and 3 equal-margin wins (20 and 40), so Blowout has co-winners there.
    assert tables["awards"]["award"].value_counts().to_dict() == {"top_score": 3, "blowout": 5}
    weekly, season = tables["metrics_team_weeks"], tables["metrics_season"]
    assert len(weekly) == len(team_weeks) and len(season) == 3 * 4
    assert {"luck", "is_boom", "points_vs_median"} <= set(weekly.columns)
    assert {"luck", "volatility", "sos_played", "sos_remaining", "efficiency", "bench_points_lost"} <= set(season.columns)
    assert check_consistency_and_sos(weekly, season, LEAGUE).passed
    assert check_season_efficiency(season, lineups).passed

    broken = season.assign(sos_games_remaining=season["sos_games_remaining"] + 1)
    assert "expected 4" in check_consistency_and_sos(weekly, broken, LEAGUE).detail
