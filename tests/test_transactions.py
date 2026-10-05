"""Transactions (METRICS_SPEC.md section 9): the trade_assets table, FAAB balances, start credits, pickups, trades,
and the season-to-date columns, on a small hand-built league whose every number can be worked out by hand, plus
the saved tables for 2020-2026. No network.

The hand-built league: 4 teams, regular season weeks 1-4, playoffs from week 5. Player "A" is drafted by team 1,
dropped in week 2 and claimed by team 2 for $12, then traded back to team 1 in week 3 for player "B" plus $5.
"C" is a free agent team 3 picks up in week 1. Each team starts one player a week who scores 10 + week points.
"""

import pandas as pd
import pytest

from sleeper_dash.metrics import transactions as tx
from sleeper_dash.transform import PROCESSED_DIR, build_trade_assets, faab_balances
from sleeper_dash.validate import check_trade_assets, check_transaction_credits, load_tables

PARAMS = {"min_faab_spend": 10}
LEAGUE = {"season": "2026"}


def stamp(week, hour=0):
    return pd.Timestamp("2026-09-10", tz="America/New_York") + pd.Timedelta(days=7 * (week - 1), hours=hour)


def move(tid, week, kind, roster, player, action, bid=None, hour=0):
    return {"transaction_id": tid, "season": 2026, "week": week, "is_preseason": False, "type": kind, "status": "complete",
            "roster_id": roster, "player_id": player, "player_name": f"Player {player}", "action": action,
            "waiver_bid": bid, "created_at": stamp(week, hour)}


def league():
    moves = pd.DataFrame([
        move("c1", 1, "free_agent", 3, "C", "add"),
        move("w1", 2, "waiver", 1, "A", "drop", hour=1), move("w2", 2, "waiver", 2, "A", "add", bid=12, hour=2),
        move("t1", 3, "trade", 2, "A", "drop"), move("t1", 3, "trade", 1, "A", "add"),
        move("t1", 3, "trade", 1, "B", "drop"), move("t1", 3, "trade", 2, "B", "add"),
        move("w3", 3, "waiver", 4, "D", "add", bid=3),              # $3: below the $10 minimum, never started
        move("w4", 5, "waiver", 4, "E", "add", bid=20),             # a playoff-week claim: not a pickup, not spending
    ]).astype({"waiver_bid": "Int64"})
    assets = pd.DataFrame([
        {"transaction_id": "t1", "season": 2026, "week": 3, "asset_order": 0, "asset": "faab", "sender_roster_id": 1,
         "receiver_roster_id": 2, "faab_amount": 5, "created_at": stamp(3)},
        {"transaction_id": "f1", "season": 2026, "week": 2, "asset_order": 0, "asset": "faab", "sender_roster_id": 3,
         "receiver_roster_id": 4, "faab_amount": 7, "created_at": stamp(2)},   # FAAB only: no outcome
    ]).astype({"faab_amount": "Int64"})
    # Who starts: team 1 starts A in weeks 1 and 4 (drafted, then traded back), team 2 starts Y, then A in week 2,
    # then B (from the trade) in weeks 3-4, team 3 starts C, team 4 starts its drafted player Z. Week 5 is a playoff week.
    starters = {1: {1: "A", 2: "X", 3: "X", 4: "A", 5: "A"}, 2: {1: "Y", 2: "A", 3: "B", 4: "B", 5: "B"},
                3: {w: "C" for w in range(1, 6)}, 4: {w: "Z" for w in range(1, 6)}}
    player_weeks = pd.DataFrame([{"season": 2026, "week": w, "roster_id": r, "player_id": p, "is_starter": True,
                                  "is_empty_slot": False, "points": 10.0 + w}
                                 for r, weeks in starters.items() for w, p in weeks.items()]
                                + [{"season": 2026, "week": 1, "roster_id": 1, "player_id": "0", "is_starter": True,
                                    "is_empty_slot": True, "points": 0.0}])
    team_weeks = pd.DataFrame([{"season": 2026, "week": w, "roster_id": r, "points": 10.0 + w, "is_playoff": w >= 5}
                               for w in range(1, 6) for r in range(1, 5)])
    return team_weeks, player_weeks, moves, assets


