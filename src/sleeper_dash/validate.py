"""Integrity and reconciliation checks on the tidy tables.

Run with:  python -m sleeper_dash.validate   (checks the saved CSVs in data/processed/)

transform runs the same checks on its tables before saving them, so tables that
fail never overwrite the ones in data/processed/.
"""

import sys
from dataclasses import dataclass

import pandas as pd

TOLERANCE = 0.01  # points

KEYS = {
    "teams": ["season", "roster_id"],
    "team_weeks": ["season", "week", "roster_id"],
    "player_weeks": ["season", "week", "roster_id", "slot_order"],
    "transactions": ["transaction_id", "player_id", "action"],
    "lineups_optimal": ["season", "week", "roster_id"],
    "lineups_optimal_players": ["season", "week", "roster_id", "slot_order"],
    "metrics_team_weeks": ["season", "week", "roster_id"],
    "metrics_season": ["season", "through_week", "roster_id"],
}
LUCK_TOLERANCE = 1e-6  # wins
BASE_TABLES = ["teams", "team_weeks", "player_weeks", "transactions"]  # built by transform; the rest by lineup


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


class ValidationError(Exception):
    """One or more checks failed; the message lists every failure."""


def _result(name, problems, ok_detail):
    return CheckResult(name, not problems, "; ".join(problems) if problems else ok_detail)


def check_team_rows_per_week(team_weeks, league):
    """Every completed week, from the league's start week on, has one row per team."""
    expected = league["settings"]["num_teams"]
    counts = team_weeks.groupby("week").size()
    if counts.empty:
        return CheckResult("Every week has one row per team", True, "no completed weeks yet")
    problems = [f"week {w}: {n} rows, expected {expected}" for w, n in counts.items() if n != expected]
    start = league["settings"].get("start_week", 1)
    missing = sorted(set(range(start, counts.index.max() + 1)) - set(counts.index))
    if missing:
        problems.append(f"weeks missing entirely: {missing}")
    return _result("Every week has one row per team", problems, f"{len(counts)} weeks x {expected} teams")


def check_matchup_pairs(team_weeks):
    """Every non-null matchup_id appears exactly twice in its week."""
    games = team_weeks.dropna(subset=["matchup_id"]).groupby(["week", "matchup_id"]).size()
    problems = [f"week {w}, matchup {int(m)}: {n} teams" for (w, m), n in games.items() if n != 2]
    return _result("Each matchup has exactly 2 teams", problems, f"{len(games)} matchups checked")


def check_starter_points(player_weeks, team_weeks):
    """Starter points add up to the team's score in every team-week (within TOLERANCE)."""
    starters = player_weeks[player_weeks["is_starter"]]
    sums = starters.groupby(["week", "roster_id"])["points"].sum().rename("starter_points").reset_index()
    merged = team_weeks[["week", "roster_id", "points"]].merge(sums, on=["week", "roster_id"], how="outer")
    problems = []
    for row in merged.itertuples():
        if pd.isna(row.points) or pd.isna(row.starter_points):
            problems.append(f"week {row.week}, roster {row.roster_id}: missing from one of the tables")
        elif abs(row.points - row.starter_points) > TOLERANCE:
            problems.append(f"week {row.week}, roster {row.roster_id}: team {row.points:.2f} vs starters {row.starter_points:.2f}")
    return _result("Starter points equal team points", problems, f"{len(merged)} team-weeks within {TOLERANCE}")


def _sleeper_totals(rosters):
    def total(settings, whole, decimal):
        return settings.get(whole, 0) + settings.get(decimal, 0) / 100

    return {
        r["roster_id"]: {
            "W": r["settings"].get("wins", 0),
            "L": r["settings"].get("losses", 0),
            "T": r["settings"].get("ties", 0),
            "PF": total(r["settings"], "fpts", "fpts_decimal"),
            "PA": total(r["settings"], "fpts_against", "fpts_against_decimal"),
        }
        for r in rosters
    }


def check_records(team_weeks, rosters, league):
    """Regular-season W-L-T matches Sleeper's roster settings, counting median games if the league plays them."""
    regular = team_weeks[~team_weeks["is_playoff"]]
    plays_median = league["settings"].get("league_average_match") == 1
    problems = []
    for roster_id, sleeper in sorted(_sleeper_totals(rosters).items()):
        games = regular[regular["roster_id"] == roster_id]
        ours = {k: int((games["result"] == k).sum()) for k in ("W", "L", "T")}
        if plays_median:
            ours["W"] += int((games["median_result"] == "W").sum())
            ours["L"] += int((games["median_result"] == "L").sum())
        if (ours["W"], ours["L"], ours["T"]) != (sleeper["W"], sleeper["L"], sleeper["T"]):
            problems.append(
                f"roster {roster_id}: ours {ours['W']}–{ours['L']}–{ours['T']}, "
                f"Sleeper {sleeper['W']}–{sleeper['L']}–{sleeper['T']}"
            )
    note = "including median games" if plays_median else "head-to-head"
    return _result("Records match Sleeper", problems, f"{len(rosters)} teams, {note}")


