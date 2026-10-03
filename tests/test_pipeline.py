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
    "saved_checks": (4, 4), "warnings": [], "seconds": 6.4,
}


def test_success_prints_the_summary_with_both_groups_of_checks(monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "run", lambda: SUMMARY)
    pipeline.main()
    out = capsys.readouterr().out
    assert "weeks 1–3" in out and "603 rows" in out and "6.4s" in out
    assert "Data checks:  2 of 2 passed" in out and "Metric checks:  2 of 2 passed" in out
    assert "PASS  Power rankings are consistent" in out and "PASS  Weekly awards are consistent" in out
    assert "4 of 4 checks passed after re-reading" in out


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
def steps(monkeypatch):
    """Fake every step of run(), recording the order they're called in."""
    calls = []
    team_weeks = pd.DataFrame({"week": [1, 2], "roster_id": [1, 1]})
    config = SimpleNamespace(season=2026, metrics={"efficiency": {"ppts_warn_gap": 5.0}})
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
    monkeypatch.setattr(pipeline.transform, "build_tables", record("transform", ({"team_weeks": team_weeks}, {}, [], None)))
    monkeypatch.setattr(pipeline.transform, "read_players", lambda: {})
    monkeypatch.setattr(pipeline.lineup, "build_lineup_tables", record("lineups", {"lineups_optimal": pd.DataFrame()}))
    monkeypatch.setattr(pipeline.metrics, "build_metric_tables", record("metrics", {"power_rankings": pd.DataFrame()}))
    monkeypatch.setattr(pipeline.validate, "run_data_checks", checks("data"))
    monkeypatch.setattr(pipeline.validate, "run_metric_checks", checks("metric"))
    monkeypatch.setattr(pipeline.validate, "run_checks", lambda *a: [CheckResult("saved", True, "ok")])
    monkeypatch.setattr(pipeline.transform, "save_tables", record("save"))
    monkeypatch.setattr(pipeline.validate, "load_tables", record("reload", {"team_weeks": team_weeks, "lineups_optimal": pd.DataFrame()}))
    monkeypatch.setattr(pipeline.lineup, "compare_to_sleeper_max", lambda *a: pd.DataFrame({"roster_id": [], "warning": []}))
    return calls, outcome


def test_steps_run_in_order(steps):
    calls, _ = steps
    summary = pipeline.run()
    assert calls == ["extract", "transform", "data checks", "lineups", "metrics", "metric checks", "save", "reload"]
    assert summary["data_checks"] == [("data check", True, "detail")]
    assert summary["metric_checks"] == [("metric check", True, "detail")]


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