@pytest.fixture
def built():
    team_weeks, player_weeks, moves, assets = league()
    return tx.build_transaction_tables(team_weeks, player_weeks, moves, assets, PARAMS), team_weeks


# --- trade_assets and FAAB balances (transform) ------------------------------------------------------

def test_trade_assets_hold_faab_and_picks_from_completed_trades_only():
    trade = {"transaction_id": "9", "type": "trade", "status": "complete", "leg": 4, "created": 1790000000000,
             "waiver_budget": [{"amount": 8, "sender": 5, "receiver": 11}],
             "draft_picks": [{"season": "2027", "round": 2, "roster_id": 3, "previous_owner_id": 5, "owner_id": 11}]}
    others = [{**trade, "transaction_id": "10", "status": "failed"}, {**trade, "transaction_id": "11", "type": "waiver"}]
    assets = build_trade_assets(LEAGUE, {4: [trade, *others]})
    assert assets[["transaction_id", "week", "asset_order", "asset", "sender_roster_id", "receiver_roster_id"]].values.tolist() == [
        ["9", 4, 0, "faab", 5, 11], ["9", 4, 1, "pick", 5, 11]]
    assert assets.loc[0, "faab_amount"] == 8 and pd.isna(assets.loc[1, "faab_amount"])
    assert assets.loc[1, ["pick_season", "pick_round", "pick_original_roster_id"]].tolist() == [2027, 2, 3]
    assert check_trade_assets(assets).passed
    assert not check_trade_assets(assets.assign(receiver_roster_id=5)).passed
    assert not check_trade_assets(assets.assign(faab_amount=pd.array([0, None], dtype="Int64"))).passed


def test_faab_left_counts_bids_and_faab_traded_and_compares_with_sleeper():
    _, _, moves, assets = league()
    rosters = [{"roster_id": r, "settings": {"waiver_budget_used": used}} for r, used in ((1, 5), (2, 7), (3, 7), (4, 16))]
    table = faab_balances(moves, assets, rosters, 100)
    assert table.loc[1, ["spent", "received", "sent", "left", "gap"]].tolist() == [0, 0, 5, 95, 0]
    assert table.loc[2, ["spent", "received", "sent", "left", "gap"]].tolist() == [12, 5, 0, 93, 0]
    assert table.loc[3, ["left", "gap"]].tolist() == [93, 0]
    assert table.loc[4, ["spent", "received", "left", "sleeper_used", "gap"]].tolist() == [23, 7, 84, 16, 0]


# --- start credits ------------------------------------------------------------------------------------

def test_each_regular_season_start_goes_to_the_teams_latest_acquisition(built):
    credits = built[0]["start_credits"].set_index(["week", "roster_id"])
    assert credits.loc[(1, 1), "source"] == "draft"                          # drafted
    assert credits.loc[(2, 2), ["source", "transaction_id"]].tolist() == ["waiver", "w2"]
    assert credits.loc[(4, 1), ["source", "transaction_id"]].tolist() == ["trade", "t1"]  # traded back: the trade, not the draft
    assert credits.loc[(3, 2), ["source", "transaction_id"]].tolist() == ["trade", "t1"]
    assert credits.loc[(1, 3), "source"] == "free_agent"
    assert set(built[0]["start_credits"]["week"]) == {1, 2, 3, 4}           # playoff week 5 earns nothing
    assert "0" not in set(built[0]["start_credits"]["player_id"])           # empty slots aren't credited


def test_pickups_are_regular_season_waiver_and_free_agent_adds_with_their_credits(built):
    pickups = built[0]["pickups"].set_index("transaction_id")
    assert list(pickups.index) == ["c1", "w2", "w3"]                        # w4 is a playoff-week claim
    assert pickups.loc["c1", ["starts", "start_points"]].tolist() == [4, 11 + 12 + 13 + 14]
    assert pickups.loc["w2", ["starts", "start_points", "waiver_bid"]].tolist() == [1, 12.0, 12]
    assert pickups.loc["w3", ["starts", "start_points"]].tolist() == [0, 0.0]


