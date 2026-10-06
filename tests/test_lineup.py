"""Tests for the optimal lineup solver (METRICS_SPEC.md section 3). All data is hand-built."""

import itertools
import math
import random

import pandas as pd
import pytest

from sleeper_dash.lineup import (
    EFFICIENCY_SEASON_COLUMNS,
    LINEUPS_OPTIMAL_COLUMNS,
    LINEUPS_OPTIMAL_PLAYERS_COLUMNS,
    SLOT_ELIGIBILITY,
    build_optimal_lineups,
    compare_to_sleeper_max,
    efficiency_season,
    eligible_positions,
    sleeper_fill,
    solve_lineup,
    starting_slots,
)
from sleeper_dash.validate import check_optimal_lineups, check_season_efficiency

ROSTER_POSITIONS = ["QB", "RB", "RB", "WR", "WR", "FLEX", "REC_FLEX", "SUPER_FLEX", "K", "DEF"] + ["BN"] * 6
SLOTS = starting_slots(ROSTER_POSITIONS)


def team_week(starters, bench, week=1, roster_id=1):
    """player_weeks and team_weeks rows for one team-week, plus each player's eligible positions.

    starters: one (player_id, positions, points) per slot in SLOTS, or None for an empty slot.
    bench: (player_id, positions, points) for every bench and injured-reserve player.
    positions is a string like "WR" or "QB/TE".
    """
    assert len(starters) == len(SLOTS)
    rows, eligibility = [], {}
    base = {"season": 2026, "week": week, "roster_id": roster_id}
    for order, (slot, player) in enumerate(zip(SLOTS, starters)):
        if player is None:
            rows.append({**base, "slot_order": order, "lineup_slot": slot, "player_id": "0", "is_starter": True,
                         "is_empty_slot": True, "points": 0.0, "position": None, "full_name": None})
        else:
            pid, positions, points = player
            rows.append({**base, "slot_order": order, "lineup_slot": slot, "player_id": pid, "is_starter": True,
                         "is_empty_slot": False, "points": points, "position": positions.split("/")[0], "full_name": pid})
            eligibility[pid] = frozenset(positions.split("/"))
    for order, (pid, positions, points) in enumerate(bench, start=len(SLOTS)):
        rows.append({**base, "slot_order": order, "lineup_slot": "BN", "player_id": pid, "is_starter": False,
                     "is_empty_slot": False, "points": points, "position": positions.split("/")[0], "full_name": pid})
        eligibility[pid] = frozenset(positions.split("/"))
    player_weeks = pd.DataFrame(rows)
    actual = round(sum(p[2] for p in starters if p is not None), 2)
    team_weeks = pd.DataFrame([{**base, "points": actual, "is_playoff": False}])
    return player_weeks, team_weeks, eligibility


def solve(starters, bench):
    player_weeks, team_weeks, eligibility = team_week(starters, bench)
    lineups, chosen = build_optimal_lineups(player_weeks, team_weeks, ROSTER_POSITIONS, eligibility)
    return lineups.iloc[0], chosen.set_index("lineup_slot", append=True)


# A lineup whose greedy fill goes wrong: filling slots in order, FLEX grabs the best
# remaining flex player (WR3), leaving REC_FLEX (WR/TE only) with a 2-point TE.
# The optimum puts RB3 at FLEX and WR3 at REC_FLEX.
TRAP_STARTERS = [
    ("QB1", "QB", 30.0), ("RB1", "RB", 20.0), ("RB2", "RB", 19.0), ("WR1", "WR", 24.0), ("WR2", "WR", 22.0),
    ("WR3", "WR", 19.5), ("TE1", "TE", 2.0), ("QB2", "QB", 25.0), ("K1", "K", 8.0), ("DEF1", "DEF", 5.0),
]
TRAP_BENCH = [("RB3", "RB", 18.0), ("WR4", "WR", 1.0)]


def greedy_fill(slots, points, positions):
    """Fill slots in order with the best remaining eligible player: the approach the solver must beat."""
    used, total = set(), 0.0
    for slot in slots:
        options = [i for i in range(len(points)) if i not in used and SLOT_ELIGIBILITY[slot] & positions[i]]
        if options:
            best = max(options, key=lambda i: points[i])
            used.add(best)
            total += points[best]
    return total


