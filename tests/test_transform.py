"""Tests for the teams table, built from the anonymised rosters fixture plus made-up users."""

import json
from pathlib import Path

import pandas as pd
import pytest

from sleeper_dash.transform import TEAM_WEEKS_COLUMNS, TEAMS_COLUMNS, build_team_weeks, build_teams, save_table

FIXTURES = Path(__file__).parent / "fixtures"
LEAGUE = {"season": "2026"}


@pytest.fixture
def rosters():
    return json.loads((FIXTURES / "rosters.json").read_text(encoding="utf-8"))


def make_users(rosters):
    """One user per roster owner, each with a custom team name."""
    return [
        {"user_id": r["owner_id"], "display_name": f"user{r['roster_id']}", "metadata": {"team_name": f"Team {r['roster_id']}"}}
        for r in rosters
    ]


def test_one_row_per_roster_with_spec_columns_and_types(rosters):
    teams = build_teams(LEAGUE, rosters, make_users(rosters))
    assert list(teams.columns) == TEAMS_COLUMNS
    assert len(teams) == 12
    assert teams["roster_id"].tolist() == list(range(1, 13))
    assert (teams["season"] == 2026).all()
    assert str(teams["owner_id"].dtype) == "string"
    assert teams["co_owners"].map(lambda v: v == []).all()  # null in raw becomes an empty list


def test_team_name_prefers_metadata_and_strips_spaces(rosters):
    users = make_users(rosters)
    users[0]["metadata"]["team_name"] = "  Padded Name "
    teams = build_teams(LEAGUE, rosters, users)
    row = teams.set_index("owner_id").loc[users[0]["user_id"]]
    assert row["team_name"] == "Padded Name"
    assert row["display_name"] == users[0]["display_name"]


@pytest.mark.parametrize("metadata", [{}, {"team_name": ""}, {"team_name": "   "}, None])
def test_team_name_falls_back_to_display_name(rosters, metadata):
    users = make_users(rosters)
    users[0]["metadata"] = metadata
    teams = build_teams(LEAGUE, rosters, users)
    row = teams.set_index("owner_id").loc[users[0]["user_id"]]
    assert row["team_name"] == users[0]["display_name"]


def test_team_without_owner_keeps_its_row(rosters):
    users = make_users(rosters)
    del users[4]  # the departed owner is no longer a league user
    rosters[4]["owner_id"] = None
    teams = build_teams(LEAGUE, rosters, users)
    orphan = teams.set_index("roster_id").loc[5]
    assert len(teams) == 12
    assert pd.isna(orphan["owner_id"]) and pd.isna(orphan["display_name"]) and pd.isna(orphan["team_name"])


# --- team_weeks ---

MEDIAN_LEAGUE = {"season": "2026", "settings": {"playoff_week_start": 15, "league_average_match": 1}}
NO_MEDIAN_LEAGUE = {"season": "2026", "settings": {"playoff_week_start": 15, "league_average_match": 0}}


def game(roster_id, matchup_id, points):
    return {"roster_id": roster_id, "matchup_id": matchup_id, "points": points}


@pytest.fixture
def week_1():
    return json.loads((FIXTURES / "matchups_week_01.json").read_text(encoding="utf-8"))


def test_week_1_fixture_invariants(week_1):
    tw = build_team_weeks(MEDIAN_LEAGUE, {1: week_1})
    assert list(tw.columns) == TEAM_WEEKS_COLUMNS
    assert len(tw) == 12 and tw["roster_id"].is_unique
    assert (tw["result"] == "W").sum() == 6 and (tw["result"] == "L").sum() == 6
    assert (tw["median_result"] == "W").sum() == 6  # 12 teams: 6 above the median, 6 below
    assert (tw["margin"].sum()) == pytest.approx(0)  # every margin is offset by its opponent's
    paired = tw.set_index("roster_id")
    for row in tw.itertuples():
        opp = paired.loc[row.opponent_roster_id]
        assert opp.opponent_roster_id == row.roster_id and opp.points == row.opponent_points
    assert not tw["is_playoff"].any()


def test_tie_and_margin():
    tw = build_team_weeks(NO_MEDIAN_LEAGUE, {3: [game(1, 1, 100.0), game(2, 1, 100.0), game(3, 2, 90.5), game(4, 2, 80.25)]})
    r = tw.set_index("roster_id")
    assert r.loc[1, "result"] == "T" and r.loc[2, "result"] == "T"
    assert r.loc[3, "result"] == "W" and r.loc[3, "margin"] == 10.25
    assert r.loc[4, "result"] == "L" and r.loc[4, "margin"] == -10.25


def test_no_median_column_when_league_has_no_median_game():
    tw = build_team_weeks(NO_MEDIAN_LEAGUE, {1: [game(1, 1, 100.0), game(2, 1, 90.0)]})
    assert "median_result" not in tw.columns


def test_playoff_week_with_bye():
    week = [game(1, 1, 120.0), game(2, 1, 110.0), game(3, None, 130.0), game(4, None, 70.0)]
    tw = build_team_weeks(MEDIAN_LEAGUE, {15: week})
    r = tw.set_index("roster_id")
    assert tw["is_playoff"].all()
    assert pd.isna(r.loc[3, "opponent_roster_id"]) and pd.isna(r.loc[3, "result"]) and pd.isna(r.loc[3, "margin"])
    assert pd.isna(r.loc[3, "matchup_id"])
    assert tw["median_result"].isna().all()  # no median game in the playoffs (assumption)


def test_median_tie_stops_the_run():
    week = [game(1, 1, 100.0), game(2, 1, 110.0), game(3, 2, 110.0), game(4, 2, 120.0), game(5, 3, 110.0), game(6, 3, 90.0)]
    with pytest.raises(ValueError, match="median"):
        build_team_weeks(MEDIAN_LEAGUE, {2: week})


def test_unpaired_matchup_stops_the_run():
    with pytest.raises(ValueError, match="matchup_id 2 has 1 team"):
        build_team_weeks(NO_MEDIAN_LEAGUE, {1: [game(1, 1, 100.0), game(2, 1, 90.0), game(3, 2, 80.0)]})


def test_save_table_writes_lists_as_json(rosters, tmp_path):
    rosters[0]["co_owners"] = ["999"]
    teams = build_teams(LEAGUE, rosters, make_users(rosters))
    path = save_table(teams, "teams", processed_dir=tmp_path)
    saved = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    assert list(saved.columns) == TEAMS_COLUMNS
    assert json.loads(saved.loc[0, "co_owners"]) == ["999"]
    assert saved.loc[1, "co_owners"] == "[]"
    assert saved.loc[0, "owner_id"] == rosters[0]["owner_id"]
