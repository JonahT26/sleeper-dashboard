"""Full refresh: extract -> transform -> data checks -> metrics -> metric checks -> save.

Run with:  python -m sleeper_dash.pipeline

Every run re-downloads the whole season and rebuilds every table, so Sleeper stat
corrections flow through. Steps, in order:

1. extract       raw Sleeper JSON into data/raw/{season}/
2. transform     tidy tables (teams, team_weeks, player_weeks, transactions, schedule)
3. data checks   reconciliation with Sleeper and integrity; any failure stops the run
4. metrics       optimal lineups, then every metric table (docs/METRICS_SPEC.md)
5. metric checks the spec's invariants (luck sums to 0, power mean 50, ...); any failure stops the run
6. save          every table to data/processed/, then re-read and re-check all of them

Nothing is saved unless steps 3 and 5 pass, so a failed run leaves the last good tables
in data/processed/. Exits with code 1 on any failure.

A successful run also writes data/cache/pipeline_run.json (gitignored): when it finished,
the league name, season, weeks, and the league facts the "How this works" copy quotes (number
of teams, whether there's a median game, playoff start). The dashboard reads it.

When there is no new completed week, the run is the same full refresh and succeeds. If Sleeper's
data hasn't changed either, every saved table comes out byte-identical; only a stat correction
to a past week changes numbers. The summary says which: whether the latest completed week moved
since the tables already in data/processed/, and which tables changed.
"""

import hashlib
import json
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from sleeper_dash import extract, lineup, metrics, transform, validate
from sleeper_dash.api import SleeperAPIError
from sleeper_dash.config import PROJECT_ROOT, load_config

RUN_RECORD_PATH = PROJECT_ROOT / "data" / "cache" / "pipeline_run.json"


def league_facts(league):
    """The league settings the dashboard's copy quotes, from Sleeper's league.json (None if they're missing)."""
    settings = league.get("settings") or {}
    if "num_teams" not in settings or "playoff_week_start" not in settings:
        return None
    return {"teams": int(settings["num_teams"]), "median_game": bool(settings.get("league_average_match")),
            "playoff_week_start": int(settings["playoff_week_start"])}


def write_run_record(league, season, weeks, path=None):
    """Record a successful run for the dashboard. Kept out of data/processed/ so the tables stay byte-identical across runs."""
    path = path or RUN_RECORD_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "league_name": league.get("name"), "season": season, "weeks": weeks, "league": league_facts(league)}
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def saved_snapshot(season, names):
    """What data/processed/ holds right now: {table: SHA-256 of its CSV} and the latest week saved for this season.

    Read before and after saving, so a run can say whether anything changed. It compares with the
    saved tables (committed to git) rather than an earlier run record, so it works on a fresh
    GitHub Actions machine too.
    """
    folder = transform.PROCESSED_DIR
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
              for name in names if (path := folder / f"{name}.csv").exists()}
    latest_week = None
    if (folder / "team_weeks.csv").exists():
        saved = pd.read_csv(folder / "team_weeks.csv", usecols=["season", "week"], encoding="utf-8-sig")
        weeks = saved.loc[saved["season"] == season, "week"]
        latest_week = int(weeks.max()) if len(weeks) else None
    return hashes, latest_week


