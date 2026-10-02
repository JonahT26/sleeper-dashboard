"""Tests for the teams table, built from the anonymised rosters fixture plus made-up users."""

import json
from pathlib import Path

import pandas as pd
import pytest

from sleeper_dash.transform import TEAMS_COLUMNS, build_teams, save_table

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


def test_save_table_writes_lists_as_json(rosters, tmp_path):
    rosters[0]["co_owners"] = ["999"]
    teams = build_teams(LEAGUE, rosters, make_users(rosters))
    path = save_table(teams, "teams", processed_dir=tmp_path)
    saved = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    assert list(saved.columns) == TEAMS_COLUMNS
    assert json.loads(saved.loc[0, "co_owners"]) == ["999"]
    assert saved.loc[1, "co_owners"] == "[]"
    assert saved.loc[0, "owner_id"] == rosters[0]["owner_id"]
