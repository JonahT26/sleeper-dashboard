"""Tests for all-play record, expected wins, and luck (METRICS_SPEC.md sections 1 and 2).

Seasons are made up but go through transform.build_team_weeks, so the inputs look
exactly like the real team_weeks table.
"""

import json
import random
from pathlib import Path

import pandas as pd
import pytest

from sleeper_dash.metrics.allplay import (
    METRICS_SEASON_COLUMNS,
    METRICS_TEAM_WEEKS_COLUMNS,
    build_allplay_tables,
    build_metrics_season,
    build_metrics_team_weeks,
    record_text,
)
from sleeper_dash.transform import build_team_weeks
from sleeper_dash.validate import check_allplay_and_luck

FIXTURES = Path(__file__).parent / "fixtures"
N_TEAMS = 12


def league(median=True, playoff_week_start=15):
    return {"season": "2026", "settings": {"playoff_week_start": playoff_week_start, "league_average_match": int(median)}}


def make_week(scores, pairs):
    """Matchups for one week. scores: {roster_id: points}; pairs: list of (a, b) games. Teams in no pair have no game."""
    matchup_of = {rid: i + 1 for i, pair in enumerate(pairs) for rid in pair}
    return [{"roster_id": rid, "matchup_id": matchup_of.get(rid), "points": pts} for rid, pts in scores.items()]


def random_season(seed, weeks=17, playoff_week_start=15, integer_scores=False):
    """A 12-team season: random pairings every week; from the playoffs on, only 4 teams have games."""
    rng = random.Random(seed)
    matchups = {}
    for week in range(1, weeks + 1):
        if integer_scores:  # coarse scores force all-play and head-to-head ties
            scores = {rid: float(rng.randint(95, 105)) for rid in range(1, N_TEAMS + 1)}
        else:
            scores = {rid: round(rng.uniform(70, 190), 2) for rid in range(1, N_TEAMS + 1)}
        order = rng.sample(range(1, N_TEAMS + 1), N_TEAMS)
        pairs = [tuple(order[i:i + 2]) for i in range(0, N_TEAMS, 2)]
        if week >= playoff_week_start:
            pairs = pairs[:2]
        matchups[week] = make_week(scores, pairs)
    return build_team_weeks(league(median=not integer_scores, playoff_week_start=playoff_week_start), matchups)


@pytest.fixture(params=[1, 2, 3])
def season_tables(request):
    team_weeks = random_season(request.param, integer_scores=request.param == 3)
    return team_weeks, build_allplay_tables({"team_weeks": team_weeks})


# --- Invariants the owner asked for -------------------------------------------------------------

def test_every_team_week_has_11_all_play_games(season_tables):
    _, tables = season_tables
    weekly = tables["metrics_team_weeks"]
    assert (weekly["allplay_wins"] + weekly["allplay_losses"] + weekly["allplay_ties"] == N_TEAMS - 1).all()


def test_league_expected_wins_equal_actual_wins_every_regular_season_week(season_tables):
    _, tables = season_tables
    weekly = tables["metrics_team_weeks"]
    regular = weekly[weekly["actual_wins"].notna()].groupby("week")
    assert len(regular) == 14
    for _, g in regular:
        assert g["actual_wins"].sum() == N_TEAMS / 2
        assert g["expected_wins"].sum() == pytest.approx(N_TEAMS / 2, abs=1e-9)


def test_luck_sums_to_zero_every_week_and_over_the_season(season_tables):
    _, tables = season_tables
    weekly, season = tables["metrics_team_weeks"], tables["metrics_season"]
    assert weekly.groupby("week")["luck"].sum().abs().max() < 1e-9
    assert season.groupby("through_week")["luck"].sum().abs().max() < 1e-9


# --- Spec sanity checks and examples ------------------------------------------------------------

