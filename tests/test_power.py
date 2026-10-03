"""Tests for the power score and rankings (METRICS_SPEC.md section 6)."""

import math
import random

import pandas as pd
import pytest

from sleeper_dash.metrics.power import COMPONENTS, POWER_RANKINGS_COLUMNS, build_power_rankings, check_params
from sleeper_dash.transform import build_team_weeks
from sleeper_dash.validate import check_power_rankings

PARAMS = {
    "weights": {"season_scoring": 0.35, "recent_form": 0.25, "roster_strength": 0.20, "results": 0.20},
    "recent_weeks": 3, "scale": 15, "shrink_weeks": 3,
}
N = 12


def league(playoff_week_start=15):
    return {"season": "2026", "settings": {"playoff_week_start": playoff_week_start, "league_average_match": 1}}


def random_league(seed, weeks=17):
    """team_weeks and lineups_optimal for a 12-team season; from week 15 only 4 teams have games."""
    rng = random.Random(seed)
    matchups, optimal = {}, []
    for week in range(1, weeks + 1):
        scores = {r: round(rng.uniform(70, 190), 2) for r in range(1, N + 1)}
        order = rng.sample(range(1, N + 1), N)
        pairs = [order[i:i + 2] for i in range(0, N, 2)][: 2 if week >= 15 else 6]
        matchup = {r: i + 1 for i, pair in enumerate(pairs) for r in pair}
        matchups[week] = [{"roster_id": r, "matchup_id": matchup.get(r), "points": p} for r, p in scores.items()]
        optimal += [{"season": 2026, "week": week, "roster_id": r, "optimal_points": round(p + rng.uniform(0, 40), 2)}
                    for r, p in scores.items()]
    return build_team_weeks(league(), matchups), pd.DataFrame(optimal)


@pytest.fixture(params=[1, 2])
def season(request):
    team_weeks, lineups = random_league(request.param)
    return team_weeks, lineups, build_power_rankings(team_weeks, lineups, PARAMS)


def by_week(rankings, week):
    return rankings[rankings["week"] == week].set_index("roster_id")


# --- Spec sanity checks -------------------------------------------------------------------------

def test_league_mean_is_50_and_contributions_sum_to_the_power_score(season):
    _, _, rankings = season
    assert (rankings.groupby("week")["power_score"].mean() - 50).abs().max() < 1e-9
    contributions = rankings[[f"contrib_{c}" for c in COMPONENTS]].sum(axis=1)
    assert (contributions - rankings["power_score"]).abs().max() < 1e-9


def test_scores_stay_inside_the_guaranteed_range(season):
    _, _, rankings = season
    bound = 15 * (N - 1) / math.sqrt(N)                         # 47.6 for 12 teams
    assert rankings["power_score"].between(50 - bound, 50 + bound).all()
    for c in COMPONENTS:                                       # every contribution positive, for the stacked bars
        assert (rankings[f"contrib_{c}"] > 0).all()


def test_ranks_are_1_to_n_every_week_and_rank_change_follows_them(season):
    _, _, rankings = season
    for _, g in rankings.groupby("week"):
        assert sorted(g["rank"]) == list(range(1, N + 1))
    assert rankings.loc[rankings["week"] == 1, "rank_change"].isna().all()
    for week in range(2, 18):
        change = by_week(rankings, week - 1)["rank"] - by_week(rankings, week)["rank"]
        assert (by_week(rankings, week)["rank_change"].astype(int) == change).all()
    assert check_power_rankings(rankings, season[0]).passed


def test_a_team_best_at_everything_ranks_first():
    team_weeks, lineups = random_league(3, weeks=5)
    best = 7
    team_weeks.loc[team_weeks["roster_id"] == best, "points"] = 250.0                # top scorer every week
    lineups.loc[lineups["roster_id"] == best, "optimal_points"] = 300.0
    opponents = team_weeks.loc[team_weeks["roster_id"] == best, ["week", "opponent_roster_id"]]
    team_weeks.loc[team_weeks["roster_id"] == best, "result"] = "W"                  # and won every game
    for week, opp in opponents.itertuples(index=False):
        team_weeks.loc[(team_weeks["week"] == week) & (team_weeks["roster_id"] == opp), "result"] = "L"
    rankings = build_power_rankings(team_weeks, lineups, PARAMS)
    assert (rankings.loc[rankings["roster_id"] == best, "rank"] == 1).all()


def test_a_zero_weight_component_has_no_effect_on_the_ranking():
    team_weeks, lineups = random_league(4, weeks=6)
    params = {**PARAMS, "weights": {"season_scoring": 0.5, "recent_form": 0.3, "roster_strength": 0.2, "results": 0.0}}
    flipped = team_weeks.assign(result=team_weeks["result"].map({"W": "L", "L": "W", "T": "T"}))
    a = build_power_rankings(team_weeks, lineups, params)
    b = build_power_rankings(flipped, lineups, params)
    assert (a["rank"] == b["rank"]).all()
    assert (a["contrib_results"] == 0).all()


@pytest.mark.parametrize("shrink_weeks", [0, 1, 10])
def test_ranking_is_identical_for_any_shrink_weeks(season, shrink_weeks):
    team_weeks, lineups, rankings = season
    other = build_power_rankings(team_weeks, lineups, {**PARAMS, "shrink_weeks": shrink_weeks})
    assert (other["rank"] == rankings["rank"]).all()