def test_flex_trap_beats_greedy_fill():
    lineup, chosen = solve(TRAP_STARTERS, TRAP_BENCH)
    assert lineup["actual_points"] == 174.5
    assert lineup["optimal_points"] == 190.5
    assert lineup["bench_points_lost"] == 16.0
    assert lineup["efficiency"] == round(174.5 / 190.5, 4)

    by_slot = chosen.droplevel(0)
    assert by_slot.loc["FLEX", "player_id"] == "RB3"
    assert by_slot.loc["REC_FLEX", "player_id"] == "WR3"
    assert by_slot.loc["SUPER_FLEX", "player_id"] == "QB2"
    assert "TE1" not in set(chosen["player_id"])

    everyone = TRAP_STARTERS + TRAP_BENCH
    points, positions = [p[2] for p in everyone], [frozenset(p[1].split("/")) for p in everyone]
    greedy = greedy_fill(SLOTS, points, positions)
    assert greedy == 174.5 < lineup["optimal_points"]
    # Sleeper's own fill (the method behind its max points) makes the same mistake
    picks = sleeper_fill(SLOTS, points, positions)
    assert [everyone[i][0] for i in picks] == ["QB1", "RB1", "RB2", "WR1", "WR2", "WR3", "TE1", "QB2", "K1", "DEF1"]
    assert sum(points[i] for i in picks) == greedy


def test_dual_position_player_fills_rec_flex_through_te_eligibility():
    # QBTE can play QB or TE. Best: QB2 at SUPER_FLEX and QBTE at REC_FLEX (15 + 12),
    # not QBTE at SUPER_FLEX and WR3 at REC_FLEX (12 + 5).
    slots = ["QB", "WR", "WR", "REC_FLEX", "SUPER_FLEX"]
    names = ["QB1", "QB2", "QBTE", "WR1", "WR2", "WR3"]
    points = [20.0, 15.0, 12.0, 10.0, 9.0, 5.0]
    positions = [{"QB"}, {"QB"}, {"QB", "TE"}, {"WR"}, {"WR"}, {"WR"}]
    chosen = solve_lineup(slots, points, positions)
    assert [names[i] for i in chosen] == ["QB1", "WR1", "WR2", "QBTE", "QB2"]


def brute_force(slots, points, positions):
    """Best (slots filled, points) over every way to assign distinct players to slots, empty slots allowed."""
    best = (0, 0.0)
    for picks in itertools.product([None, *range(len(points))], repeat=len(slots)):
        used = [p for p in picks if p is not None]
        if len(used) != len(set(used)):
            continue
        if any(p is not None and not SLOT_ELIGIBILITY[s] & positions[p] for s, p in zip(slots, picks)):
            continue
        best = max(best, (len(used), round(sum(points[p] for p in used), 2)))
    return best


def test_matches_brute_force_on_random_small_lineups():
    rng = random.Random(2026)
    position_choices = [{"QB"}, {"RB"}, {"WR"}, {"TE"}, {"K"}, {"DEF"}, {"QB", "TE"}, {"RB", "WR"}]
    for _ in range(300):
        slots = rng.choices(sorted(SLOT_ELIGIBILITY), k=rng.randint(1, 4))
        n = rng.randint(0, 6)
        points = [round(rng.uniform(-5, 40), 2) for _ in range(n)]
        positions = [rng.choice(position_choices) for _ in range(n)]
        chosen = solve_lineup(slots, points, positions)
        used = [p for p in chosen if p is not None]
        assert len(used) == len(set(used))
        assert all(p is None or SLOT_ELIGIBILITY[s] & positions[p] for s, p in zip(slots, chosen))
        assert (len(used), round(sum(points[p] for p in used), 2)) == brute_force(slots, points, positions)


def test_already_optimal_lineup_is_100_percent_and_unchanged():
    lineup, chosen = solve(TRAP_STARTERS[:5] + [("RB3", "RB", 18.0), ("WR3", "WR", 19.5)] + TRAP_STARTERS[7:],
                           [("TE1", "TE", 2.0), ("WR4", "WR", 1.0)])
    assert lineup["efficiency"] == 1.0 and lineup["bench_points_lost"] == 0.0
    assert chosen["was_started"].all()
    assert chosen.droplevel(0).loc["FLEX", "player_id"] == "RB3"  # same slots as the manager, not just the same players


