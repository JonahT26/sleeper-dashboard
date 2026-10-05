"""Past seasons (Phase 5): several seasons built and checked one by one, stacked, and managers matched by owner ID.

Covers seasons.py, the multi-season parts of config.py, extract, validate, and the pipeline (end to end
against a fake two-season league), plus the three rules settled when past seasons were added
(owner, 2026-10-05): Sleeper's known stale season totals, eligibility from the slot a player started
in, and the regular season counted from week 1 whatever Sleeper's start_week says.
"""

import pandas as pd
import pytest

from fake_sleeper import LEAGUE_ID, START_DATE, FakeHistory, FakeSleeper
from sleeper_dash import api, extract, lineup, pipeline, seasons, transform
from sleeper_dash import validate as v
from sleeper_dash.config import Config, load_config
from sleeper_dash.validate import KEYS, CheckResult

PAST_LEAGUE = "2000000000000000000"
PAST_OWNERS = {1: "900000000000000002", 2: "900000000000000001", 3: "900000000000000003",  # managers 1 and 2 swapped rosters
               4: "900000000000000004", 5: "900000000000000005", 6: "900000000000000099"}  # manager 99 has since left


def two_seasons():
    current = FakeSleeper(previous_league_id=PAST_LEAGUE)
    past = FakeSleeper(last_scored_leg=5, league_id=PAST_LEAGUE, season="2025", owners=PAST_OWNERS)
    return FakeHistory(current, past)


@pytest.fixture
def run_pipeline(monkeypatch, tmp_path):
    metrics = load_config().metrics

    def run(fake, folder="a", history_from=2025, gaps=None):
        root = tmp_path / folder
        monkeypatch.setattr(api, "get", fake.get)
        monkeypatch.setattr(api, "PLAYERS_CACHE_PATH", root / "cache" / "players_nfl.json")
        monkeypatch.setattr(extract, "RAW_DIR", root / "raw")
        monkeypatch.setattr(transform, "RAW_DIR", root / "raw")
        monkeypatch.setattr(transform, "PROCESSED_DIR", root / "processed")
        monkeypatch.setattr(pipeline, "RUN_RECORD_PATH", root / "cache" / "pipeline_run.json")
        config = Config(league_id=LEAGUE_ID, season=2026, season_start_dates={2025: "2025-09-03", 2026: START_DATE},
                        metrics=metrics, history_from=history_from, sleeper_points_gaps=gaps or {})
        monkeypatch.setattr(pipeline, "load_config", lambda: config)
        return pipeline.run()

    return run


def saved(tmp_path, folder, name):
    return pd.read_csv(tmp_path / folder / "processed" / f"{name}.csv", dtype={"owner_id": str}, encoding="utf-8-sig")


# --- end to end -------------------------------------------------------------------------------

def test_two_seasons_are_built_checked_and_stacked(run_pipeline, tmp_path):
    summary = run_pipeline(two_seasons())
    assert summary["seasons"] == [2025, 2026] and summary["weeks"] == [1, 2, 3]  # weeks: the current season
    assert all(ok for _, ok, _ in summary["data_checks"] + summary["metric_checks"])
    details = dict((name, detail) for name, _, detail in summary["data_checks"])
    assert details["Records match Sleeper"].endswith("passed in 1 earlier season(s) too")
    for name in KEYS:
        if name != "managers":
            assert set(saved(tmp_path, "a", name)["season"]) <= {2025, 2026}, name
    team_weeks = saved(tmp_path, "a", "team_weeks")
    assert team_weeks.groupby("season")["week"].max().to_dict() == {2025: 5, 2026: 3}


def test_adding_a_past_season_leaves_the_current_seasons_rows_unchanged(run_pipeline, tmp_path):
    run_pipeline(FakeSleeper(), "alone", history_from=None)
    run_pipeline(two_seasons(), "with history")
    for name in KEYS:
        if name == "managers":
            continue
        alone = saved(tmp_path, "alone", name)
        both = saved(tmp_path, "with history", name)
        current = both[both["season"] == 2026].reset_index(drop=True)
        if name == "teams":  # team names in the fake say which season they're from; everything else is the same
            alone, current = alone.drop(columns="team_name"), current.drop(columns="team_name")
        pd.testing.assert_frame_equal(alone, current, check_dtype=False, obj=name)


def test_managers_are_matched_by_owner_id_not_roster_or_team_name(run_pipeline, tmp_path):
    run_pipeline(two_seasons())
    managers = saved(tmp_path, "a", "managers").set_index("owner_id")
    assert len(managers) == 7  # six current managers plus one who left
    assert managers.loc["900000000000000001", ["first_season", "last_season", "seasons"]].tolist() == [2025, 2026, 2]
    assert managers.loc["900000000000000099", ["first_season", "last_season", "seasons"]].tolist() == [2025, 2025, 1]
    assert managers.loc["900000000000000006", "first_season"] == 2026
    teams = saved(tmp_path, "a", "teams")
    # Manager 1 had roster 2 in 2025 and roster 1 in 2026: same person, different roster.
    rows = teams[teams["owner_id"] == "900000000000000001"].set_index("season")["roster_id"].to_dict()
    assert rows == {2025: 2, 2026: 1}