# --- Formula, components, and edge cases --------------------------------------------------------

def test_hand_worked_four_team_example():
    # Week 1: A 100, B 120, C 80, D 140; B beat A and D beat C. Optimal = points + 10 for everyone.
    matchups = {1: [{"roster_id": 1, "matchup_id": 1, "points": 100.0}, {"roster_id": 2, "matchup_id": 1, "points": 120.0},
                    {"roster_id": 3, "matchup_id": 2, "points": 80.0}, {"roster_id": 4, "matchup_id": 2, "points": 140.0}]}
    team_weeks = build_team_weeks(league(), matchups)
    lineups = team_weeks[["season", "week", "roster_id"]].assign(optimal_points=team_weeks["points"] + 10)
    row = build_power_rankings(team_weeks, lineups, PARAMS).set_index("roster_id").loc[4]

    z_points = 30 / math.sqrt(500)          # mean 110, population SD sqrt(500)
    z_results = 1.0                         # results 0, 1, 0, 1: mean 0.5, SD 0.5
    f = 1 / (1 + 3)
    assert row["contrib_season_scoring"] == pytest.approx(0.35 * (50 + 15 * f * z_points))
    assert row["contrib_results"] == pytest.approx(0.20 * (50 + 15 * f * z_results))
    assert row["power_score"] == pytest.approx(50 + 15 * f * (0.80 * z_points + 0.20 * z_results))
    assert row["rank"] == 1 and pd.isna(row["rank_change"])


def test_recent_form_uses_the_last_recent_weeks_only(season):
    team_weeks, _, rankings = season
    expected = team_weeks[team_weeks["week"].between(3, 5)].groupby("roster_id")["points"].mean()
    assert (by_week(rankings, 5)["recent_form"] - expected).abs().max() < 1e-9
    early = team_weeks[team_weeks["week"] <= 2].groupby("roster_id")["points"].mean()      # fewer weeks than the window
    assert (by_week(rankings, 2)["recent_form"] - early).abs().max() < 1e-9


def test_results_are_head_to_head_only_and_frozen_in_the_playoffs(season):
    team_weeks, _, rankings = season
    regular = team_weeks[team_weeks["week"] <= 14]
    h2h = regular["result"].map({"W": 1.0, "T": 0.5, "L": 0.0}).groupby(regular["roster_id"]).mean()
    for week in (14, 15, 17):
        assert (by_week(rankings, week)["results"] - h2h).abs().max() < 1e-12
    assert (by_week(rankings, 17)["season_scoring"] != by_week(rankings, 14)["season_scoring"]).any()   # others keep updating


def test_early_season_compression():
    team_weeks, lineups = random_league(5, weeks=2)
    rankings = build_power_rankings(team_weeks, lineups, PARAMS)
    bound_week_1 = 15 * (1 / 4) * (N - 1) / math.sqrt(N)      # f = 1/(1+3) in week 1: within 50 ± 11.9
    assert (by_week(rankings, 1)["power_score"] - 50).abs().max() <= bound_week_1 + 1e-9


def test_a_component_with_no_spread_gives_everyone_50_times_its_weight():
    team_weeks, lineups = random_league(6, weeks=3)
    lineups["optimal_points"] = 150.0
    rankings = build_power_rankings(team_weeks, lineups, PARAMS)
    assert (rankings["contrib_roster_strength"] - 0.20 * 50).abs().max() < 1e-12


def test_exact_ties_go_to_season_scoring_then_results_then_roster_id():
    matchups = {1: [{"roster_id": r, "matchup_id": (r + 1) // 2, "points": p} for r, p in
                    [(1, 100.0), (2, 100.0), (3, 100.0), (4, 100.0)]]}
    no_median = {"season": "2026", "settings": {"playoff_week_start": 15, "league_average_match": 0}}
    team_weeks = build_team_weeks(no_median, matchups)         # four identical scores: every game a tie
    lineups = team_weeks[["season", "week", "roster_id"]].assign(optimal_points=110.0)
    rankings = build_power_rankings(team_weeks, lineups, PARAMS).set_index("roster_id")
    assert rankings["rank"].to_dict() == {1: 1, 2: 2, 3: 3, 4: 4}


def test_output_columns(season):
    assert list(season[2].columns) == POWER_RANKINGS_COLUMNS


@pytest.mark.parametrize("change, message", [
    ({"weights": {**PARAMS["weights"], "results": 0.25}}, "sum to 1"),
    ({"weights": {"season_scoring": 0.8, "recent_form": 0.2}}, "exactly"),
    ({"weights": {**PARAMS["weights"], "results": -0.2, "season_scoring": 0.75}}, ">= 0"),
    ({"scale": 20}, "outside 0-100"),
    ({"recent_weeks": 0}, "recent_weeks"),
])
def test_bad_parameters_stop_with_a_clear_message(change, message):
    with pytest.raises(ValueError, match=message):
        check_params({**PARAMS, **change}, n_teams=12)


def test_validation_catches_broken_tables(season):
    team_weeks, _, rankings = season
    broken = rankings.copy()
    broken.loc[5, "rank_change"] = 99
    assert "rank_change" in check_power_rankings(broken, team_weeks).detail
    broken = rankings.copy()
    broken.loc[5, "power_score"] += 1
    detail = check_power_rankings(broken, team_weeks).detail
    assert "don't sum" in detail and "not 50" in detail
