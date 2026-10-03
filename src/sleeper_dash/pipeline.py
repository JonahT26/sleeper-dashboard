"""Full refresh: extract -> transform -> optimal lineups -> metrics -> validate.

Run with:  python -m sleeper_dash.pipeline

Every run re-downloads the whole season and rebuilds every table, so Sleeper stat
corrections flow through. Tables are checked before they are saved, and the saved
CSVs are checked again after saving. Exits with code 1 if anything fails, leaving
the last good tables in data/processed/.
"""

import sys
import time

from sleeper_dash import extract, lineup, transform, validate
from sleeper_dash.api import SleeperAPIError
from sleeper_dash.config import load_config
from sleeper_dash import metrics


def run():
    """Run every step and return a summary dict. Raises on any failure."""
    started = time.perf_counter()
    config = load_config()

    extracted = extract.extract(config)

    tables, league, rosters, _ = transform.build_tables(config.season)
    tables.update(lineup.build_lineup_tables(tables, league, transform.read_players()))
    tables.update(metrics.build_metric_tables(tables, config.metrics))
    validate.validate(tables, league, rosters)  # before saving: failures never overwrite good tables
    transform.save_tables(tables)

    saved = validate.load_tables()
    results = validate.validate(saved, league, rosters)  # after saving: the CSVs themselves pass

    weeks = sorted(int(w) for w in saved["team_weeks"]["week"].unique())
    sleeper_check = lineup.compare_to_sleeper_max(
        saved["lineups_optimal"], saved["team_weeks"], rosters, config.metrics["efficiency"]["ppts_warn_gap"]
    )
    return {
        "season": config.season,
        "weeks": weeks,
        "api_calls": extracted["calls"],
        "rows": {name: len(table) for name, table in saved.items()},
        "checks_passed": sum(r.passed for r in results),
        "checks_total": len(results),
        "warnings": [f"roster {r.roster_id}: optimal points {r.warning}" for r in sleeper_check.dropna(subset=["warning"]).itertuples()],
        "seconds": time.perf_counter() - started,
    }


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
    print(f"  API calls:  {summary['api_calls']}")
    for name, rows in summary["rows"].items():
        print(f"  {name + ':':<25}{rows:>5} rows")
    print(f"  Checks:     {summary['checks_passed']} of {summary['checks_total']} passed")
    warnings = summary.get("warnings", [])
    print(f"  Warnings:   {len(warnings)} (soft checks; they never stop the run)")
    for warning in warnings:
        print(f"    - {warning}")
    print(f"  Run time:   {summary['seconds']:.1f}s")


if __name__ == "__main__":
    main()
