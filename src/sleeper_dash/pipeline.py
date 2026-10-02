"""Full refresh: extract -> transform -> validate.

Run with:  python -m sleeper_dash.pipeline

Every run re-downloads the whole season and rebuilds every table, so Sleeper stat
corrections flow through. Tables are checked before they are saved, and the saved
CSVs are checked again after saving. Exits with code 1 if anything fails, leaving
the last good tables in data/processed/.
"""

import sys
import time

from sleeper_dash import extract, transform, validate
from sleeper_dash.api import SleeperAPIError
from sleeper_dash.config import load_config


def run():
    """Run every step and return a summary dict. Raises on any failure."""
    started = time.perf_counter()
    config = load_config()

    extracted = extract.extract(config)

    tables, league, rosters, _ = transform.build_tables(config.season)
    validate.validate(tables, league, rosters)  # before saving: failures never overwrite good tables
    transform.save_tables(tables)

    saved = validate.load_tables()
    results = validate.validate(saved, league, rosters)  # after saving: the CSVs themselves pass

    weeks = sorted(int(w) for w in saved["team_weeks"]["week"].unique())
    return {
        "season": config.season,
        "weeks": weeks,
        "api_calls": extracted["calls"],
        "rows": {name: len(table) for name, table in saved.items()},
        "checks_passed": sum(r.passed for r in results),
        "checks_total": len(results),
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
        print(f"  {name + ':':<14}{rows:>5} rows")
    print(f"  Checks:     {summary['checks_passed']} of {summary['checks_total']} passed")
    print(f"  Run time:   {summary['seconds']:.1f}s")


if __name__ == "__main__":
    main()