def check_points_for_against(team_weeks, rosters):
    """Regular-season points for and against match Sleeper's fpts and fpts_against (within TOLERANCE)."""
    regular = team_weeks[~team_weeks["is_playoff"]]
    problems = []
    for roster_id, sleeper in sorted(_sleeper_totals(rosters).items()):
        games = regular[regular["roster_id"] == roster_id]
        pf, pa = games["points"].sum(), games["opponent_points"].sum()
        if abs(pf - sleeper["PF"]) > TOLERANCE:
            problems.append(f"roster {roster_id}: points for {pf:.2f} vs Sleeper {sleeper['PF']:.2f}")
        if abs(pa - sleeper["PA"]) > TOLERANCE:
            problems.append(f"roster {roster_id}: points against {pa:.2f} vs Sleeper {sleeper['PA']:.2f}")
    return _result("Points for/against match Sleeper", problems, f"{len(rosters)} teams within {TOLERANCE}")


def check_optimal_lineups(lineups, chosen, team_weeks):
    """Optimal lineups are complete and consistent (METRICS_SPEC.md section 3, sanity checks 1 and 4).

    Every team-week has one, actual points equal the team score, optimal points are at
    least actual points and equal the sum of the chosen players, and no player is used twice.
    """
    key = ["season", "week", "roster_id"]
    merged = team_weeks[key + ["points"]].merge(lineups, on=key, how="outer", indicator="source")
    problems = [f"week {r.week}, roster {r.roster_id}: missing from {'lineups_optimal' if r.source == 'left_only' else 'team_weeks'}"
                for r in merged[merged["source"] != "both"].itertuples()]
    both = merged[merged["source"] == "both"]
    chosen_sum = chosen.groupby(key)["points"].sum().rename("chosen_points").reset_index()
    both = both.merge(chosen_sum, on=key, how="left")
    for r in both.itertuples():
        where = f"week {r.week}, roster {r.roster_id}"
        if abs(r.actual_points - r.points) > TOLERANCE:
            problems.append(f"{where}: actual {r.actual_points:.2f} vs team score {r.points:.2f}")
        if r.optimal_points < r.actual_points - TOLERANCE:
            problems.append(f"{where}: optimal {r.optimal_points:.2f} below actual {r.actual_points:.2f}")
        if pd.isna(r.chosen_points) or abs(r.optimal_points - r.chosen_points) > TOLERANCE:
            problems.append(f"{where}: optimal {r.optimal_points:.2f} vs chosen players' total {r.chosen_points}")
    filled = chosen[~chosen["is_empty_slot"].astype(bool)]
    reused = filled[filled.duplicated(key + ["player_id"])]
    problems += [f"week {r.week}, roster {r.roster_id}: player {r.player_id} used twice" for r in reused.itertuples()]
    return _result("Optimal lineups are consistent", problems, f"{len(both)} team-weeks; optimal >= actual")


