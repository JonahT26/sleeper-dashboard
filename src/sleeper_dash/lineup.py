"""Optimal lineups: the best score each team could have posted each week, with hindsight.

Run with:  python -m sleeper_dash.lineup   (rebuilds from the saved tables, checks, saves, and reports)

Implements docs/METRICS_SPEC.md section 3. Each team-week is solved exactly as an
assignment problem (starting slots x players) with scipy's linear_sum_assignment,
so the result is provably optimal, unlike a greedy slot-by-slot fill. Pure
functions only: tables in, tables out. Reading and saving files happens in main().
"""

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

# Which player positions may fill each starting slot (Sleeper's rules; METRICS_SPEC.md section 3).
SLOT_ELIGIBILITY = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "K": {"K"},
    "DEF": {"DEF"},
    "FLEX": {"RB", "WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
}
BENCH = "BN"

# Cost of putting a player in a slot he can't fill. Far larger than any possible point
# total, so the solver first fills as many slots as it can (spec: a slot is always filled
# when an eligible player is available, even one with negative points), then maximises points.
INFEASIBLE = 1e6
# Tie-breaks, far below the 0.01-point resolution of Sleeper scores (10 slots x 0.00011
# < 0.01), so they never change optimal points. Between equal-scoring options, prefer the
# player the manager actually started, and then the slot he actually started in.
STARTER_BONUS = 1e-4
SAME_SLOT_BONUS = 1e-5

LINEUPS_OPTIMAL_COLUMNS = [
    "season", "week", "roster_id", "actual_points", "optimal_points", "bench_points_lost", "efficiency",
]
LINEUPS_OPTIMAL_PLAYERS_COLUMNS = [
    "season", "week", "roster_id", "slot_order", "lineup_slot", "player_id", "full_name", "position",
    "points", "is_empty_slot", "was_started",
]


def starting_slots(roster_positions):
    """The league's starting slots in order (every entry except bench). Unknown slot names stop the run."""
    slots = [slot for slot in roster_positions if slot != BENCH]
    unknown = sorted(set(slots) - set(SLOT_ELIGIBILITY))
    if unknown:
        raise ValueError(
            f"Unknown lineup slot(s) {unknown}: add their eligible positions to SLOT_ELIGIBILITY "
            "in lineup.py and to docs/METRICS_SPEC.md section 3."
        )
    return slots


def eligible_positions(player_ids, players):
    """Map each player ID to the positions he may play: fantasy_positions from the players cache.

    Falls back to the primary position when fantasy_positions is empty. A player with
    neither stops the run, because silently leaving him out would understate optimal points.
    """
    result, missing = {}, []
    for player_id in player_ids:
        info = players.get(player_id) or {}
        positions = info.get("fantasy_positions") or ([info["position"]] if info.get("position") else [])
        if positions:
            result[player_id] = frozenset(positions)
        else:
            missing.append(player_id)
    if missing:
        raise ValueError(f"No position information in the players cache for player(s) {sorted(missing)}.")
    return result


def solve_lineup(slots, points, positions, started_in=None):
    """Return, for each slot, the index of the player filling it in the optimal lineup.

    slots: starting slot names in order. points: each player's points. positions: each
    player's eligible positions. started_in: for each player, the index of the slot he
    actually started in, or None for bench. A slot is None only when no eligible player
    is left for it.
    """
    n_slots, n_players = len(slots), len(points)
    if n_players == 0:
        return [None] * n_slots
    started_in = started_in if started_in is not None else [None] * n_players

    eligible = np.array([[bool(SLOT_ELIGIBILITY[slot] & set(pos)) for pos in positions] for slot in slots])
    value = np.tile(np.asarray(points, dtype=float), (n_slots, 1))
    for player, slot in enumerate(started_in):
        if slot is not None:
            value[:, player] += STARTER_BONUS
            value[slot, player] += SAME_SLOT_BONUS

    rows, cols = linear_sum_assignment(np.where(eligible, -value, INFEASIBLE))
    chosen = [None] * n_slots
    for slot, player in zip(rows, cols):
        if eligible[slot, player]:
            chosen[slot] = int(player)
    return chosen