def test_equal_points_tie_goes_to_the_player_who_started():
    starters = list(TRAP_STARTERS)
    starters[3] = ("WR1", "WR", 10.0)
    lineup, chosen = solve(starters, TRAP_BENCH + [("WR9", "WR", 10.0)])  # bench WR scored exactly the same as WR1
    assert "WR1" in set(chosen["player_id"]) and "WR9" not in set(chosen["player_id"])


def test_negative_scores_still_fill_the_slot_with_the_least_bad_option():
    starters = list(TRAP_STARTERS)
    starters[9] = ("DEF1", "DEF", -3.0)
    lineup, chosen = solve(starters, TRAP_BENCH + [("DEF2", "DEF", -1.0)])
    defense = chosen.droplevel(0).loc["DEF"]
    assert defense["player_id"] == "DEF2" and not defense["is_empty_slot"]
    assert lineup["optimal_points"] - lineup["actual_points"] == pytest.approx(16.0 + 2.0)


def test_only_negative_option_is_still_used_rather_than_left_empty():
    chosen = solve_lineup(["DEF"], [-4.0], [{"DEF"}])
    assert chosen == [0]


def test_empty_slot_is_penalised_when_an_eligible_player_sat_on_the_bench():
    starters = list(TRAP_STARTERS)
    starters[8] = None  # kicker slot left empty
    lineup, _ = solve(starters, TRAP_BENCH + [("K2", "K", 7.0)])
    assert lineup["actual_points"] == 174.5 - 8.0
    assert lineup["optimal_points"] == 190.5 - 8.0 + 7.0


def test_no_eligible_player_rostered_means_no_penalty_for_that_slot():
    starters = list(TRAP_STARTERS[:5]) + [("RB3", "RB", 18.0), ("WR3", "WR", 19.5)] + list(TRAP_STARTERS[7:])
    starters[8] = None  # no kicker on the roster at all
    lineup, chosen = solve(starters, [("TE1", "TE", 2.0)])
    assert chosen.droplevel(0).loc["K", "is_empty_slot"]
    assert lineup["bench_points_lost"] == 0.0 and lineup["efficiency"] == 1.0


def test_injured_reserve_player_counts_as_bench():
    # The 7th bench row is the IR player; Phase 1 decided IR players are part of the pool.
    bench = [("B1", "RB", 0.0), ("B2", "WR", 0.0), ("B3", "TE", 0.0), ("B4", "QB", 0.0), ("B5", "K", 0.0),
             ("B6", "DEF", 0.0), ("IR1", "WR", 30.0)]
    lineup, chosen = solve(TRAP_STARTERS, bench)
    assert "IR1" in set(chosen["player_id"])


def test_zero_optimal_points_gives_null_efficiency():
    zeros = [(f"P{i}", pos, 0.0) for i, pos in enumerate(["QB", "RB", "RB", "WR", "WR", "RB", "WR", "QB", "K", "DEF"])]
    lineup, _ = solve(zeros, [])
    assert lineup["optimal_points"] == 0.0 and math.isnan(lineup["efficiency"])


def test_output_tables_have_spec_columns_and_one_row_per_slot():
    player_weeks, team_weeks, eligibility = team_week(TRAP_STARTERS, TRAP_BENCH)
    lineups, chosen = build_optimal_lineups(player_weeks, team_weeks, ROSTER_POSITIONS, eligibility)
    assert list(lineups.columns) == LINEUPS_OPTIMAL_COLUMNS and len(lineups) == 1
    assert list(chosen.columns) == LINEUPS_OPTIMAL_PLAYERS_COLUMNS
    assert chosen["slot_order"].tolist() == list(range(len(SLOTS)))
    assert chosen["lineup_slot"].tolist() == SLOTS


def test_unknown_slot_stops_the_run():
    with pytest.raises(ValueError, match="IDP_FLEX"):
        starting_slots(["QB", "IDP_FLEX", "BN"])


def test_eligibility_uses_fantasy_positions_then_primary_position_and_rejects_unknowns():
    players = {"1": {"fantasy_positions": ["QB", "TE"], "position": "QB"}, "2": {"fantasy_positions": None, "position": "WR"}}
    assert eligible_positions(["1", "2"], players) == {"1": {"QB", "TE"}, "2": {"WR"}}
    with pytest.raises(ValueError, match="3"):
        eligible_positions(["3"], players)