def test_a_history_longer_than_sleepers_stops_the_run(run_pipeline):
    with pytest.raises(extract.ExtractError, match="no league before season 2025"):
        run_pipeline(two_seasons(), history_from=2024)


def test_a_failed_check_in_a_past_season_stops_the_run_and_names_the_season(run_pipeline, tmp_path):
    with pytest.raises(v.ValidationError, match=r"2025: .*roster 1: points for") as error:
        run_pipeline(two_seasons(), gaps={2025: [{"roster_id": 1, "points_for": 5.0, "points_against": 0.0}]})
    assert "after adding back 1 team(s)' known gaps" in str(error.value)
    assert not (tmp_path / "a" / "processed").exists()  # nothing saved


# --- known gaps in Sleeper's stored season totals (owner decision 1a) --------------------------

def rosters_with(points_for, points_against):
    return [{"roster_id": 1, "settings": {"wins": 1, "losses": 0, "ties": 0, "fpts": int(points_for),
                                          "fpts_decimal": round(points_for % 1 * 100), "fpts_against": int(points_against),
                                          "fpts_against_decimal": round(points_against % 1 * 100)}}]


def test_known_gaps_are_added_back_to_sleepers_totals_to_the_cent():
    adjusted = seasons.with_known_gaps(rosters_with(1796.62, 1639.18), [{"roster_id": 1, "points_for": -2.00, "points_against": 17.70}])
    s = adjusted[0]["settings"]
    assert (s["fpts"], s["fpts_decimal"], s["fpts_against"], s["fpts_against_decimal"]) == (1794, 62, 1656, 88)
    assert s["known_points_gap"]
    original = rosters_with(1796.62, 1639.18)
    assert seasons.with_known_gaps(original, []) == original  # no gaps: an unchanged copy


def test_the_points_check_allows_exactly_the_listed_gaps():
    team_weeks = pd.DataFrame({"season": 2023, "week": [1], "roster_id": [1], "points": [101.00], "opponent_points": [90.00],
                               "is_playoff": [False]})
    stale = rosters_with(100.00, 90.00)  # Sleeper's total missed a 1-point correction
    assert not v.check_points_for_against(team_weeks, stale).passed
    fixed = seasons.with_known_gaps(stale, [{"roster_id": 1, "points_for": 1.00, "points_against": 0.0}])
    result = v.check_points_for_against(team_weeks, fixed)
    assert result.passed and "1 team(s) with a known Sleeper gap" in result.detail
    wrong = seasons.with_known_gaps(stale, [{"roster_id": 1, "points_for": 2.00, "points_against": 0.0}])
    assert not v.check_points_for_against(team_weeks, wrong).passed  # a listed gap must be exactly right


def test_the_config_lists_the_gaps_found_in_2020_2021_and_2023():
    gaps = load_config().sleeper_points_gaps
    assert sorted(gaps) == [2020, 2021, 2023]
    for season, entries in gaps.items():  # each gap is one game: a team's points for is its opponent's points against
        assert round(sum(e["points_for"] for e in entries), 2) == round(sum(e["points_against"] for e in entries), 2)


# --- eligibility from the slot a player started in (owner decision 2) ---------------------------

def test_a_start_in_a_single_position_slot_proves_that_position_that_week():
    assert lineup.week_positions(frozenset({"RB"}), "WR") == frozenset({"RB", "WR"})
    assert lineup.week_positions(frozenset({"RB"}), "FLEX") == frozenset({"RB"})  # a flex start proves nothing more
    assert lineup.week_positions(frozenset({"RB"}), None) == frozenset({"RB"})    # bench


def test_a_player_listed_differently_today_can_still_fill_the_slot_he_started_in():
    # 2021 week 8: a WR whom Sleeper lists as RB today. Without the rule the best lineup scored less than the real one.
    player_weeks = pd.DataFrame({
        "season": 2021, "week": 8, "roster_id": 7, "slot_order": [0, 1, 2], "lineup_slot": ["RB", "WR", "BN"],
        "player_id": ["a", "b", "c"], "full_name": ["A", "B", "C"], "position": ["RB", "RB", "RB"],
        "is_starter": [True, True, False], "is_empty_slot": [False, False, False], "points": [10.0, 15.7, 3.0]})
    team_weeks = pd.DataFrame({"season": [2021], "week": [8], "roster_id": [7], "points": [25.7]})
    positions = {"a": frozenset({"RB"}), "b": frozenset({"RB"}), "c": frozenset({"RB"})}
    lineups, _ = lineup.build_optimal_lineups(player_weeks, team_weeks, ["RB", "WR", "BN"], positions)
    assert lineups["optimal_points"].tolist() == [25.7] and lineups["efficiency"].tolist() == [1.0]


# --- the regular season starts in week 1 (owner decision 3) -------------------------------------

def test_the_regular_season_starts_in_week_1_whatever_start_week_says():
    league_2020 = {"settings": {"start_week": 4, "playoff_week_start": 14}}
    assert v._regular_weeks(league_2020) == list(range(1, 14))