def build_optimal_lineups(player_weeks, team_weeks, roster_positions, positions_by_player):
    """Solve every team-week. Returns (lineups_optimal, lineups_optimal_players).

    The player pool is every non-empty row of player_weeks for the team-week: starters,
    bench, and injured reserve (Phase 1 decision). positions_by_player maps player_id
    to eligible positions (see eligible_positions).
    """
    slots = starting_slots(roster_positions)
    summary_rows, player_rows = [], []

    for (season, week, roster_id), group in player_weeks.groupby(["season", "week", "roster_id"], sort=True):
        pool = group[~group["is_empty_slot"]].reset_index(drop=True)
        started_in = [int(o) if s else None for o, s in zip(pool["slot_order"], pool["is_starter"])]
        chosen = solve_lineup(
            slots,
            pool["points"].tolist(),
            [positions_by_player[pid] for pid in pool["player_id"]],
            started_in,
        )

        total = 0.0
        for order, (slot, player) in enumerate(zip(slots, chosen)):
            row = {"season": season, "week": week, "roster_id": roster_id, "slot_order": order, "lineup_slot": slot}
            if player is None:
                row.update(player_id=None, full_name=None, position=None, points=0.0, is_empty_slot=True, was_started=False)
            else:
                p = pool.loc[player]
                row.update(player_id=p["player_id"], full_name=p["full_name"], position=p["position"],
                           points=float(p["points"]), is_empty_slot=False, was_started=bool(p["is_starter"]))
                total += float(p["points"])
            player_rows.append(row)
        summary_rows.append({"season": season, "week": week, "roster_id": roster_id, "optimal_points": round(total, 2)})

    lineups = pd.DataFrame(summary_rows, columns=["season", "week", "roster_id", "optimal_points"])
    actual = team_weeks[["season", "week", "roster_id", "points"]].rename(columns={"points": "actual_points"})
    lineups = lineups.merge(actual, on=["season", "week", "roster_id"], how="left", validate="one_to_one")
    if lineups["actual_points"].isna().any():
        missing = lineups.loc[lineups["actual_points"].isna(), ["week", "roster_id"]].values.tolist()
        raise ValueError(f"No team_weeks score for (week, roster_id) {missing}.")
    lineups["bench_points_lost"] = (lineups["optimal_points"] - lineups["actual_points"]).round(2)
    positive = lineups["optimal_points"] > 0
    lineups["efficiency"] = (lineups["actual_points"] / lineups["optimal_points"]).where(positive).round(4)
    lineups = lineups[LINEUPS_OPTIMAL_COLUMNS].astype(
        {"season": "int64", "week": "int64", "roster_id": "int64", "actual_points": "float64",
         "optimal_points": "float64", "bench_points_lost": "float64", "efficiency": "float64"}
    )

    players = pd.DataFrame(player_rows, columns=LINEUPS_OPTIMAL_PLAYERS_COLUMNS).astype(
        {"season": "int64", "week": "int64", "roster_id": "int64", "slot_order": "int64", "lineup_slot": "string",
         "player_id": "string", "full_name": "string", "position": "string", "points": "float64",
         "is_empty_slot": "bool", "was_started": "bool"}
    )
    return lineups.reset_index(drop=True), players


def build_lineup_tables(tables, league, players):
    """Add-on for the pipeline: {lineups_optimal, lineups_optimal_players} from the tidy tables and players cache."""
    player_weeks = tables["player_weeks"]
    ids = player_weeks.loc[~player_weeks["is_empty_slot"], "player_id"].unique()
    lineups, chosen = build_optimal_lineups(
        player_weeks, tables["team_weeks"], league["roster_positions"], eligible_positions(ids, players)
    )
    return {"lineups_optimal": lineups, "lineups_optimal_players": chosen}


def compare_to_sleeper_max(lineups, team_weeks, rosters, warn_gap):
    """Soft check: each team's regular-season optimal points vs Sleeper's max possible points (ppts).

    Returns one row per team. warning is set when ours is below Sleeper's figure, or above
    it by more than warn_gap points. A warning is printed, never a failure.
    """
    regular = lineups.merge(team_weeks[["season", "week", "roster_id", "is_playoff"]], on=["season", "week", "roster_id"])
    ours = regular[~regular["is_playoff"].astype(bool)].groupby("roster_id")["optimal_points"].sum()
    sleeper = {r["roster_id"]: r["settings"].get("ppts", 0) + r["settings"].get("ppts_decimal", 0) / 100 for r in rosters}
    table = pd.DataFrame({"optimal_points": ours.round(2), "sleeper_ppts": pd.Series(sleeper)}).rename_axis("roster_id")
    table["gap"] = (table["optimal_points"] - table["sleeper_ppts"]).round(2)

    def warning(gap):
        if gap < -0.005:
            return f"below Sleeper's max points by {-gap:.2f}"
        if gap > warn_gap:
            return f"above Sleeper's max points by {gap:.2f} (more than {warn_gap})"
        return None

    table["warning"] = table["gap"].map(warning)
    return table.reset_index()