def test_validation_flags_inconsistent_lineup_tables():
    player_weeks, team_weeks, eligibility = team_week(TRAP_STARTERS, TRAP_BENCH)
    lineups, chosen = build_optimal_lineups(player_weeks, team_weeks, ROSTER_POSITIONS, eligibility)
    assert check_optimal_lineups(lineups, chosen, team_weeks).passed

    too_low = lineups.assign(optimal_points=100.0)
    assert "below actual" in check_optimal_lineups(too_low, chosen, team_weeks).detail

    reused = chosen.copy()
    reused.loc[1, "player_id"] = reused.loc[0, "player_id"]
    assert "used twice" in check_optimal_lineups(lineups, reused, team_weeks).detail


def sleeper_check_league(ppts_by_roster):
    """Three teams with the FLEX trap lineup in week 1 (Sleeper's method 174.50, best lineup 190.50) and a
    playoff week 2 that must not count; ppts_by_roster gives each roster's Sleeper max points."""
    frames, eligibility = [], {}
    for roster_id in ppts_by_roster:
        for week in (1, 2):
            player_weeks, team_weeks, positions = team_week(TRAP_STARTERS, TRAP_BENCH, week=week, roster_id=roster_id)
            frames.append((player_weeks, team_weeks.assign(is_playoff=week == 2)))
            eligibility.update(positions)
    player_weeks = pd.concat([f[0] for f in frames], ignore_index=True)
    team_weeks = pd.concat([f[1] for f in frames], ignore_index=True)
    lineups, _ = build_optimal_lineups(player_weeks, team_weeks, ROSTER_POSITIONS, eligibility)
    players = {pid: {"fantasy_positions": sorted(pos)} for pid, pos in eligibility.items()}
    rosters = [{"roster_id": r, "settings": {"ppts": int(p), "ppts_decimal": round(p % 1 * 100)}} for r, p in ppts_by_roster.items()]
    return lineups, player_weeks, team_weeks, rosters, players


def test_sleeper_max_points_soft_check_rebuilds_sleepers_method_to_the_cent():
    lineups, player_weeks, team_weeks, rosters, players = sleeper_check_league({1: 174.50, 2: 174.49, 3: 180.00})
    check = compare_to_sleeper_max(lineups, player_weeks, team_weeks, rosters, ROSTER_POSITIONS, players).set_index("roster_id")
    assert (check["sleeper_method_points"] == 174.5).all()      # regular season only: the playoff week 2 isn't counted
    assert (check["optimal_points"] == 190.5).all()
    assert pd.isna(check.loc[1, "warning"])                      # exact match
    assert check.loc[1, "optimal_above_ppts"] == 16.0            # the best lineup beating Sleeper's figure never warns
    assert check.loc[2, "gap"] == 0.01 and "0.01 above" in check.loc[2, "warning"]   # one cent is enough
    assert check.loc[3, "gap"] == -5.5 and "5.50 below" in check.loc[3, "warning"]


def test_sleeper_fill_uses_week_positions_so_a_position_change_shows_up():
    # The Taysom Hill pattern (2024): listed QB/TE, a 30-point player is taken at QB by Sleeper's fill, leaving
    # REC_FLEX a 5-point WR; listed TE only, he goes to REC_FLEX and the real QB plays. The totals differ by 15,
    # which is how the check exposes a player whose position Sleeper lists differently from the players cache.
    slots = ["QB", "REC_FLEX"]
    points = [30.0, 20.0, 5.0]
    as_qb_te = [{"QB", "TE"}, {"QB"}, {"WR"}]
    as_te = [{"TE"}, {"QB"}, {"WR"}]
    assert sleeper_fill(slots, points, as_qb_te) == [0, 2]          # 30 + 5 = 35
    assert sleeper_fill(slots, points, as_te) == [1, 0]             # 20 + 30 = 50
    assert [solve_lineup(slots, points, as_qb_te)[i] for i in range(2)] == [1, 0]   # the best lineup isn't fooled
    assert sleeper_fill(["K"], points, as_te) == [None]             # no eligible player: slot left empty


@pytest.mark.parametrize("name", ["lineups_optimal", "lineups_optimal_players"])
def test_duplicate_lineup_keys_fail_validation(name):
    from sleeper_dash.validate import check_unique_keys

    player_weeks, team_weeks, eligibility = team_week(TRAP_STARTERS, TRAP_BENCH)
    lineups, chosen = build_optimal_lineups(player_weeks, team_weeks, ROSTER_POSITIONS, eligibility)
    tables = {"lineups_optimal": lineups, "lineups_optimal_players": chosen}
    tables[name] = pd.concat([tables[name], tables[name].iloc[[0]]])
    result = check_unique_keys(tables)
    assert not result.passed and result.detail.startswith(name)