def check_allplay_and_luck(weekly, season, team_weeks, rosters):
    """All-play and luck invariants (METRICS_SPEC.md sections 1 and 2).

    Per team-week, all-play W + L + T = teams that week − 1. Per week, the league's
    W + ½T = n(n − 1)/2. In regular-season weeks where every team played, expected wins sum
    to actual wins, so luck sums to 0. Median cross-check: median_result is W exactly when
    all-play wins >= n/2. Season totals for the last week equal the sum of the weekly rows,
    and the season record (head-to-head + median) equals Sleeper's roster wins/losses/ties.
    """
    problems = []
    week_key = ["season", "week"]
    n = weekly.groupby(week_key)["roster_id"].transform("size")
    games = weekly["allplay_wins"] + weekly["allplay_losses"] + weekly["allplay_ties"]
    for r in weekly[games != n - 1].itertuples():
        problems.append(f"week {r.week}, roster {r.roster_id}: all-play W+L+T is not {int(n[r.Index]) - 1}")

    by_week = weekly.assign(credit=weekly["allplay_wins"] + 0.5 * weekly["allplay_ties"], n=n).groupby(week_key)
    for (season_id, week), g in by_week:
        teams = int(g["n"].iloc[0])
        if abs(g["credit"].sum() - teams * (teams - 1) / 2) > LUCK_TOLERANCE:
            problems.append(f"week {week}: league all-play wins {g['credit'].sum()} != {teams * (teams - 1) / 2}")
        if g["actual_wins"].notna().all():
            if abs(g["expected_wins"].sum() - g["actual_wins"].sum()) > LUCK_TOLERANCE or abs(g["luck"].sum()) > LUCK_TOLERANCE:
                problems.append(f"week {week}: expected wins {g['expected_wins'].sum():.6f} vs actual {g['actual_wins'].sum()}; "
                                f"luck sums to {g['luck'].sum():.2e}")

    if "median_result" in team_weeks:
        merged = weekly.assign(n=n).merge(team_weeks[week_key + ["roster_id", "median_result"]], on=week_key + ["roster_id"])
        played = merged[merged["median_result"].notna()]
        mismatch = played[(played["median_result"] == "W") != (played["allplay_wins"] >= played["n"] / 2)]
        problems += [f"week {r.week}, roster {r.roster_id}: median_result {r.median_result} but all-play wins {r.allplay_wins}"
                     for r in mismatch.itertuples()]

    last = season[season["through_week"] == season["through_week"].max()].set_index("roster_id")
    sums = weekly.groupby("roster_id")[["allplay_wins", "actual_wins", "expected_wins", "luck"]].sum()
    for column in sums:
        diff = (last[column] - sums[column]).abs()
        problems += [f"roster {rid}: season {column} differs from the weekly total" for rid in diff[diff > LUCK_TOLERANCE].index]

    # The displayed record (head-to-head + median) must be Sleeper's official record.
    for roster_id, sleeper in sorted(_sleeper_totals(rosters).items()):
        if roster_id not in last.index:
            problems.append(f"roster {roster_id}: missing from metrics_season")
            continue
        ours = tuple(int(last.at[roster_id, c]) for c in ("wins", "losses", "ties"))
        if ours != (sleeper["W"], sleeper["L"], sleeper["T"]):
            problems.append(f"roster {roster_id}: record {'–'.join(map(str, ours))} vs Sleeper {sleeper['W']}–{sleeper['L']}–{sleeper['T']}")
    return _result("All-play and luck are consistent", problems,
                   f"{len(weekly)} team-weeks; luck sums to 0 each week; median cross-check agrees; records match Sleeper")


def check_unique_keys(tables):
    """No table has two rows with the same key."""
    problems = []
    for name, table in tables.items():
        dupes = int(table.duplicated(KEYS[name]).sum())
        if dupes:
            problems.append(f"{name}: {dupes} duplicate key(s) on ({', '.join(KEYS[name])})")
    return _result("No duplicate keys", problems, f"{len(tables)} tables checked")


def run_checks(tables, league, rosters):
    """Run every check. tables maps table name to DataFrame: the BASE_TABLES, plus the lineup tables when present."""
    team_weeks = tables["team_weeks"]
    results = [
        check_team_rows_per_week(team_weeks, league),
        check_matchup_pairs(team_weeks),
        check_starter_points(tables["player_weeks"], team_weeks),
        check_records(team_weeks, rosters, league),
        check_points_for_against(team_weeks, rosters),
    ]
    if "lineups_optimal" in tables:
        results.append(check_optimal_lineups(tables["lineups_optimal"], tables["lineups_optimal_players"], team_weeks))
    if "metrics_team_weeks" in tables:
        results.append(check_allplay_and_luck(tables["metrics_team_weeks"], tables["metrics_season"], team_weeks, rosters))
    results.append(check_unique_keys(tables))
    return results


def format_results(results):
    width = max(len(r.name) for r in results)
    lines = [f"{'Check':<{width}}  Result  Detail"]
    lines += [f"{r.name:<{width}}  {'PASS' if r.passed else 'FAIL':<6}  {r.detail}" for r in results]
    return "\n".join(lines)


def validate(tables, league, rosters):
    """Run every check; raise ValidationError listing all failures. Returns the results when all pass."""
    results = run_checks(tables, league, rosters)
    failed = [r for r in results if not r.passed]
    if failed:
        raise ValidationError(
            f"{len(failed)} validation check(s) failed; nothing was saved or published.\n\n" + format_results(results)
        )
    return results


def load_tables(processed_dir=None, names=None):
    """Read the saved tables back with IDs kept as text. names defaults to every table in KEYS."""
    from sleeper_dash.transform import PROCESSED_DIR

    processed_dir = processed_dir or PROCESSED_DIR
    tables = {}
    for name in names or KEYS:
        path = processed_dir / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing. Run `python -m sleeper_dash.pipeline` first.")
        tables[name] = pd.read_csv(
            path, dtype={"owner_id": str, "player_id": str, "transaction_id": str}, encoding="utf-8-sig"
        )
    return tables


def main():
    from sleeper_dash.config import load_config
    from sleeper_dash.transform import read_raw

    season = load_config().season
    results = run_checks(load_tables(), read_raw(season, "league.json"), read_raw(season, "rosters.json"))
    print(format_results(results))
    failed = sum(not r.passed for r in results)
    print(f"\n{len(results) - failed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
