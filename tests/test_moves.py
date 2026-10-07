"""The Roster moves section (UI_GUIDE.md "Roster moves"; metrics in METRICS_SPEC.md section 9): its view, week by week,
on the hand-built league from test_transactions (every number worked out by hand) and on the saved 2025 tables,
plus the rendered section on 2025's page. No network.
"""

import pandas as pd
import pytest

from sleeper_dash.config import load_config
from sleeper_dash.dashboard import build
from sleeper_dash.dashboard.build import build_view, render
from sleeper_dash.dashboard.moves import PICKUPS_LEFT_OUT, TOP_PICKUPS, TRADES_SHOWN, moves_view
from sleeper_dash.metrics import transactions as tx
from sleeper_dash.transform import PROCESSED_DIR
from sleeper_dash.validate import load_tables
from test_dashboard import RUN
from test_page import parse, week_nodes
from test_transactions import PARAMS, league

NAMES = {1: "One", 2: "Two", 3: "Three", 4: "Four"}
METRICS = {"transactions": PARAMS}
LAST_REGULAR = 4


@pytest.fixture
def hand_built():
    team_weeks, player_weeks, moves, assets = league()
    built = tx.build_transaction_tables(team_weeks, player_weeks, moves, assets, PARAMS)
    return {"start_credits": built["start_credits"], "pickups": built["pickups"], "trades": built["trades"],
            "metrics_season": built["season"]}


def view(tables, week):
    return moves_view(tables, NAMES, week, LAST_REGULAR, METRICS)


def test_week_by_week_the_section_shows_what_had_happened_by_then(hand_built):
    first = view(hand_built, 1)
    assert first["pickups"] == [{"player": "Player C", "team": "Three", "how": "free agent, week 1", "starts": "1 start",
                                 "points": "11.0"}]
    assert first["faab"] == [] and first["trades"] == []                   # nobody has bid or traded yet
    third = view(hand_built, 3)
    assert [p["player"] for p in third["pickups"]] == ["Player C", "Player A"]  # 36.0, then A's 12.0 for team 2
    assert third["pickups"][1]["how"] == "waivers, $12, week 2"
    assert third["trades"] == [{"week": 3, "result": "Two ahead by 13.0", "sides": [
        {"roster_id": 1, "team": "One", "got": "Player A", "points": "0.0"},
        {"roster_id": 2, "team": "Two", "got": "Player B and $5", "points": "13.0"}]}]


def test_after_the_regular_season_trades_are_won_and_playoff_weeks_change_nothing(hand_built):
    last, playoff = view(hand_built, 4), view(hand_built, 5)
    assert last["trades"][0]["result"] == "Two won by 13.0"
    assert [s["points"] for s in last["trades"][0]["sides"]] == ["14.0", "27.0"]
    assert last["subtitle"] == "Points each move has put in the starting lineup this regular season."
    assert playoff["subtitle"] == ("Points each move has put in the starting lineup in the regular season; "
                                   "playoff weeks don't count.")
    assert {k: v for k, v in playoff.items() if k != "subtitle"} == {k: v for k, v in last.items() if k != "subtitle"}


def test_faab_rows_show_points_per_dollar_from_the_minimum_spend_and_dashes_below_it(hand_built):
    rows = view(hand_built, 4)["faab"]
    assert rows[0] == {"team": "Two", "spent": "$12", "points": "12.0", "per_dollar": "1.0"}
    assert {r["team"]: r["per_dollar"] for r in rows[1:]} == {"One": "—", "Three": "—", "Four": "—"}
    assert next(r for r in rows if r["team"] == "Four")["spent"] == "$3"
    assert view(hand_built, 4)["min_spend"] == "$10"


def test_even_trades_and_sides_that_received_nothing_are_worded_plainly(hand_built):
    trades = hand_built["trades"].copy()
    trades.loc[trades["roster_id"] == 1, ["players", "faab_received"]] = [None, 0]
    no_credits = hand_built["start_credits"][hand_built["start_credits"]["source"] != "trade"]
    card = view({**hand_built, "trades": trades, "start_credits": no_credits}, 4)["trades"][0]
    assert card["result"] == "Even" and card["sides"][0]["got"] == "nothing"
    assert view({**hand_built, "trades": trades, "start_credits": no_credits}, 3)["trades"][0]["result"] == "Even so far"


@pytest.mark.parametrize("position", ["K", "DEF"])
def test_kickers_and_defenses_are_left_out_of_best_pickups_but_not_out_of_faab(hand_built, position):
    _, player_weeks, _, _ = league()
    positions = player_weeks.assign(position=player_weeks["player_id"].map({"C": position}).fillna("WR"))
    everyone, filtered = view(hand_built, 3), view({**hand_built, "player_weeks": positions}, 3)
    assert [p["player"] for p in everyone["pickups"]] == ["Player C", "Player A"]
    assert [p["player"] for p in filtered["pickups"]] == ["Player A"]          # C, team 3's free agent, is a K or DEF
    assert filtered["faab"] == everyone["faab"] and filtered["trades"] == everyone["trades"]