# --- combining checks across seasons, and managers -------------------------------------------

def test_one_season_keeps_its_results_and_several_are_combined():
    one = [CheckResult("Records match Sleeper", True, "12 teams")]
    assert v.combine_season_results({2026: one}) == one
    combined = v.combine_season_results({2025: [CheckResult("Records match Sleeper", False, "roster 3: 9 wins vs 10")],
                                         2026: one, 2024: [CheckResult("Records match Sleeper", True, "12 teams")]})
    assert combined == [CheckResult("Records match Sleeper", False, "2025: roster 3: 9 wins vs 10")]
    passing = v.combine_season_results({2025: one, 2026: one})
    assert passing[0].passed and passing[0].detail == "2026: 12 teams; passed in 1 earlier season(s) too"


def test_validate_seasons_raises_naming_the_stage():
    def checks(tables, league, rosters):
        return [CheckResult("A check", league["ok"], "detail")]
    with pytest.raises(v.ValidationError, match="Data checks: 1 check"):
        v.validate_seasons({2025: ({}, {"ok": False}, []), 2026: ({}, {"ok": True}, [])}, checks, "Data checks")


def make_teams():
    return pd.DataFrame({"season": [2025, 2025, 2026, 2026], "roster_id": [1, 2, 1, 2],
                         "owner_id": ["A", "B", "B", "C"], "display_name": ["ann", "bob_old", "bob", "cat"]})


def test_managers_take_their_latest_name_and_count_their_seasons():
    managers = seasons.build_managers(make_teams()).set_index("owner_id")
    assert managers.loc["B"].tolist() == ["bob", 2025, 2026, 2]
    assert managers.loc["A"].tolist() == ["ann", 2025, 2025, 1]
    assert managers.loc["C"].tolist() == ["cat", 2026, 2026, 1]
    assert v.check_managers(seasons.build_managers(make_teams()), make_teams()).passed


def test_the_managers_check_catches_problems():
    teams = make_teams()
    managers = seasons.build_managers(teams)
    doubled = teams.assign(owner_id=["A", "A", "B", "C"])
    assert "2025: owner A has 2 teams" in v.check_managers(seasons.build_managers(doubled), doubled).detail
    assert "owner C owns a team but isn't in managers" in v.check_managers(managers[managers["owner_id"] != "C"], teams).detail
    wrong = managers.assign(seasons=managers["seasons"] + 1)
    assert "seasons is" in v.check_managers(wrong, teams).detail


def test_stack_and_slice_round_trip():
    by_season = {2026: {"t": pd.DataFrame({"season": [2026], "x": [1]})},
                 2025: {"t": pd.DataFrame({"season": [2025, 2025], "x": [2, 3]}), "u": pd.DataFrame({"season": [2025]})}}
    stacked = seasons.stack(by_season)
    assert stacked["t"]["season"].tolist() == [2025, 2025, 2026] and stacked["u"]["season"].tolist() == [2025]
    assert seasons.season_slice(stacked, 2026)["t"]["x"].tolist() == [1]
    empty = seasons.stack({2025: {"t": pd.DataFrame({"season": pd.Series(dtype="int64"), "x": pd.Series(dtype="float64")})},
                           2026: {"t": pd.DataFrame({"season": [2026], "x": [1.5]})}})
    assert empty["t"]["x"].dtype == "float64"


# --- config ------------------------------------------------------------------------------------

def write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


BASE = 'league_id: "123"\nseason: 2026\nseason_start_dates:\n  2025: 2025-09-03\n  2026: 2026-09-09\n'


def test_history_from_sets_the_seasons_and_needs_a_date_for_each(tmp_path):
    from sleeper_dash.config import load_config as load

    assert load(write(tmp_path, BASE)).seasons == [2026]
    assert load(write(tmp_path, BASE + "history_from: 2025\n")).seasons == [2025, 2026]
    with pytest.raises(ValueError, match=r"no date for season\(s\) \[2024\]"):
        load(write(tmp_path, BASE + "history_from: 2024\n"))
    with pytest.raises(ValueError, match="no later than season"):
        load(write(tmp_path, BASE + "history_from: 2027\n"))
    assert load_config().seasons == list(range(2020, 2027))  # the project: every season since 2020 (owner, 2026-10-05)


def test_known_gaps_in_config_are_read_and_checked(tmp_path):
    from sleeper_dash.config import load_config as load

    text = BASE + "sleeper_points_gaps:\n  2025:\n    - {roster_id: 3, points_for: 2.00}\n"
    assert load(write(tmp_path, text)).sleeper_points_gaps == {2025: [{"roster_id": 3, "points_for": 2.0, "points_against": 0.0}]}
    with pytest.raises(ValueError, match="sleeper_points_gaps"):
        load(write(tmp_path, BASE + "sleeper_points_gaps:\n  2025:\n    - {points_for: 2.00}\n"))
    with pytest.raises(ValueError, match="sleeper_points_gaps"):
        load(write(tmp_path, BASE + "sleeper_points_gaps:\n  2025:\n    - {roster_id: 3, pf: 2.00}\n"))
