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
    # Every weekly table gains week 3 (playoff odds start there); teams, managers, and transactions don't
    # change (the fake league has completed moves in week 1 only), and nor does Sleeper's provisional
    # bracket, because the seeding is the same after week 3 as after week 2. No trades, and the two week 1 pickups
    # never start, so trade_assets, trades, and pickups don't change either (start_credits gains week 3's starts).
    assert set(summary["changed_tables"]) == set(KEYS) - {"teams", "managers", "transactions", "winners_bracket",
                                                          "trade_assets", "trades", "pickups"}


# --- playoff weeks (HANDOFF.md risk 4) ---------------------------------------------------------
# An 8-team league scored through its first two playoff weeks (8 and 9, like weeks 15 and 16).
# Sleeper's real 2025 playoffs for this league looked like PlayoffLeague() with no behaviours:
# standings count the regular season only, every team is listed every week, byes have no
# matchup_id, and consolation games are paired. The other behaviours are what Sleeper might do
# instead. Owner decisions 2026-10-03: standings that also count the playoffs are accepted (one
# standard must fit every team); teams missing from the matchups or without a lineup stop the run.

from fake_sleeper import PlayoffLeague  # noqa: E402
from sleeper_dash import validate  # noqa: E402
from sleeper_dash.dashboard import build  # noqa: E402


def read(tmp_path, name, folder="a"):
    return transform.pd.read_csv(tmp_path / folder / "processed" / f"{name}.csv")


@pytest.mark.parametrize("behaviours", [(), ("no_consolation_games",)], ids=["as in 2025", "no consolation games"])
def test_playoff_weeks_run_cleanly_and_publish(run_pipeline, tmp_path, behaviours):
    summary = run_pipeline(PlayoffLeague(behaviours))
    assert all_passed(summary) and summary["weeks"] == list(range(1, 10))
    team_weeks = read(tmp_path, "team_weeks")
    week8 = team_weeks[team_weeks["week"] == 8]
    games = 4 if behaviours else 6  # seeds 1-2 have a bye; 7-8 play a consolation game unless there is none
    assert len(week8) == 8 and week8["matchup_id"].notna().sum() == games
    assert week8["is_playoff"].all() and week8["median_result"].isna().all()  # no median game in the playoffs
    season = read(tmp_path, "metrics_season").set_index(["through_week", "roster_id"])
    assert season.loc[9, "luck"].equals(season.loc[7, "luck"])  # luck frozen at the end of the regular season
    assert read(tmp_path, "power_rankings").groupby("week").size().loc[8:9].tolist() == [8, 8]
    root = tmp_path / "a"
    build.build_site(out_dir=root / "site", processed_dir=root / "processed", run_path=root / "cache" / "pipeline_run.json")
    html = (root / "site" / "index.html").read_text(encoding="utf-8")
    assert 'id="week-8"' in html
    # The Playoffs section in both playoff weeks; the fake's bracket, like a provisional one, has no results.
    assert html.count('class="bracket-section"') == 2 and "Winner of 1 v " in html and 'class="champion' not in html


def check_detail(summary, name):
    return next(detail for check, _, detail in summary["data_checks"] if check == name)


@pytest.mark.parametrize("behaviours, records, points", [
    (("roster_wins_include_playoff_games",), "regular season + playoff games", "regular season"),
    (("roster_wins_include_playoff_games", "roster_wins_include_playoff_median"),
     "regular season + playoff games and median", "regular season"),
    (("roster_points_include_playoffs",), "regular season", "regular season + every playoff week"),
    (("roster_wins_include_playoff_games", "roster_points_include_playoffs"),
     "regular season + playoff games", "regular season + every playoff week"),
], ids=["wins count playoff games", "wins count playoff games and median", "points count playoffs", "both count playoffs"])
def test_either_counting_standard_is_accepted_in_playoff_weeks(run_pipeline, tmp_path, behaviours, records, points):
    # Owner decision 2026-10-03: Sleeper's standings may count the playoffs too, as long as one
    # standard fits every team. Our numbers never depend on it, so the tables are identical.
    baseline = run_pipeline(PlayoffLeague(), "baseline")
    assert check_detail(baseline, "Records match Sleeper").endswith("; regular season")
    summary = run_pipeline(PlayoffLeague(behaviours), "other")
    assert all_passed(summary)
    assert check_detail(summary, "Records match Sleeper").endswith(f"; {records}")
    assert check_detail(summary, "Points for/against match Sleeper").endswith(f"; {points}")
    assert saved_files(tmp_path, "other") == saved_files(tmp_path, "baseline")


def test_standings_that_fit_no_single_standard_still_stop_the_run(run_pipeline, tmp_path):
    # Team 1 counted with its playoff games, everyone else without: no one standard fits every team.
    regular, with_playoffs = PlayoffLeague(), PlayoffLeague(("roster_wins_include_playoff_games",))

    class Mixed:
        def get(self, path):
            if path.endswith("/rosters"):
                return [with_playoffs.get(path)[0]] + regular.get(path)[1:]
            return regular.get(path)

    with pytest.raises(validate.ValidationError, match="no counting standard fits every team"):
        run_pipeline(Mixed())
    assert not (tmp_path / "a" / "processed").exists()


def test_teams_left_out_of_playoff_matchups_stop_the_run(run_pipeline, tmp_path):
    # Owner decision 2026-10-03: keep stopping (never seen; continuing would publish a broken ladder).
    with pytest.raises(validate.ValidationError, match="Every week has one row per team"):
        run_pipeline(PlayoffLeague(("no_game_teams_missing",)))
    assert not (tmp_path / "a" / "processed").exists()  # nothing saved, so nothing published


def test_unscored_no_game_teams_stop_the_run(run_pipeline, tmp_path):
    # Owner decision 2026-10-03: keep stopping (never seen). Stops in transform, before any check runs.
    with pytest.raises(ValueError, match="Week 8, roster 1: 0 starters"):
        run_pipeline(PlayoffLeague(("no_game_teams_unscored",)))
    assert not (tmp_path / "a" / "processed").exists()
