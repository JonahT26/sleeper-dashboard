"""Tests for loading config.yaml: required settings, quoted league ID, and the season start dates."""

import pytest

from sleeper_dash.config import load_config

VALID = 'league_id: "123"\nseason: 2026\nseason_start_dates:\n  2026: 2026-09-09\n'


def write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_project_config_loads():
    config = load_config()
    assert config.season_start_date.startswith(str(config.season))


def test_unquoted_and_quoted_dates_both_load_as_text(tmp_path):
    assert load_config(write(tmp_path, VALID)).season_start_date == "2026-09-09"
    quoted = VALID.replace("2026-09-09", '"2026-09-09"')
    assert load_config(write(tmp_path, quoted)).season_start_date == "2026-09-09"


def test_past_seasons_have_their_own_dates(tmp_path):
    # Phase 5 rebuilds past seasons, which Sleeper's /state/nfl can no longer describe.
    config = load_config(write(tmp_path, VALID + "  2025: 2025-09-04\n"))
    assert config.start_date(2025) == "2025-09-04"
    assert config.season_start_date == "2026-09-09"


def test_a_season_without_a_date_is_a_clear_error(tmp_path):
    config = load_config(write(tmp_path, VALID))
    with pytest.raises(ValueError, match="no date for season 2024"):
        config.start_date(2024)


def test_season_start_dates_are_required(tmp_path):
    with pytest.raises(ValueError, match="season_start_dates"):
        load_config(write(tmp_path, 'league_id: "123"\nseason: 2026\n'))


def test_the_configured_season_needs_a_date(tmp_path):
    # Bumping season without adding its start date stops the run.
    with pytest.raises(ValueError, match="no date for season 2027"):
        load_config(write(tmp_path, VALID.replace("season: 2026", "season: 2027")))


@pytest.mark.parametrize("value", ['"2026-13-01"', "Sept 9", "20260909", "2026-09-09T00:00:00", "null"])
def test_each_start_date_must_be_a_date(tmp_path, value):
    with pytest.raises(ValueError, match="season_start_dates"):
        load_config(write(tmp_path, VALID.replace("2026-09-09", value)))


def test_each_start_date_must_be_in_its_season(tmp_path):
    with pytest.raises(ValueError, match="isn't in 2026"):
        load_config(write(tmp_path, VALID.replace("2026-09-09", "2027-09-08")))


@pytest.mark.parametrize("dates", ['"2026-09-09"', "[2026-09-09]", "{}", '\n  "twenty": 2026-09-09'])
def test_start_dates_must_be_listed_by_season(tmp_path, dates):
    with pytest.raises(ValueError, match="season_start_dates"):
        load_config(write(tmp_path, f'league_id: "123"\nseason: 2026\nseason_start_dates: {dates}\n'))


def test_impossible_unquoted_date_names_the_file(tmp_path):
    # YAML itself rejects it while reading, before the setting is looked at.
    with pytest.raises(ValueError, match="config.yaml has a value that can't be read .* YYYY-MM-DD"):
        load_config(write(tmp_path, VALID.replace("2026-09-09", "2026-13-01")))


def test_league_id_must_be_quoted(tmp_path):
    with pytest.raises(ValueError, match="quoted string"):
        load_config(write(tmp_path, VALID.replace('"123"', "123")))