def test_league_all_play_credit_is_66_per_week_and_average_is_500(season_tables):
    _, tables = season_tables
    weekly = tables["metrics_team_weeks"]
    credit = (weekly["allplay_wins"] + 0.5 * weekly["allplay_ties"]).groupby(weekly["week"]).sum()
    assert (credit == N_TEAMS * (N_TEAMS - 1) / 2).all()
    assert (weekly.groupby("week")["allplay_win_pct"].mean() - 0.5).abs().max() < 1e-12


def test_top_scorer_has_no_losses_and_bottom_scorer_no_wins(season_tables):
    team_weeks, tables = season_tables
    merged = tables["metrics_team_weeks"].merge(team_weeks, on=["season", "week", "roster_id"])
    for _, g in merged.groupby("week"):
        assert g.loc[g["points"].idxmax(), "allplay_losses"] == 0
        assert g.loc[g["points"].idxmin(), "allplay_wins"] == 0


def test_higher_score_always_means_more_all_play_wins(season_tables):
    team_weeks, tables = season_tables
    merged = tables["metrics_team_weeks"].merge(team_weeks, on=["season", "week", "roster_id"])
    for _, g in merged.groupby("week"):
        g = g.sort_values("points")
        higher = g["points"].diff() > 0
        assert (g["allplay_wins"].diff()[higher] > 0).all()


def test_weekly_ranges(season_tables):
    _, tables = season_tables
    weekly = tables["metrics_team_weeks"].dropna(subset=["luck"])
    assert weekly["expected_wins"].between(0, 1).all()
    assert (weekly["luck"].abs() <= 10 / 11 + 1e-12).all()


def test_spec_example_fourth_best_score():
    scores = {rid: 200.0 - 10 * rid for rid in range(1, 13)}  # roster 4 has the 4th-best score
    weekly = build_metrics_team_weeks(build_team_weeks(league(median=False), {1: make_week(scores, [(4, 1), (2, 3), (5, 6), (7, 8), (9, 10), (11, 12)])}))
    row = weekly.set_index("roster_id").loc[4]
    assert (row["allplay_wins"], row["allplay_losses"], row["allplay_ties"]) == (8, 3, 0)
    assert row["expected_wins"] == pytest.approx(8 / 11)
    assert row["luck"] == pytest.approx(-8 / 11)          # lost to roster 1
    assert weekly.set_index("roster_id").loc[1, "luck"] == pytest.approx(0.0)  # won with the top score


def test_ties_count_half_in_all_play_and_head_to_head():
    scores = {rid: 100.0 + rid for rid in range(1, 13)}
    scores[2] = scores[1] = 150.0  # rosters 1 and 2 tie for the top score and play each other
    weekly = build_metrics_team_weeks(build_team_weeks(league(median=False), {1: make_week(scores, [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12)])}))
    row = weekly.set_index("roster_id").loc[1]
    assert (row["allplay_wins"], row["allplay_losses"], row["allplay_ties"]) == (10, 0, 1)
    assert row["allplay_win_pct"] == pytest.approx(10.5 / 11)
    assert row["actual_wins"] == 0.5
    assert row["luck"] == pytest.approx(0.5 - 10.5 / 11)


def test_playoff_weeks_keep_all_play_but_freeze_luck(season_tables):
    _, tables = season_tables
    weekly, season = tables["metrics_team_weeks"], tables["metrics_season"]
    playoffs = weekly[weekly["week"] >= 15]
    assert playoffs[["actual_wins", "expected_wins", "luck"]].isna().all().all()
    assert playoffs["allplay_wins"].notna().all()

    by_week = season.set_index(["through_week", "roster_id"])
    for column in ["luck", "expected_wins", "actual_wins", "games", "h2h_wins"]:
        assert (by_week.loc[17, column] == by_week.loc[14, column]).all()      # frozen after week 14
    assert (by_week.loc[17, "allplay_wins"] >= by_week.loc[14, "allplay_wins"]).all()
    assert (by_week.loc[17, "allplay_wins"] + by_week.loc[17, "allplay_losses"] + by_week.loc[17, "allplay_ties"] == 17 * 11).all()


