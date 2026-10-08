"""Tests for the pipeline: step order, stopping on failed checks, the summary, and exit codes.

Every step is faked, so nothing is downloaded or saved.
"""

from types import SimpleNamespace

import pandas as pd
import pytest

from sleeper_dash import pipeline
from sleeper_dash.api import SleeperAPIError
from sleeper_dash.validate import CheckResult, ValidationError

SUMMARY = {
    "season": 2026, "weeks": [1, 2, 3], "api_calls": 23,
    "rows": {"teams": 12, "team_weeks": 36, "player_weeks": 603, "transactions": 189, "power_rankings": 36},
    "data_checks": [("Records match Sleeper", True, "12 teams"), ("No duplicate keys (data tables)", True, "5 tables")],
    "metric_checks": [("Power rankings are consistent", True, "mean 50"), ("Weekly awards are consistent", True, "24 awards")],
    "saved_checks": (4, 4), "warnings": [], "seconds": 6.4, "previous_week": 3, "changed_tables": [],
}


def test_success_prints_the_summary_with_both_groups_of_checks(monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "run", lambda: SUMMARY)
    pipeline.main()
    out = capsys.readouterr().out
    assert "weeks 1–3" in out and "603 rows" in out and "6.4s" in out
    assert "Data checks:  2 of 2 passed" in out and "Metric checks:  2 of 2 passed" in out
    assert "PASS  Power rankings are consistent" in out and "PASS  Weekly awards are consistent" in out
    assert "4 of 4 checks passed after re-reading" in out


@pytest.mark.parametrize("previous, changed, week_line, table_line", [
    (3, [], "3 (no new completed week since the last run)", "unchanged (every file identical)"),
    (3, ["team_weeks", "power_rankings"], "3 (no new completed week since the last run)", "2 of 5 changed: team_weeks, power_rankings"),
    (2, ["team_weeks"], "3 (new: the last run ended at week 2)", "1 of 5 changed: team_weeks"),
    (None, None, "3 (no saved tables for this season before this run)", "first save"),
])
def test_summary_says_whether_the_week_and_the_tables_changed(monkeypatch, capsys, previous, changed, week_line, table_line):
    monkeypatch.setattr(pipeline, "run", lambda: {**SUMMARY, "previous_week": previous, "changed_tables": changed})
    pipeline.main()
    out = capsys.readouterr().out
    assert f"Latest completed week:  {week_line}" in out
    assert f"Tables vs the last run: {table_line}" in out


@pytest.mark.parametrize("status, complete", [("in_season", False), ("complete", True), (None, False)])
def test_the_run_record_says_whether_sleeper_marks_the_season_complete(status, complete):
    league = {"status": status, "settings": {"num_teams": 12, "playoff_week_start": 15, "league_average_match": 1}}
    assert pipeline.league_facts(league) == {"teams": 12, "median_game": True, "season_complete": complete,
                                             "playoff_week_start": 15, "playoff_teams": None}


def test_in_github_actions_the_summary_goes_on_the_run_page(monkeypatch, tmp_path):
    page = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(page))
    monkeypatch.setattr(pipeline, "run", lambda: {**SUMMARY, "previous_week": 2, "changed_tables": ["team_weeks"]})
    pipeline.main()
    text = page.read_text(encoding="utf-8")
    assert text.startswith("## Pipeline: passed")
    assert "| Latest completed week | 3 (new: the last run ended at week 2) |" in text
    assert "| Data checks | 2 of 2 passed |" in text and "| Metric checks | 2 of 2 passed |" in text
    assert "| Saved files re-checked | 4 of 4 checks passed |" in text
    assert "| Tables written | 5; vs the last run: 1 of 5 changed: team_weeks |" in text
    assert "| team_weeks | 36 | yes |" in text and "| player_weeks | 603 | no |" in text
    assert "| Records match Sleeper | PASS | 12 teams |" in text


def test_outside_github_actions_nothing_is_written(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "run", lambda: SUMMARY)
    pipeline.main()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("error", [ValidationError("Records match Sleeper: roster 4 has 2 wins, Sleeper says 3"),
                                   SleeperAPIError("Gave up on /state/nfl")])
def test_a_failure_says_why_on_the_run_page(monkeypatch, tmp_path, error):
    page = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(page))

    def fail():
        raise error

    monkeypatch.setattr(pipeline, "run", fail)
    with pytest.raises(SystemExit):
        pipeline.main()
    text = page.read_text(encoding="utf-8")
    assert text.startswith("## Pipeline: FAILED")
    assert "the last good page stays live" in text and str(error) in text


@pytest.mark.parametrize("error", [ValidationError("Metric checks: 1 check(s) failed"), SleeperAPIError("Gave up on /state/nfl")])
def test_failures_exit_with_code_1_and_explain(monkeypatch, capsys, error):
    def fail():
        raise error

    monkeypatch.setattr(pipeline, "run", fail)
    with pytest.raises(SystemExit) as exit_info:
        pipeline.main()
    assert exit_info.value.code == 1
    assert "PIPELINE FAILED" in capsys.readouterr().err