def main():
    from sleeper_dash.config import PROJECT_ROOT, load_config
    from sleeper_dash.transform import read_players, read_raw, save_tables
    from sleeper_dash.validate import BASE_TABLES, ValidationError, load_tables, validate

    config = load_config()
    league, rosters = read_raw(config.season, "league.json"), read_raw(config.season, "rosters.json")
    tables = load_tables(names=BASE_TABLES)
    lineup_tables = build_lineup_tables(tables, league, read_players())
    try:
        validate({**tables, **lineup_tables}, league, rosters)
    except ValidationError as error:
        raise SystemExit(str(error))
    for name, path in save_tables(lineup_tables).items():
        print(f"Saved {len(lineup_tables[name])} rows to {path.relative_to(PROJECT_ROOT).as_posix()}")

    names = tables["teams"].set_index("roster_id")["team_name"]
    lineups, chosen = lineup_tables["lineups_optimal"], lineup_tables["lineups_optimal_players"]
    _report_latest_week(lineups, chosen, tables["player_weeks"], names)
    _report_season(lineups, names)
    _report_sleeper_check(lineups, tables["team_weeks"], rosters, names, config.metrics["efficiency"]["ppts_warn_gap"])


def _report_latest_week(lineups, chosen, player_weeks, names):
    week = int(lineups["week"].max())
    latest = lineups[lineups["week"] == week].copy()
    latest.insert(0, "team_name", latest["roster_id"].map(names))
    latest["efficiency"] = (latest["efficiency"] * 100).round(1)

    # The single costliest decision per team: the best player the optimal lineup used but the manager benched.
    benched = chosen[(chosen["week"] == week) & ~chosen["was_started"] & ~chosen["is_empty_slot"]]
    top_benched = benched.sort_values("points", ascending=False).drop_duplicates("roster_id").set_index("roster_id")
    latest["best_benched_player"] = latest["roster_id"].map(
        lambda r: f"{top_benched.at[r, 'full_name']} ({top_benched.at[r, 'points']:.1f})" if r in top_benched.index else "—"
    )
    latest = latest.sort_values("efficiency", ascending=False)

    print(f"\nWEEK {week}: ACTUAL VS OPTIMAL (sorted by efficiency)")
    columns = ["team_name", "actual_points", "optimal_points", "bench_points_lost", "efficiency", "best_benched_player"]
    print(latest[columns].rename(columns={"efficiency": "efficiency_%"}).to_string(index=False))
    print(f"\n  League: {latest['actual_points'].sum():.2f} actual of {latest['optimal_points'].sum():.2f} optimal "
          f"({100 * latest['actual_points'].sum() / latest['optimal_points'].sum():.1f}%); "
          f"perfect lineups: {int((latest['bench_points_lost'] == 0).sum())}; "
          f"bench points lost: median {latest['bench_points_lost'].median():.1f}, max {latest['bench_points_lost'].max():.1f}")


def _report_season(lineups, names):
    season = lineups.groupby("roster_id")[["actual_points", "optimal_points", "bench_points_lost"]].sum().round(2)
    season["efficiency_%"] = (100 * season["actual_points"] / season["optimal_points"]).round(1)
    season.insert(0, "team_name", season.index.map(names))
    weeks = sorted(int(w) for w in lineups["week"].unique())
    print(f"\nSEASON TO DATE, weeks {weeks[0]}–{weeks[-1]} (efficiency = total actual / total optimal)")
    print(season.sort_values("efficiency_%", ascending=False).to_string(index=False))
    weekly = lineups["efficiency"] * 100
    print(f"\n  Weekly efficiency across all {len(lineups)} team-weeks: min {weekly.min():.1f}%, "
          f"median {weekly.median():.1f}%, max {weekly.max():.1f}%")


def _report_sleeper_check(lineups, team_weeks, rosters, names, warn_gap):
    check = compare_to_sleeper_max(lineups, team_weeks, rosters, warn_gap)
    check.insert(1, "team_name", check["roster_id"].map(names))
    print(f"\nSOFT CHECK: regular-season optimal points vs Sleeper's max points (warn below, or above by > {warn_gap})")
    print(check.drop(columns="roster_id").fillna({"warning": "ok"}).to_string(index=False))
    print(f"\n  Warnings: {int(check['warning'].notna().sum())} of {len(check)} teams")


if __name__ == "__main__":
    main()
