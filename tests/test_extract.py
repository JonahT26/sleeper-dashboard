"""Tests for deciding the latest completed week. A week still in progress must never count."""

import pytest

from sleeper_dash.extract import ExtractError, latest_completed_week


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
