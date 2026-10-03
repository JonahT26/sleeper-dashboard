"""Tests for deciding the latest completed week. A week still in progress must never count."""

import pytest

from sleeper_dash.extract import ExtractError, future_schedule_weeks, latest_completed_week


def make_state(week, season="2026", season_type="regular"):
    return {"week": week, "season": season, "season_type": season_type}


def make_league(last_scored_leg, season="2026"):
    return {"season": season, "settings": {"last_scored_leg": last_scored_leg}}


def test_mid_season_both_signals_agree():
    # Week 4 under way; Sleeper has scored through week 3.
    assert latest_completed_week(make_state(4), make_league(3)) == 3


def test_scoring_not_finished_after_calendar_rolls_over():
    # NFL calendar says week 5, but Sleeper has not finished scoring week 4 yet.
    assert latest_completed_week(make_state(5), make_league(3)) == 3


def test_in_progress_week_never_counts_even_if_scored_leg_runs_ahead():
    # If last_scored_leg ever moved during a week, the NFL calendar still caps it.
    assert latest_completed_week(make_state(4), make_league(4)) == 3


def test_preseason_has_no_completed_weeks():
    assert latest_completed_week(make_state(1, season_type="pre"), make_league(0)) == 0


def test_week_one_in_progress_has_no_completed_weeks():
    assert latest_completed_week(make_state(1), make_league(0)) == 0


def test_after_the_season_uses_last_scored_leg():
    # Next NFL season has begun; this league's season is over through week 17.
    assert latest_completed_week(make_state(2, season="2027"), make_league(17)) == 17


def test_missing_last_scored_leg_is_an_error():
    league = {"season": "2026", "settings": {}}
    with pytest.raises(ExtractError, match="last_scored_leg"):
        latest_completed_week(make_state(4), league)


@pytest.mark.parametrize("last_week, expected", [(0, list(range(1, 15))), (3, list(range(4, 15))), (14, []), (17, [])])
def test_future_schedule_covers_the_rest_of_the_regular_season(last_week, expected):
    league = {"settings": {"playoff_week_start": 15}}
    assert future_schedule_weeks(league, last_week) == expected


# --- replacing data/raw/{season}/ (Windows can briefly refuse it) ------------------------------

def _folders(tmp_path):
    from sleeper_dash import extract

    staging, season = tmp_path / "2026.partial", tmp_path / "2026"
    for folder, text in ((staging, "new"), (season, "old")):
        folder.mkdir()
        (folder / "league.json").write_text(text, encoding="utf-8")
    return extract, staging, season


def test_swap_retries_when_windows_briefly_refuses(tmp_path, monkeypatch):
    extract, staging, season = _folders(tmp_path)
    real_rename, refusals, waits = type(staging).rename, [2], []

    def flaky_rename(self, target):
        if refusals[0]:
            refusals[0] -= 1
            raise PermissionError(5, "Access is denied")
        return real_rename(self, target)

    monkeypatch.setattr(type(staging), "rename", flaky_rename)
    monkeypatch.setattr(extract.time, "sleep", waits.append)
    extract._swap_in(staging, season)
    assert (season / "league.json").read_text(encoding="utf-8") == "new" and not staging.exists()
    assert waits == [0.2, 0.4]


def test_swap_gives_up_with_a_clear_error(tmp_path, monkeypatch):
    extract, staging, season = _folders(tmp_path)

    def refuse(self, target):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(type(staging), "rename", refuse)
    monkeypatch.setattr(extract.time, "sleep", lambda seconds: None)
    with pytest.raises(ExtractError, match="after 5 tries"):
        extract._swap_in(staging, season)
    assert (staging / "league.json").exists()  # the new download is kept for a rerun to replace