def test_the_section_is_hidden_until_there_is_a_move_to_show(hand_built):
    quiet = {"start_credits": hand_built["start_credits"][hand_built["start_credits"]["source"] == "draft"],
             "pickups": hand_built["pickups"].iloc[0:0], "trades": hand_built["trades"].iloc[0:0],
             "metrics_season": hand_built["metrics_season"].assign(faab_spent=0)}
    assert view(quiet, 4) is None
    assert view({"metrics_season": hand_built["metrics_season"]}, 4) is None  # tables not built (older saves)


# --- the saved 2025 season --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def season_2025():
    saved = load_tables(PROCESSED_DIR, names=build.TABLES)
    return {n: t[t["season"] == 2025].reset_index(drop=True) for n, t in saved.items() if "season" in t.columns}


def test_2025_matches_the_saved_tables_every_week(season_2025):
    t = season_2025
    names = t["teams"].set_index("roster_id")["team_name"].to_dict()
    credits, pickups, season = t["start_credits"], t["pickups"], t["metrics_season"]
    for week in range(1, 18):
        v = moves_view(t, names, week, 14, load_config().metrics)
        cutoff = min(week, 14)
        so_far = credits[credits["week"] <= cutoff]
        # Best pickups: the top scorers among regular-season pickups made by then, from the credits.
        earned = so_far[so_far["source"].isin(["waiver", "free_agent"])].groupby(["transaction_id", "player_id"])["points"].sum()
        made = pickups[pickups["week"] <= cutoff].set_index(["transaction_id", "player_id"]).index
        position = t["player_weeks"].drop_duplicates("player_id").set_index("player_id")["position"]
        expected = sorted((p for k, p in earned.items() if k in made and p > 0 and position.get(k[1]) not in PICKUPS_LEFT_OUT),
                          reverse=True)[:TOP_PICKUPS]
        assert [p["points"] for p in v["pickups"]] == [f"{p:.1f}" for p in expected], f"week {week}"
        # FAAB: one row per team, straight from metrics_season.
        rows = season[season["through_week"] == week].set_index("roster_id")
        by_team = {r["team"]: r for r in v["faab"]}
        for rid, r in rows.iterrows():
            shown = by_team[names[rid]]
            assert shown["spent"] == f"${int(r.faab_spent)}" and shown["points"] == f"{r.waiver_points:.1f}"
            assert shown["per_dollar"] == (f"{r.faab_points_per_dollar:.1f}" if pd.notna(r.faab_points_per_dollar) else "—")
        # Trades: made by then, newest first, three shown; each side's points from the trade's credits.
        made_trades = t["trades"][t["trades"]["week"] <= cutoff]
        cards = v["trades"] + v["earlier_trades"]
        assert len(cards) == made_trades["transaction_id"].nunique() and len(v["trades"]) == min(TRADES_SHOWN, len(cards))
        assert [c["week"] for c in cards] == sorted([c["week"] for c in cards], reverse=True)
        traded = so_far[so_far["source"] == "trade"].groupby("roster_id")["points"].sum()
        for rid in names:
            shown = sum(float(s["points"]) for c in cards for s in c["sides"] if s["roster_id"] == rid)
            assert shown == pytest.approx(traded.get(rid, 0.0), abs=0.05 * len(cards)), f"week {week}, roster {rid}"


def test_2025s_page_draws_the_section_after_the_charts_with_every_week_in_its_template(season_2025):
    stacked = load_tables(PROCESSED_DIR, names=build.TABLES)
    weeks = list(range(1, 18))
    html = render(build_view(stacked, {**RUN, "season": 2025, "weeks": weeks}, load_config().metrics))
    nodes = week_nodes(parse(html))
    for week, node in nodes.items():
        section = node.one("section", "moves-section")
        assert section.one("h2").text() == "Roster moves"
        lists = section.all("ol", "pickups")
        if week == 1:  # every pickup that had scored by week 1 was a kicker or defense: no Best pickups block
            assert lists == [] and "Best pickups" not in section.text()
        else:
            assert 1 <= len(lists[0].all("li")) <= TOP_PICKUPS
        assert len(section.one("table", "faab").one("tbody").all("tr")) == 12
    final = nodes[17].one("section", "moves-section")
    assert len(final.one("ol", "pickups").all("li")) == TOP_PICKUPS
    assert len(final.all("li", "trade")) == 21 and final.one("details", "earlier").one("summary").text() == "Earlier trades (18)"
    assert all(" won by " in li.one("p", "trade-result").text() or li.one("p", "trade-result").text() == "Even"
               for li in final.all("li", "trade"))
    assert html.index('class="moves-section"') > html.index('id="fig-rank-history-17"')


def test_how_this_works_explains_roster_moves_with_the_configured_minimum_spend():
    from sleeper_dash.dashboard.explainer import sections

    config = load_config()
    league = {"teams": 12, "median_game": True, "playoff_week_start": 15, "playoff_teams": 6}
    params = {**config.metrics, "transactions": {"min_faab_spend": 25}}
    moves = next(s for s in sections(params, league) if s["heading"] == "Roster moves")
    assert "once a team has spent $25." in moves["paragraphs"][1]
    headings = [s["heading"] for s in sections(config.metrics, league)]
    assert headings.index("Roster moves") == headings.index("Why past weeks can change") - 1
