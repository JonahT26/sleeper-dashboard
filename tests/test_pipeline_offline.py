"""The real pipeline, end to end, against a fake Sleeper (tests/fake_sleeper.py) in a temporary folder.

Covers what an unattended weekly job meets: Sleeper's /state/nfl describing another season or
the off-season (the 2026 tables must come out byte-identical), a run with no new completed week
(succeeds, tables unchanged), a stat correction to a past week, and a new week arriving.
"""

import pytest

from fake_sleeper import IN_SEASON, LEAGUE_ID, START_DATE, STATES, FakeSleeper
from sleeper_dash import api, extract, pipeline, transform
from sleeper_dash.config import Config, load_config
from sleeper_dash.validate import KEYS


@pytest.fixture
def run_pipeline(monkeypatch, tmp_path):
    """run_pipeline(fake, folder="a", start_date=...) runs pipeline.run() with every file under tmp_path/folder.

    Runs in the same folder share every file, as consecutive weekly runs do: the second run
    replaces the first one's raw folder (extract's swap) and compares with its saved tables.
    """
    metrics = load_config().metrics

    def run(fake, folder="a", start_date=START_DATE):
        root = tmp_path / folder
        raw = root / "raw"
        monkeypatch.setattr(api, "get", fake.get)
        monkeypatch.setattr(api, "PLAYERS_CACHE_PATH", root / "cache" / "players_nfl.json")
        monkeypatch.setattr(extract, "RAW_DIR", raw)
        monkeypatch.setattr(transform, "RAW_DIR", raw)
        monkeypatch.setattr(transform, "PROCESSED_DIR", root / "processed")
        monkeypatch.setattr(pipeline, "RUN_RECORD_PATH", root / "cache" / "pipeline_run.json")
        config = Config(league_id=LEAGUE_ID, season=2026, season_start_dates={2026: start_date}, metrics=metrics)
        monkeypatch.setattr(pipeline, "load_config", lambda: config)
        return pipeline.run()

    return run


def saved_files(tmp_path, folder):
    return {name: (tmp_path / folder / "processed" / f"{name}.csv").read_bytes() for name in KEYS}


def all_passed(summary):
    return (all(passed for _, passed, _ in summary["data_checks"] + summary["metric_checks"])
            and summary["saved_checks"][0] == summary["saved_checks"][1])


def test_fake_league_runs_cleanly_in_season(run_pipeline, tmp_path):
    summary = run_pipeline(FakeSleeper())
    assert summary["weeks"] == [1, 2, 3] and all_passed(summary)
    assert summary["previous_week"] is None and summary["changed_tables"] is None  # first save
    moves = transform.pd.read_csv(tmp_path / "a" / "processed" / "transactions.csv", dtype={"transaction_id": str})
    assert moves.set_index("transaction_id")["is_preseason"].to_dict() == {"t1": True, "t2": False}


@pytest.mark.parametrize("when", [name for name in STATES if STATES[name] is not IN_SEASON])
def test_2026_tables_are_identical_whatever_season_sleeper_describes(run_pipeline, tmp_path, when):
    baseline = run_pipeline(FakeSleeper(state=IN_SEASON), "baseline")
    other = run_pipeline(FakeSleeper(state=STATES[when]), "other")
    assert all_passed(other) and other["weeks"] == baseline["weeks"] == [1, 2, 3]
    assert saved_files(tmp_path, "other") == saved_files(tmp_path, "baseline")


def test_a_wrong_start_date_is_caught_while_sleeper_describes_the_season(run_pipeline, tmp_path):
    with pytest.raises(ValueError, match="Sleeper says it started 2026-09-09"):
        run_pipeline(FakeSleeper(state=IN_SEASON), start_date="2026-09-16")
    assert not (tmp_path / "a" / "processed").exists()  # nothing saved


def test_the_start_date_decides_preseason_moves_after_rollover(run_pipeline, tmp_path):
    # With Sleeper on 2027 there is nothing to check against: config.yaml alone decides, so a
    # later date makes the 12 Sep pickup preseason too. (This is why the date is in config.yaml.)
    run_pipeline(FakeSleeper(state=STATES["off-season, rolled over to 2027"]), start_date="2026-09-16")
    moves = transform.pd.read_csv(tmp_path / "a" / "processed" / "transactions.csv", dtype={"transaction_id": str})
    assert moves["is_preseason"].all()


@pytest.mark.parametrize("second_state", [IN_SEASON, STATES["week 5 under way, week 4 not yet scored"],
                                          STATES["off-season, rolled over to 2027"]])
def test_no_new_completed_week_succeeds_and_leaves_tables_unchanged(run_pipeline, tmp_path, second_state):
    run_pipeline(FakeSleeper(last_scored_leg=3))
    first = saved_files(tmp_path, "a")
    summary = run_pipeline(FakeSleeper(last_scored_leg=3, state=second_state))
    assert all_passed(summary) and summary["weeks"] == [1, 2, 3]
    assert summary["previous_week"] == 3 and summary["changed_tables"] == []
    assert saved_files(tmp_path, "a") == first


def test_a_stat_correction_without_a_new_week_changes_the_numbers(run_pipeline, tmp_path):
    fake = FakeSleeper(last_scored_leg=3)
    run_pipeline(fake)
    fake.corrections[(2, "101")] = 5000  # team 1's QB: 50.00 points in week 2 after a correction
    summary = run_pipeline(fake)
    assert all_passed(summary) and summary["previous_week"] == 3 and summary["weeks"] == [1, 2, 3]
    assert {"team_weeks", "player_weeks", "power_rankings"} <= set(summary["changed_tables"])
    assert "teams" not in summary["changed_tables"]


def test_a_new_week_is_reported(run_pipeline):
    run_pipeline(FakeSleeper(last_scored_leg=2, state={**IN_SEASON, "week": 3}))
    summary = run_pipeline(FakeSleeper(last_scored_leg=3))
    assert all_passed(summary) and summary["previous_week"] == 2 and summary["weeks"] == [1, 2, 3]
    # Every weekly table gains week 3; teams and transactions don't change (the fake league has
    # completed moves in week 1 only).
    assert set(summary["changed_tables"]) == set(KEYS) - {"teams", "transactions"}