def test_a_trade_side_scores_the_starts_of_the_players_it_received(built):
    trades = built[0]["trades"].set_index("roster_id")
    assert list(built[0]["trades"]["transaction_id"].unique()) == ["t1"]    # the FAAB-only trade has no outcome
    assert trades.loc[1, ["players", "faab_received", "starts", "start_points", "margin", "result"]].tolist() == [
        "Player A", 0, 1, 14.0, 14.0 - 27.0, "lost"]
    assert trades.loc[2, ["players", "faab_received", "starts", "start_points", "margin", "result"]].tolist() == [
        "Player B", 5, 2, 27.0, 13.0, "won"]


def test_a_trade_with_three_teams_stops_the_run():
    team_weeks, player_weeks, moves, assets = league()
    third = pd.DataFrame([move("t1", 3, "trade", 3, "Q", "add")]).astype({"waiver_bid": "Int64"})
    with pytest.raises(ValueError, match="involves 3 teams"):
        tx.build_transaction_tables(team_weeks, player_weeks, pd.concat([moves, third]), assets, PARAMS)


def test_season_columns_build_up_week_by_week_and_hold_through_the_playoffs(built):
    season = built[0]["season"].set_index(["through_week", "roster_id"])
    assert season.loc[(1, 2), ["waiver_points", "faab_spent"]].tolist() == [0.0, 0]
    assert season.loc[(2, 2), ["waiver_points", "faab_spent", "faab_points_per_dollar"]].tolist() == [12.0, 12, 1.0]
    assert pd.isna(season.loc[(4, 4), "faab_points_per_dollar"]) and season.loc[(4, 4, ), "faab_spent"] == 3  # below $10
    assert season.loc[(3, 1), ["trades", "trade_margin"]].tolist() == [1, -13.0]   # week 3: B scored 13 for team 2
    assert season.loc[(4, 1), "trade_margin"] == -13.0 and season.loc[(4, 2), "trade_margin"] == 13.0
    final, playoff = season.xs(4, level="through_week"), season.xs(5, level="through_week")
    assert playoff.equals(final)                                            # the week 5 claim and starts change nothing
    assert season.loc[(4, 3), "pickup_points"] == 50.0


def test_min_faab_spend_must_be_a_number():
    team_weeks, player_weeks, moves, assets = league()
    with pytest.raises(ValueError, match="min_faab_spend"):
        tx.build_transaction_tables(team_weeks, player_weeks, moves, assets, {"min_faab_spend": "ten"})


def test_the_check_passes_and_catches_a_start_credited_twice_or_a_wrong_ratio(built):
    tables, team_weeks = built
    args = (tables["start_credits"], tables["pickups"], tables["trades"], tables["season"], team_weeks)
    assert check_transaction_credits(*args).passed
    doubled = pd.concat([tables["start_credits"], tables["start_credits"].iloc[[0]]])
    assert "credits sum to" in check_transaction_credits(doubled, *args[1:]).detail
    wrong = tables["season"].assign(faab_points_per_dollar=tables["season"]["faab_points_per_dollar"] * 2)
    assert "FAAB efficiency" in check_transaction_credits(*args[:3], wrong, team_weeks).detail
    lopsided = tables["trades"].assign(margin=1.0)
    assert "margins sum to" in check_transaction_credits(args[0], args[1], lopsided, *args[3:]).detail


# --- the saved tables (2020-2026) -------------------------------------------------------------------

@pytest.fixture(scope="module")
def saved():
    return load_tables(PROCESSED_DIR, names=["team_weeks", "player_weeks", "start_credits", "pickups", "trades",
                                             "metrics_season", "trade_assets"])


def test_every_saved_season_credits_each_start_once(saved):
    for season in sorted(saved["team_weeks"]["season"].unique()):
        pick = {n: t[t["season"] == season] for n, t in saved.items()}
        result = check_transaction_credits(pick["start_credits"], pick["pickups"], pick["trades"], pick["metrics_season"],
                                           pick["team_weeks"])
        assert result.passed, f"{season}: {result.detail}"


def test_no_draft_pick_has_ever_been_traded_in_this_league(saved):
    """A redraft league: if one ever appears, trade_assets records it and the spec's note needs revisiting."""
    assets = saved["trade_assets"]
    assert (assets["asset"] == "faab").sum() > 150 and (assets["asset"] == "pick").sum() == 0
