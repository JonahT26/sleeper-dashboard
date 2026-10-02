"""Tests for the pipeline's summary output and exit codes. run() is faked, so nothing is downloaded."""

import pytest

from sleeper_dash import pipeline
from sleeper_dash.api import SleeperAPIError
from sleeper_dash.validate import ValidationError

SUMMARY = {
    "season": 2026, "weeks": [1, 2, 3], "api_calls": 12,
    "rows": {"teams": 12, "team_weeks": 36, "player_weeks": 603, "transactions": 189},
    "checks_passed": 6, "checks_total": 6, "seconds": 3.2,
}


def test_success_prints_the_summary(monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "run", lambda: SUMMARY)
    pipeline.main()
    out = capsys.readouterr().out
    assert "weeks 1–3" in out and "6 of 6 passed" in out and "603 rows" in out and "3.2s" in out


@pytest.mark.parametrize("error", [ValidationError("Records match Sleeper  FAIL"), SleeperAPIError("Gave up on /state/nfl")])
def test_failures_exit_with_code_1_and_explain(monkeypatch, capsys, error):
    def fail():
        raise error

    monkeypatch.setattr(pipeline, "run", fail)
    with pytest.raises(SystemExit) as exit_info:
        pipeline.main()
    assert exit_info.value.code == 1
    assert "PIPELINE FAILED" in capsys.readouterr().err
