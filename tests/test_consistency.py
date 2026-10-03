"""Tests for consistency: volatility, floor/ceiling, boom and bust (METRICS_SPEC.md section 4)."""

import random

import numpy as np
import pandas as pd
import pytest

from sleeper_dash.metrics.consistency import (
    SEASON_COLUMNS,
    TEAM_WEEK_COLUMNS,
    check_params,
    consistency_season,
    consistency_team_weeks,
)
from sleeper_dash.validate import check_consistency_and_sos

PARAMS = {"min_weeks": 3, "floor_pct": 0.10, "ceiling_pct": 0.90, "boom_margin": 20, "bust_margin": 20}


def team_weeks_from(scores):
    """scores: {week: {roster_id: points}} -> a minimal team_weeks table."""
    rows = [{"season": 2026, "week": w, "roster_id": r, "points": p} for w, teams in scores.items() for r, p in teams.items()]
    return pd.DataFrame(rows)


def build(scores, params=PARAMS):
    team_weeks = team_weeks_from(scores)
    weekly = consistency_team_weeks(team_weeks, params)
    return weekly, consistency_season(team_weeks, weekly, params)


def random_scores(seed, weeks=17, teams=12):
    rng = random.Random(seed)
    return {w: {r: round(rng.uniform(70, 190), 2) for r in range(1, teams + 1)} for w in range(1, weeks + 1)}


def test_points_vs_median_and_thresholds_count_exactly_on_the_line():
    # Three teams: the median each week is roster 2's score.
    weekly, _ = build({1: {1: 120.0, 2: 100.0, 3: 80.0}, 2: {1: 119.99, 2: 100.0, 3: 80.01}})
    w = weekly.set_index(["week", "roster_id"])
    assert w.loc[(1, 1), "points_vs_median"] == 20.0 and w.loc[(1, 1), "is_boom"]       # exactly +20 is a boom
    assert w.loc[(1, 3), "points_vs_median"] == -20.0 and w.loc[(1, 3), "is_bust"]      # exactly -20 is a bust
    assert not w.loc[(2, 1), "is_boom"] and not w.loc[(2, 3), "is_bust"]                # 0.01 short of each line
    assert not w.loc[(1, 2), "is_boom"] and not w.loc[(1, 2), "is_bust"]


def test_even_number_of_teams_uses_the_average_of_the_middle_two_scores():
    weekly, _ = build({1: {1: 150.0, 2: 101.25, 3: 101.24, 4: 60.0}})
    assert weekly.set_index("roster_id")["points_vs_median"].to_dict() == pytest.approx({1: 48.755, 2: 0.005, 3: -0.005, 4: -41.245})


def test_volatility_is_the_sample_sd_of_score_minus_median_and_floor_ceiling_are_percentiles():
    scores = {1: {1: 100.0, 2: 90.0, 3: 80.0}, 2: {1: 110.0, 2: 120.0, 3: 100.0}, 3: {1: 120.0, 2: 110.0, 3: 130.0}}
    _, season = build(scores)
    row = season.query("through_week == 3").set_index("roster_id").loc[1]
    d = [100 - 90, 110 - 110, 120 - 120]                          # roster 1 vs each week's median
    assert row["volatility"] == pytest.approx(np.std(d, ddof=1), abs=0.005)
    assert row["floor"] == pytest.approx(102.0)                    # 10th percentile of 100, 110, 120
    assert row["ceiling"] == pytest.approx(118.0)                  # 90th percentile
    assert row["weeks"] == 3


def test_hidden_until_min_weeks_but_boom_counts_shown_from_week_1():
    scores = {1: {1: 150.0, 2: 100.0, 3: 90.0}, 2: {1: 100.0, 2: 110.0, 3: 90.0}, 3: {1: 100.0, 2: 110.0, 3: 90.0}}
    _, season = build(scores)
    s = season.set_index(["through_week", "roster_id"])
    assert s.loc[(1, 1), ["volatility", "floor", "ceiling"]].isna().all()
    assert s.loc[(2, 1), ["volatility", "floor", "ceiling"]].isna().all()
    assert s.loc[(1, 1), "boom_weeks"] == 1 and s.loc[(1, 1), "boom_rate"] == 1.0
    assert s.loc[(3, 1), ["volatility", "floor", "ceiling"]].notna().all()
    assert s.loc[(3, 1), "boom_rate"] == pytest.approx(1 / 3)


def test_team_at_the_median_every_week_has_zero_volatility_and_no_booms_or_busts():
    scores = {w: {1: 100.0 + 40 * w, 2: 100.0 + w, 3: 50.0 - w} for w in range(1, 6)}  # roster 2 is always the median
    _, season = build(scores)
    row = season.query("through_week == 5").set_index("roster_id").loc[2]
    assert row["volatility"] == 0 and row["boom_weeks"] == 0 and row["bust_weeks"] == 0


def test_volatility_ignores_league_wide_shifts_in_a_week():
    scores = random_scores(1)
    shifted = {w: {r: round(p + 7.5 * w, 2) for r, p in teams.items()} for w, teams in scores.items()}  # a different shift every week
    _, base = build(scores)
    _, moved = build(shifted)
    assert (base["volatility"] - moved["volatility"]).abs().max() < 0.011  # equal up to rounding to 2 dp
    assert (base["boom_weeks"] == moved["boom_weeks"]).all() and (base["bust_weeks"] == moved["bust_weeks"]).all()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_invariants_on_random_seasons(seed):
    scores = random_scores(seed)
    weekly, season = build(scores)
    assert not (weekly["is_boom"] & weekly["is_bust"]).any()
    full = season.dropna(subset=["floor"])
    medians = team_weeks_from(scores).groupby("roster_id")["points"].median()
    last = season.query("through_week == 17").set_index("roster_id")
    assert (last["floor"] <= medians).all() and (medians <= last["ceiling"]).all()
    assert (full["floor"] <= full["ceiling"]).all() and (full["volatility"] >= 0).all()
    assert (season["boom_weeks"] + season["bust_weeks"] <= season["weeks"]).all()
    assert season["boom_rate"].between(0, 1).all() and season["bust_rate"].between(0, 1).all()
    assert (last["weeks"] == 17).all()  # playoff weeks count, for every team


def test_output_columns():
    weekly, season = build(random_scores(4, weeks=3))
    assert list(weekly.columns) == TEAM_WEEK_COLUMNS and list(season.columns) == SEASON_COLUMNS
    assert len(season) == 3 * 12


@pytest.mark.parametrize("change, message", [
    ({"boom_margin": 0}, "greater than 0"),
    ({"bust_margin": -5}, "greater than 0"),
    ({"floor_pct": 0.95}, "floor_pct"),
    ({"min_weeks": 1}, "min_weeks"),
])
def test_bad_parameters_stop_with_a_clear_message(change, message):
    with pytest.raises(ValueError, match=message):
        check_params({**PARAMS, **change})


def test_validation_catches_a_boom_and_bust_in_the_same_week():
    weekly, season = build(random_scores(5, weeks=3))
    season = season.assign(sos_games_played=season["through_week"], sos_games_remaining=14 - season["through_week"])
    league = {"settings": {"start_week": 1, "playoff_week_start": 15}}
    assert check_consistency_and_sos(weekly, season, league).passed
    weekly.loc[0, ["is_boom", "is_bust"]] = True
    assert "both a boom and a bust" in check_consistency_and_sos(weekly, season, league).detail