def run():
    """Run every step and return a summary dict. Raises on any failure."""
    started = time.perf_counter()
    config = load_config()

    extracted = extract.extract(config)

    tables, league, rosters, _ = transform.build_tables(config.season, config.season_start_date)
    data_results = validate.validate(tables, league, rosters, validate.run_data_checks, "Data checks")

    tables.update(lineup.build_lineup_tables(tables, league, transform.read_players()))
    tables.update(metrics.build_metric_tables(tables, config.metrics))
    metric_results = validate.validate(tables, league, rosters, validate.run_metric_checks, "Metric checks")

    before, previous_week = saved_snapshot(config.season, tables)
    transform.save_tables(tables)
    after, _ = saved_snapshot(config.season, tables)
    saved = validate.load_tables()
    saved_results = validate.validate(saved, league, rosters, stage="Saved-file checks")  # the CSVs themselves pass

    weeks = sorted(int(w) for w in saved["team_weeks"]["week"].unique())
    write_run_record(league, config.season, weeks)
    sleeper_check = lineup.compare_to_sleeper_max(
        saved["lineups_optimal"], saved["team_weeks"], rosters, config.metrics["efficiency"]["ppts_warn_gap"]
    )
    return {
        "season": config.season,
        "weeks": weeks,
        "previous_week": previous_week,  # latest week in data/processed/ before this run; None if none for this season
        "changed_tables": None if not before else [name for name in tables if before.get(name) != after.get(name)],
        "api_calls": extracted["calls"],
        "rows": {name: len(table) for name, table in saved.items()},
        "data_checks": [(r.name, r.passed, r.detail) for r in data_results],
        "metric_checks": [(r.name, r.passed, r.detail) for r in metric_results],
        "saved_checks": (sum(r.passed for r in saved_results), len(saved_results)),
        "warnings": [f"roster {r.roster_id}: optimal points {r.warning}" for r in sleeper_check.dropna(subset=["warning"]).itertuples()],
        "seconds": time.perf_counter() - started,
    }


def _week_change(latest, previous):
    if latest is None:
        return "none yet"
    if previous is None:
        return f"{latest} (no saved tables for this season before this run)"
    if latest == previous:
        return f"{latest} (no new completed week since the last run)"
    if latest > previous:
        return f"{latest} (new: the last run ended at week {previous})"
    return f"{latest} (fewer weeks than the last run, which ended at week {previous})"


def _table_change(changed, total):
    if changed is None:
        return "first save"
    if not changed:
        return "unchanged (every file identical)"
    return f"{len(changed)} of {total} changed: {', '.join(changed)}"


def _check_lines(checks):
    width = max(len(name) for name, _, _ in checks)
    return [f"    {'PASS' if passed else 'FAIL'}  {name:<{width}}  {detail}" for name, passed, detail in checks]


def main():
    try:
        summary = run()
    except validate.ValidationError as error:
        print(f"PIPELINE FAILED: validation\n\n{error}", file=sys.stderr)
        sys.exit(1)
    except (extract.ExtractError, SleeperAPIError, FileNotFoundError, ValueError) as error:
        print(f"PIPELINE FAILED: {error}", file=sys.stderr)
        sys.exit(1)

    weeks = summary["weeks"]
    week_text = f"{weeks[0]}–{weeks[-1]}" if weeks else "none completed yet"
    print(f"Pipeline complete: season {summary['season']}, weeks {week_text}")
    print(f"  Latest completed week:  {_week_change(weeks[-1] if weeks else None, summary['previous_week'])}")
    print(f"  Tables vs the last run: {_table_change(summary['changed_tables'], len(summary['rows']))}")
    print(f"  API calls:  {summary['api_calls']}")
    print("  Tables saved:")
    for name, rows in summary["rows"].items():
        print(f"    {name + ':':<25}{rows:>5} rows")
    for label, key in (("Data checks", "data_checks"), ("Metric checks", "metric_checks")):
        checks = summary[key]
        print(f"  {label}:  {sum(passed for _, passed, _ in checks)} of {len(checks)} passed")
        print("\n".join(_check_lines(checks)))
    passed, total = summary["saved_checks"]
    print(f"  Saved files re-checked:  {passed} of {total} checks passed after re-reading the CSVs")
    warnings = summary.get("warnings", [])
    print(f"  Warnings:   {len(warnings)} (soft checks; they never stop the run)")
    for warning in warnings:
        print(f"    - {warning}")
    print(f"  Run time:   {summary['seconds']:.1f}s")


if __name__ == "__main__":
    main()
