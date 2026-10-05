"""Tests for metrics/playoff_odds.py (METRICS_SPEC.md section 8): invariants, proofs, reproducibility, edge cases."""

import numpy as np
import pandas as pd
import pytest

from sleeper_dash.metrics import playoff_odds as po
from sleeper_dash.validate import check_playoff_odds

TEAMS = 12
REGULAR_WEEKS = 14
PARAMS = {"simulations": 2000, "seed": 2026, "shrink_weeks": 6, "min_weeks": 3}
SEED_COLS = [f"p_seed_{s}" for s in po.SEEDS]


def make_league(median=True, **settings):
    return {"season": "2026", "settings": {"num_teams": TEAMS, "playoff_week_start": REGULAR_WEEKS + 1,
                                           "league_average_match": int(median), "playoff_teams": 6,
                                           "playoff_round_type": 0, "playoff_seed_type": 0, **settings}}


def pairings():
    """This league's shape: an 11-week round robin (circle method), then weeks 1-3 repeated."""
    ids, weeks = list(range(1, TEAMS + 1)), {}
    for week in range(1, 12):
        weeks[week] = [(ids[i], ids[-1 - i]) for i in range(TEAMS // 2)]
        ids = [ids[0], ids[-1]] + ids[1:-1]
    for week in range(12, REGULAR_WEEKS + 1):
        weeks[week] = weeks[week - 11]
    return weeks


def league_tables(points, through_week, median=True):
    """team_weeks through `through_week` and the full regular-season schedule, from {(week, roster_id): points}."""
    games, schedule = [], []
    for week, pairs in pairings().items():
        week_points = {r: points[(week, r)] for r in range(1, TEAMS + 1)}
        week_median = np.median(list(week_points.values()))
        for a, b in pairs:
            for me, them in ((a, b), (b, a)):
                schedule.append({"season": 2026, "week": week, "roster_id": me, "opponent_roster_id": them,
                                 "is_completed": week <= through_week})
                if week <= through_week:
                    mine, theirs = week_points[me], week_points[them]
                    games.append({"season": 2026, "week": week, "roster_id": me, "points": mine,
                                  "result": "W" if mine > theirs else "L" if mine < theirs else "T",
                                  "median_result": ("W" if mine > week_median else "L") if median else None,
                                  "is_playoff": False})
    team_weeks = pd.DataFrame(games).sort_values(["week", "roster_id"]).reset_index(drop=True)
    return team_weeks, pd.DataFrame(schedule).astype({"opponent_roster_id": "Int64"})


def random_points(seed=1):
    rng = np.random.default_rng(seed)
    strength = rng.normal(0, 8, TEAMS)
    return {(w, r): round(float(120 + strength[r - 1] + rng.normal(0, 20)), 2)
            for w in range(1, REGULAR_WEEKS + 1) for r in range(1, TEAMS + 1)}


def ordered_points():
    """Team 1 outscores team 2, which outscores team 3, ... every week: the standings are never in doubt."""
    return {(w, r): 200.0 - 10 * r + w / 100 for w in range(1, REGULAR_WEEKS + 1) for r in range(1, TEAMS + 1)}


def odds(points, through_week, params=PARAMS, median=True, **settings):
    team_weeks, schedule = league_tables(points, through_week, median)
    return po.build_playoff_odds(team_weeks, schedule, make_league(median, **settings), params), team_weeks


# --- the spec's sanity checks ----------------------------------------------------------------

def test_probabilities_sum_across_teams_and_seeds():
    table, team_weeks = odds(random_points(), 8)
    assert sorted(table["week"].unique()) == list(range(3, 9))  # from min_weeks to the latest completed week
    for _, g in table.groupby("week"):
        assert len(g) == TEAMS
        assert g["p_playoffs"].sum() == pytest.approx(6, abs=1e-9)
        assert g["p_bye"].sum() == pytest.approx(2, abs=1e-9)
        assert g["p_title"].sum() == pytest.approx(1, abs=1e-9)
        for column in SEED_COLS:  # every seed goes to exactly one team in every simulation
            assert g[column].sum() == pytest.approx(1, abs=1e-9)
    assert np.allclose(table[SEED_COLS].sum(axis=1), table["p_playoffs"])
    assert np.allclose(table[["p_seed_1", "p_seed_2"]].sum(axis=1), table["p_bye"])
    assert (table["p_title"] <= table["p_playoffs"]).all() and (table["p_bye"] <= table["p_playoffs"]).all()
    assert table[["p_playoffs", "p_bye", "p_title"] + SEED_COLS].stack().between(0, 1).all()
    assert check_playoff_odds(table, team_weeks, make_league()).passed


def test_average_final_wins_add_up_to_the_seasons_wins():
    # With a median game each week has 6 head-to-head winners plus 6 median winners; without it, 6.
    with_median, _ = odds(random_points(), 5)
    without, team_weeks = odds(random_points(), 5, median=False)
    assert with_median.groupby("week")["avg_wins"].sum().round(2).eq(TEAMS * REGULAR_WEEKS).all()
    assert without.groupby("week")["avg_wins"].sum().round(2).eq(TEAMS // 2 * REGULAR_WEEKS).all()
    games = 2 * REGULAR_WEEKS
    assert np.allclose(with_median["avg_wins"] + with_median["avg_losses"], games, atol=1e-3)
    assert check_playoff_odds(without, team_weeks, make_league(median=False)).passed


def test_clinched_teams_show_100_and_eliminated_teams_0():
    table, team_weeks = odds(ordered_points(), 12)
    week = table[table["week"] == 12].set_index("roster_id")
    assert week.loc[1, "clinched"] and not week.loc[1, "out"]  # 24-0 with two weeks left
    assert week.loc[12, "out"] and not week.loc[12, "clinched"]  # 0-24
    assert table["clinched"].any() and table["out"].any()
    clinched, out = table[table["clinched"]], table[table["out"]]
    assert (clinched["p_playoffs"] == 1).all()
    assert (out[["p_playoffs", "p_bye", "p_title"] + SEED_COLS] == 0).all().all()
    assert not (table["clinched"] & table["out"]).any()
    assert check_playoff_odds(table, team_weeks, make_league()).passed


def test_the_bounds_are_proofs_not_simulation_results():
    standings = pd.DataFrame({"standing": [20.0, 19, 18, 17, 16, 15, 14, 6, 5, 4, 3, 2]}, index=range(1, 13))
    clinched, out = po.proven_status(standings, games_left=np.full(12, 4), places=6)
    # Clinched: team 1 (20) can be reached only by teams 2-5 (team 6 tops out at 15 + 4 = 19); team 2 (19) by
    # teams 1 and 3-6, five teams. Team 3 (18) could be caught by six. Out: teams 8-12 (best 10 or less) already
    # trail six teams; team 7 (best 18) trails only teams 1 and 2 for certain.
    assert clinched.tolist() == [True, True, False, False, False, False, False, False, False, False, False, False]
    assert out.tolist() == [False] * 7 + [True] * 5
    # A near-certain team that a bound can't prove stays unproven, whatever the simulation says.
    almost, _ = po.proven_status(pd.DataFrame({"standing": [24.0] + [20.0] * 6 + [0.0] * 5}),
                                 games_left=np.full(12, 4), places=6)
    assert not almost[0]


def test_after_the_last_regular_season_week_the_odds_are_the_final_standings():
    table, team_weeks = odds(random_points(), REGULAR_WEEKS)
    final = table[table["week"] == REGULAR_WEEKS].set_index("roster_id")
    seeds = po.seeding(po.standings_through(team_weeks, REGULAR_WEEKS))
    for place, roster_id in enumerate(seeds, start=1):
        row = final.loc[roster_id]
        assert row["p_playoffs"] == (1.0 if place <= 6 else 0.0)
        assert row["p_bye"] == (1.0 if place <= 2 else 0.0)
        assert [row[c] for c in SEED_COLS] == [float(place == s) for s in po.SEEDS]
        assert row["clinched"] == (place <= 6) and row["out"] == (place > 6)
    assert final["p_title"].sum() == pytest.approx(1)  # the playoffs themselves are still simulated
    assert check_playoff_odds(table, team_weeks, make_league()).passed


# --- reproducibility (sanity check 6) ---------------------------------------------------------

def test_two_runs_give_identical_tables():
    first, _ = odds(random_points(), 6)
    second, _ = odds(random_points(), 6)
    assert first.to_csv(index=False) == second.to_csv(index=False)


def test_a_different_seed_moves_odds_by_monte_carlo_error_only():
    sims = 4000
    first, _ = odds(random_points(), 6, params={**PARAMS, "simulations": sims})
    other, _ = odds(random_points(), 6, params={**PARAMS, "simulations": sims, "seed": 7})
    assert not first.equals(other)
    for column in ["p_playoffs", "p_bye", "p_title"]:
        p = (first[column] + other[column]) / 2
        se = np.sqrt(2 * p * (1 - p) / sims)  # SE of the difference of two independent estimates
        assert ((first[column] - other[column]).abs() <= 4 * se + 1e-12).all(), column


def test_each_week_has_its_own_seed():
    # Week 5's odds don't depend on which other weeks were simulated in the same run.
    team_weeks, schedule = league_tables(random_points(), 6)
    alone = po.odds_for_week(team_weeks, schedule, 2026, 5, po.league_format(make_league()), PARAMS)
    together = po.build_playoff_odds(team_weeks, schedule, make_league(), PARAMS)
    pd.testing.assert_frame_equal(alone, together[together["week"] == 5].reset_index(drop=True), check_dtype=False)


# --- monotonicity (sanity check 7) ------------------------------------------------------------

@pytest.mark.parametrize("team", [3, 8])
def test_better_past_scores_never_lower_playoff_or_bye_odds(team):
    base = random_points()
    boosted = {key: value + (15 if key[1] == team and key[0] <= 6 else 0) for key, value in base.items()}
    before, _ = odds(base, 6)
    after, _ = odds(boosted, 6)
    b, a = before[before["roster_id"] == team], after[after["roster_id"] == team]
    assert (a["p_playoffs"].to_numpy() >= b["p_playoffs"].to_numpy()).all()
    assert (a["p_bye"].to_numpy() >= b["p_bye"].to_numpy()).all()
    assert (a["strength"].to_numpy() > b["strength"].to_numpy()).all()


# --- the model's pieces ------------------------------------------------------------------------

def test_strength_estimates_follow_the_formula():
    d = np.array([[10.0, -10.0], [20.0, -20.0], [0.0, 0.0]])  # 3 weeks x 2 teams, each week's mean 0
    strength, strength_sd, sigma = po.strength_estimates(d, shrink_weeks=6)
    # Team means 10 and -10; pooled within-team SD: sum of squares (0+100+100)*2 = 400 over 2*(3-1) = 4 -> 10.
    assert sigma == pytest.approx(10)
    assert strength.tolist() == pytest.approx([3 / 9 * 10, 3 / 9 * -10])
    assert strength_sd.tolist() == pytest.approx([10 / 3, 10 / 3])  # sqrt(100 / (3 + 6))


def test_standings_and_seeding_use_wins_then_points_for():
    team_weeks = pd.DataFrame({
        "week": [1] * 4, "roster_id": [1, 2, 3, 4], "points": [100.0, 90.0, 120.0, 80.0],
        "result": ["W", "L", "W", "T"], "median_result": ["W", "L", "W", "L"], "is_playoff": [False] * 4})
    standings = po.standings_through(team_weeks, 1)
    assert standings["standing"].tolist() == [2.0, 0.0, 2.0, 0.5]  # a tie is half a win
    assert po.seeding(standings) == [3, 1, 4, 2]  # 3 and 1 level on wins: more points for first


def test_ties_at_the_cutoff_are_found():
    standings = pd.DataFrame({"standing": [10.0, 9, 8, 8, 7, 6, 6, 5], "points_for": [1, 1, 5, 5, 1, 2, 2, 1.0]},
                             index=range(1, 9))
    assert po.tied_at_cutoff(standings, 6) == [[3, 4], [6, 7]]  # 6 and 7 straddle the cutoff
    assert po.tied_at_cutoff(standings, 2) == []


def test_before_min_weeks_there_are_no_rows():
    table, _ = odds(random_points(), 2)
    assert table.empty and list(table.columns) == po.PLAYOFF_ODDS_COLUMNS


# --- settings that stop the run --------------------------------------------------------------

@pytest.mark.parametrize("setting, value", [("playoff_teams", 4), ("playoff_seed_type", 1), ("playoff_round_type", 1)])
def test_an_unverified_playoff_format_stops_the_run(setting, value):
    with pytest.raises(ValueError, match=f"{setting} is {value}"):
        odds(random_points(), 5, **{setting: value})


@pytest.mark.parametrize("change, message", [
    ({"simulations": 0}, "simulations"), ({"seed": -1}, "seed"), ({"shrink_weeks": 0}, "shrink_weeks"),
    ({"min_weeks": 1}, "min_weeks"), ({"simulations": 10.5}, "simulations")])
def test_bad_settings_stop_with_a_clear_message(change, message):
    with pytest.raises(ValueError, match=f"metrics.playoff_odds: .*{message}"):
        po.check_params({**PARAMS, **change})


def test_the_config_file_settings_are_valid():
    from sleeper_dash.config import load_config

    po.check_params(load_config().metrics["playoff_odds"])


# --- the validator catches broken tables ------------------------------------------------------

def test_the_validator_catches_broken_odds():
    table, team_weeks = odds(ordered_points(), 12)
    league = make_league()
    shifted = table.copy()
    shifted.loc[0, "p_playoffs"] += 0.01
    assert "p_playoffs sums to" in check_playoff_odds(shifted, team_weeks, league).detail
    wrong = table.copy()
    i = wrong.index[wrong["clinched"]][0]
    wrong.loc[i, ["p_playoffs", "p_seed_6"]] = [0.99, wrong.loc[i, "p_seed_6"] - 0.01]
    assert "clinched but playoff odds" in check_playoff_odds(wrong, team_weeks, league).detail