# --- run(): step order and stopping on failed checks ------------------------------------------

@pytest.fixture
def steps(monkeypatch, tmp_path):
    """Fake every step of run(), recording the order they're called in."""
    calls = []
    monkeypatch.setattr(pipeline, "RUN_RECORD_PATH", tmp_path / "pipeline_run.json")
    monkeypatch.setattr(pipeline.transform, "PROCESSED_DIR", tmp_path / "processed")  # empty: nothing saved before
    team_weeks = pd.DataFrame({"season": 2026, "week": [1, 2], "roster_id": [1, 1]})
    teams = pd.DataFrame({"season": [2026], "roster_id": [1], "owner_id": ["900"], "display_name": ["user1"]})
    no_rows = pd.DataFrame({"season": pd.Series(dtype="int64")})
    config = SimpleNamespace(season=2026, seasons=[2026], season_start_date="2026-09-09", start_date=lambda season: "2026-09-09",
                             sleeper_points_gaps={}, champion_overrides={}, metrics={"efficiency": {"ppts_warn_gap": 5.0}})
    outcome = {"data": True, "metric": True}

    def record(name, result=None):
        def step(*args, **kwargs):
            calls.append(name)
            return result
        return step

    def checks(group):
        def run_group(tables, league, rosters):
            calls.append(f"{group} checks")
            return [CheckResult(f"{group} check", outcome[group], "detail")]
        return run_group

    monkeypatch.setattr(pipeline, "load_config", lambda: config)
    monkeypatch.setattr(pipeline.extract, "extract", record("extract", {"calls": 23}))
    monkeypatch.setattr(pipeline.transform, "build_tables", record("transform", ({"team_weeks": team_weeks, "teams": teams}, {}, [], None)))
    monkeypatch.setattr(pipeline.validate, "check_managers", lambda *a: CheckResult("managers check", True, "ok"))
    monkeypatch.setattr(pipeline.transform, "read_players", lambda: {})
    monkeypatch.setattr(pipeline.lineup, "build_lineup_tables", record("lineups", {"lineups_optimal": no_rows}))
    monkeypatch.setattr(pipeline.metrics, "build_metric_tables", record("metrics", {"power_rankings": pd.DataFrame()}))
    monkeypatch.setattr(pipeline.validate, "run_data_checks", checks("data"))
    monkeypatch.setattr(pipeline.validate, "run_metric_checks", checks("metric"))
    monkeypatch.setattr(pipeline.validate, "run_checks", lambda *a: [CheckResult("saved", True, "ok")])
    monkeypatch.setattr(pipeline.transform, "save_tables", record("save"))
    monkeypatch.setattr(pipeline.validate, "load_tables", record("reload", {"team_weeks": team_weeks, "lineups_optimal": no_rows,
                                                                            "teams": teams, "managers": pd.DataFrame()}))
    monkeypatch.setattr(pipeline.lineup, "compare_to_sleeper_max", lambda *a: pd.DataFrame({"roster_id": [], "warning": []}))
    return calls, outcome


def test_steps_run_in_order(steps):
    calls, _ = steps
    summary = pipeline.run()
    assert calls == ["extract", "transform", "data checks", "lineups", "metrics", "metric checks", "save", "reload"]
    assert summary["data_checks"] == [("data check", True, "detail"), ("managers check", True, "ok"),
                                     ("Title overrides match Sleeper's bracket", True, "no overrides")]
    assert summary["metric_checks"] == [("metric check", True, "detail")]


def test_a_successful_run_records_when_it_finished(steps):
    import json

    pipeline.run()
    record = json.loads(pipeline.RUN_RECORD_PATH.read_text(encoding="utf-8"))
    assert record["season"] == 2026 and record["weeks"] == [1, 2]
    assert record["finished_at"].endswith("+00:00")


def test_a_failed_run_records_nothing(steps):
    _, outcome = steps
    outcome["metric"] = False
    with pytest.raises(ValidationError):
        pipeline.run()
    assert not pipeline.RUN_RECORD_PATH.exists()


def test_a_failed_data_check_stops_before_metrics_and_saves_nothing(steps):
    calls, outcome = steps
    outcome["data"] = False
    with pytest.raises(ValidationError, match="Data checks"):
        pipeline.run()
    assert calls == ["extract", "transform", "data checks"]


def test_a_failed_metric_check_stops_the_run_and_saves_nothing(steps):
    calls, outcome = steps
    outcome["metric"] = False
    with pytest.raises(ValidationError, match="Metric checks"):
        pipeline.run()
    assert "save" not in calls and calls[-1] == "metric checks"