def test_season_rows_are_running_totals_of_the_weekly_rows(season_tables):
    _, tables = season_tables
    weekly, season = tables["metrics_team_weeks"], tables["metrics_season"]
    assert len(season) == 17 * N_TEAMS
    for through_week in (1, 7, 14, 17):
        expected = weekly[weekly["week"] <= through_week].groupby("roster_id")[["allplay_wins", "allplay_ties", "luck"]].sum()
        got = season[season["through_week"] == through_week].set_index("roster_id")
        assert (got["allplay_wins"] == expected["allplay_wins"]).all()
        assert (got["luck"] - expected["luck"]).abs().max() < 1e-9
        total = got["allplay_wins"] + got["allplay_losses"] + got["allplay_ties"]
        assert ((got["allplay_win_pct"] - (got["allplay_wins"] + 0.5 * got["allplay_ties"]) / total).abs() < 1e-12).all()
    week_14 = season[season["through_week"] == 14]
    assert (week_14["h2h_wins"] + week_14["h2h_losses"] + week_14["h2h_ties"] == week_14["games"]).all()
    assert (week_14["games"] == 14).all()
    assert ((week_14["actual_wins"] - (week_14["h2h_wins"] + 0.5 * week_14["h2h_ties"])).abs() < 1e-12).all()


def test_a_week_with_a_missing_team_uses_the_teams_that_scored():
    scores = {rid: 100.0 + rid for rid in range(1, 12)}  # 11 teams; roster 11 has no game
    weekly = build_metrics_team_weeks(build_team_weeks(league(median=False), {1: make_week(scores, [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)])}))
    assert (weekly["allplay_wins"] + weekly["allplay_losses"] + weekly["allplay_ties"] == 10).all()
    assert pd.isna(weekly.set_index("roster_id").loc[11, "luck"])  # no head-to-head game, so no luck


def test_median_cross_check_on_real_week_1():
    matchups = json.loads((FIXTURES / "matchups_week_01.json").read_text(encoding="utf-8"))
    team_weeks = build_team_weeks(league(), {1: matchups})
    tables = build_allplay_tables({"team_weeks": team_weeks})
    merged = tables["metrics_team_weeks"].merge(team_weeks, on=["season", "week", "roster_id"])
    assert ((merged["median_result"] == "W") == (merged["allplay_wins"] >= 6)).all()
    assert check_allplay_and_luck(tables["metrics_team_weeks"], tables["metrics_season"], team_weeks).passed


# --- Output shape, validation, display ----------------------------------------------------------

def test_output_columns_and_keys(season_tables):
    _, tables = season_tables
    assert list(tables["metrics_team_weeks"].columns) == METRICS_TEAM_WEEKS_COLUMNS
    assert list(tables["metrics_season"].columns) == METRICS_SEASON_COLUMNS
    assert not tables["metrics_team_weeks"].duplicated(["season", "week", "roster_id"]).any()
    assert not tables["metrics_season"].duplicated(["season", "through_week", "roster_id"]).any()


def test_validation_passes_on_good_tables_and_catches_bad_ones(season_tables):
    team_weeks, tables = season_tables
    weekly, season = tables["metrics_team_weeks"], tables["metrics_season"]
    assert check_allplay_and_luck(weekly, season, team_weeks).passed

    broken = weekly.copy()
    broken.loc[0, "allplay_wins"] += 1
    assert "W+L+T" in check_allplay_and_luck(broken, season, team_weeks).detail

    broken = weekly.copy()
    broken.loc[0, "luck"] += 0.1
    assert "luck sums to" in check_allplay_and_luck(broken, build_metrics_season(broken), team_weeks).detail


def test_record_text_shows_ties_only_when_there_are_any():
    assert record_text(41, 14, 0) == "41–14"
    assert record_text(41, 13, 1) == "41–13–1"
