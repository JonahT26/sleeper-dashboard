"""Full refresh: extract -> transform -> data checks -> metrics -> metric checks -> save.

Run with:  python -m sleeper_dash.pipeline

Every run re-downloads every configured season (config.yaml season, and past seasons back to
history_from) and rebuilds every table, so Sleeper stat corrections flow through. Steps, in order:

1. extract       raw Sleeper JSON into data/raw/{season}/, one folder per season
2. transform     tidy tables per season (teams, team_weeks, player_weeks, transactions, schedule,
                 winners_bracket), plus managers matched across seasons by owner ID
3. data checks   reconciliation with Sleeper and integrity, for every season against its own league
                 and standings; any failure stops the run
4. metrics       optimal lineups, then every metric table (docs/METRICS_SPEC.md), per season
5. metric checks the spec's invariants (luck sums to 0, power mean 50, ...), per season; any failure stops the run
6. save          every table, seasons stacked by their season column, to data/processed/, then re-read
                 and re-check all of them

Nothing is saved unless steps 3 and 5 pass, so a failed run leaves the last good tables
in data/processed/. Exits with code 1 on any failure.

A successful run also writes data/cache/pipeline_run.json (gitignored): when it finished,
the league name, season, weeks, and the league facts the "How this works" copy quotes (number
of teams, whether there's a median game, playoff start, playoff teams), and whether Sleeper marks the season
complete (for the page's stale-data line). The dashboard reads it.

When there is no new completed week, the run is the same full refresh and succeeds. If Sleeper's
data hasn't changed either, every saved table comes out byte-identical; only a stat correction
to a past week changes numbers. The summary says which: whether the latest completed week moved
since the tables already in data/processed/, and which tables changed.

In GitHub Actions the same summary, or the reason a run failed, is also written to the run's
summary page (the file named by GITHUB_STEP_SUMMARY), so a run's result shows without opening its log.
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from sleeper_dash import extract, lineup, metrics, seasons, transform, validate
from sleeper_dash.api import SleeperAPIError
from sleeper_dash.config import PROJECT_ROOT, load_config

RUN_RECORD_PATH = PROJECT_ROOT / "data" / "cache" / "pipeline_run.json"


def league_facts(league):
    """The league settings the dashboard's copy quotes, from Sleeper's league.json (None if they're missing)."""
    settings = league.get("settings") or {}
    if "num_teams" not in settings or "playoff_week_start" not in settings:
        return None
    return {"teams": int(settings["num_teams"]), "median_game": bool(settings.get("league_average_match")),
            "season_complete": league.get("status") == "complete",  # Sleeper marks a finished season "complete"
            "playoff_week_start": int(settings["playoff_week_start"]),
            "playoff_teams": settings.get("playoff_teams")}  # quoted by the playoff odds section and its copy


def write_run_record(league, season, weeks, path=None, all_seasons=None):
    """Record a successful run for the dashboard. Kept out of data/processed/ so the tables stay byte-identical across runs."""
    path = path or RUN_RECORD_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "league_name": league.get("name"), "season": season, "weeks": weeks, "league": league_facts(league),
              "seasons": all_seasons or [season]}
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

    # Each season is built and checked against its own league settings and Sleeper standings.
    by_season = {}
    for season in config.seasons:
        tables, league, rosters, _ = transform.build_tables(season, config.start_date(season))
        by_season[season] = (tables, league, seasons.with_known_gaps(rosters, config.sleeper_points_gaps.get(season, [])))
    teams = pd.concat([t["teams"] for t, _, _ in by_season.values()], ignore_index=True)
    managers = seasons.build_managers(teams)
    data_results = validate.validate_seasons(by_season, validate.run_data_checks, "Data checks",
                                             extra=[validate.check_managers(managers, teams)])

    players = transform.read_players()
    for tables, league, _ in by_season.values():
        tables.update(lineup.build_lineup_tables(tables, league, players))
        tables.update(metrics.build_metric_tables(tables, config.metrics, league))
    metric_results = validate.validate_seasons(by_season, validate.run_metric_checks, "Metric checks")

    tables = seasons.stack({season: t for season, (t, _, _) in by_season.items()})
    tables["managers"] = managers
    before, previous_week = saved_snapshot(config.season, tables)
    transform.save_tables(tables)
    after, _ = saved_snapshot(config.season, tables)
    saved = validate.load_tables()
    saved_by_season = {season: (seasons.season_slice(saved, season), league, rosters)
                       for season, (_, league, rosters) in by_season.items()}
    saved_results = validate.validate_seasons(saved_by_season, stage="Saved-file checks",  # the CSVs themselves pass
                                              extra=[validate.check_managers(saved["managers"], saved["teams"])])

    _, league, rosters = by_season[config.season]
    current = seasons.season_slice(saved, config.season)
    weeks = sorted(int(w) for w in current["team_weeks"]["week"].unique())
    write_run_record(league, config.season, weeks, all_seasons=config.seasons)
    # Soft check on the current season only: past seasons' gaps are known and come from today's player positions (risk 10).
    sleeper_check = lineup.compare_to_sleeper_max(
        current["lineups_optimal"], current["team_weeks"], rosters, config.metrics["efficiency"]["ppts_warn_gap"]
    )
    return {
        "season": config.season,
        "seasons": config.seasons,
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


def _season_span(all_seasons):
    return str(all_seasons[0]) if len(all_seasons) == 1 else f"{all_seasons[0]}–{all_seasons[-1]} ({len(all_seasons)} seasons)"


def _check_lines(checks):
    width = max(len(name) for name, _, _ in checks)
    return [f"    {'PASS' if passed else 'FAIL'}  {name:<{width}}  {detail}" for name, passed, detail in checks]


def write_step_summary(markdown):
    """Add markdown to the GitHub Actions run summary. Outside GitHub Actions there is none, so nothing happens."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown.rstrip() + "\n\n")


def summary_markdown(summary):
    """The run summary as markdown for GitHub's run page: latest week, checks passed, tables written."""
    weeks, rows, changed = summary["weeks"], summary["rows"], summary["changed_tables"]
    groups = [(label, summary[key]) for label, key in (("Data checks", "data_checks"), ("Metric checks", "metric_checks"))]
    passed, total = summary["saved_checks"]
    warnings = summary.get("warnings", [])
    lines = [
        "## Pipeline: passed",
        "",
        "| | |",
        "|---|---|",
        f"| Latest completed week | {_week_change(weeks[-1] if weeks else None, summary['previous_week'])} |",
        f"| Seasons | {_season_span(summary.get('seasons', [summary['season']]))} |",
        *(f"| {label} | {sum(ok for _, ok, _ in checks)} of {len(checks)} passed |" for label, checks in groups),
        f"| Saved files re-checked | {passed} of {total} checks passed |",
        f"| Tables written | {len(rows)}; vs the last run: {_table_change(changed, len(rows))} |",
        f"| Warnings | {len(warnings)} (soft checks; they never stop the run) |",
        f"| Sleeper API calls | {summary['api_calls']} |",
        "",
        "| Table | Rows | Changed this run |",
        "|---|--:|---|",
        *(f"| {name} | {n:,} | {'first save' if changed is None else 'yes' if name in changed else 'no'} |"
          for name, n in rows.items()),
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
        *(f"| {name} | {'PASS' if ok else 'FAIL'} | {detail} |" for _, checks in groups for name, ok, detail in checks),
    ]
    if warnings:
        lines += ["", *(f"- Warning: {warning}" for warning in warnings)]
    return "\n".join(lines)


def failure_markdown(error):
    """Why the pipeline stopped, for GitHub's run page."""
    return ("## Pipeline: FAILED\n\n"
            "Nothing was saved and nothing will be published; the last good page stays live.\n\n"
            f"```\n{error}\n```")


def main():
    try:
        summary = run()
    except validate.ValidationError as error:
        print(f"PIPELINE FAILED: validation\n\n{error}", file=sys.stderr)
        write_step_summary(failure_markdown(f"Validation\n\n{error}"))
        sys.exit(1)
    except (extract.ExtractError, SleeperAPIError, FileNotFoundError, ValueError) as error:
        print(f"PIPELINE FAILED: {error}", file=sys.stderr)
        write_step_summary(failure_markdown(error))
        sys.exit(1)

    write_step_summary(summary_markdown(summary))

    weeks = summary["weeks"]
    week_text = f"{weeks[0]}–{weeks[-1]}" if weeks else "none completed yet"
    print(f"Pipeline complete: season {summary['season']}, weeks {week_text}")
    print(f"  Seasons:    {_season_span(summary.get('seasons', [summary['season']]))}")
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