def weekly_lineups(rows):
    """lineups_optimal rows from (week, roster_id, actual, optimal) tuples."""
    table = pd.DataFrame(rows, columns=["week", "roster_id", "actual_points", "optimal_points"]).assign(season=2026)
    table["bench_points_lost"] = (table["optimal_points"] - table["actual_points"]).round(2)
    table["efficiency"] = (table["actual_points"] / table["optimal_points"]).where(table["optimal_points"] > 0).round(4)
    return table[LINEUPS_OPTIMAL_COLUMNS]


# Team 1: 90 of 100, then 150 of 200. Team 2: perfect both weeks.
TWO_WEEKS = weekly_lineups([(1, 1, 90.0, 100.0), (1, 2, 120.0, 120.0), (2, 1, 150.0, 200.0), (2, 2, 80.0, 80.0)])


def test_season_efficiency_is_total_actual_over_total_optimal_not_the_mean_of_weekly_ratios():
    season = efficiency_season(TWO_WEEKS).set_index(["through_week", "roster_id"])
    assert season.loc[(1, 1), "efficiency"] == 0.9
    assert season.loc[(2, 1), "efficiency"] == 0.8          # 240 / 300; the mean of 90% and 75% would be 82.5%
    assert season.loc[(1, 1), "bench_points_lost"] == 10.0
    assert season.loc[(2, 1), "bench_points_lost"] == 60.0
    assert season.loc[(2, 2), "efficiency"] == 1.0 and season.loc[(2, 2), "bench_points_lost"] == 0.0


def test_season_efficiency_has_one_row_per_team_per_week_and_spec_columns():
    season = efficiency_season(TWO_WEEKS)
    assert list(season.columns) == EFFICIENCY_SEASON_COLUMNS
    assert season[["through_week", "roster_id"]].values.tolist() == [[1, 1], [1, 2], [2, 1], [2, 2]]


def test_season_efficiency_is_null_only_without_optimal_points():
    season = efficiency_season(weekly_lineups([(1, 1, 0.0, 0.0), (2, 1, 50.0, 100.0)])).set_index("through_week")
    assert math.isnan(season.loc[1, "efficiency"])
    assert season.loc[2, "efficiency"] == 0.5


def test_season_efficiency_counts_playoff_weeks():
    season = efficiency_season(weekly_lineups([(14, 1, 100.0, 100.0), (15, 1, 50.0, 100.0)])).set_index("through_week")
    assert season.loc[15, "efficiency"] == 0.75


@pytest.mark.parametrize("seed", range(5))
def test_season_efficiency_lies_between_the_best_and_worst_week(seed):
    rng = random.Random(seed)
    rows = []
    for week in range(1, 18):
        for roster_id in range(1, 13):
            optimal = round(rng.uniform(80, 200), 2)
            rows.append((week, roster_id, round(optimal - rng.uniform(0, 50), 2), optimal))
    lineups = weekly_lineups(rows)
    season = efficiency_season(lineups)
    assert check_season_efficiency(season, lineups).passed
    for r in season.itertuples():
        weeks = lineups[(lineups["roster_id"] == r.roster_id) & (lineups["week"] <= r.through_week)]["efficiency"]
        assert weeks.min() - 0.0001 <= r.efficiency <= weeks.max() + 0.0001


def test_validation_flags_wrong_season_efficiency():
    season = efficiency_season(TWO_WEEKS)
    assert check_season_efficiency(season, TWO_WEEKS).passed

    mean_of_ratios = season.copy()
    mean_of_ratios.loc[(season["through_week"] == 2) & (season["roster_id"] == 1), "efficiency"] = 0.825
    assert "total actual / total optimal 0.8000" in check_season_efficiency(mean_of_ratios, TWO_WEEKS).detail

    bench = season.assign(bench_points_lost=season["bench_points_lost"] + 1)
    assert "points left on the bench" in check_season_efficiency(bench, TWO_WEEKS).detail

    missing = season.iloc[1:]
    assert "missing from metrics_season" in check_season_efficiency(missing, TWO_WEEKS).detail

    blank = season.assign(efficiency=float("nan"))
    assert not check_season_efficiency(blank, TWO_WEEKS).passed
