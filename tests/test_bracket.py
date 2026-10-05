"""The Playoffs section's view (UI_GUIDE.md "Playoffs"), tested on the six finished brackets in data/processed/
(2020-2025, committed, so these run anywhere) and on a synthetic bracket that Sleeper hasn't filled in. No network.

Each playoff week shows only what was known by then: results from the rounds played so far, teams only once
the game that sends them on has been played, and the champion only after the final.
"""

import pandas as pd
import pytest

from sleeper_dash.dashboard import build
from sleeper_dash.dashboard.bracket import bracket_view
from sleeper_dash.metrics.playoff_odds import seeding, standings_through
from sleeper_dash.transform import PROCESSED_DIR
from sleeper_dash.validate import load_tables

FINISHED = list(range(2020, 2026))


@pytest.fixture(scope="module")
def saved():
    return load_tables(PROCESSED_DIR, names=build.TABLES)


def season_of(saved, season):
    """(bracket, team_weeks, names, league settings, seed by roster) for one saved season."""
    pick = {n: t[t["season"] == season].reset_index(drop=True) for n, t in saved.items() if "season" in t.columns}
    team_weeks = pick["team_weeks"]
    start = int(team_weeks.loc[team_weeks["is_playoff"].astype(bool), "week"].min())
    names = pick["teams"].set_index("roster_id")["team_name"].to_dict()
    seeds = seeding(standings_through(team_weeks, start - 1))
    return pick["winners_bracket"], team_weeks, names, {"playoff_week_start": start}, {r: i + 1 for i, r in enumerate(seeds)}


def filled(slot):
    return (slot["seed"], slot["team"], slot["points"], slot["won"])


@pytest.mark.parametrize("season", FINISHED)
def test_hidden_before_the_playoffs(saved, season):
    bracket, team_weeks, names, league, _ = season_of(saved, season)
    assert bracket_view(bracket, team_weeks, names, league, league["playoff_week_start"] - 1) is None
    assert bracket_view(bracket.iloc[0:0], team_weeks, names, league, league["playoff_week_start"]) is None


@pytest.mark.parametrize("season", FINISHED)
def test_after_the_final_every_game_shows_sleepers_winner_and_that_weeks_scores(saved, season):
    bracket, team_weeks, names, league, seed = season_of(saved, season)
    start = league["playoff_week_start"]
    view = bracket_view(bracket, team_weeks, names, league, start + 2)
    points = team_weeks.set_index(["week", "roster_id"])["points"]
    assert [(r["name"], r["week"], r["played"]) for r in view["rounds"]] == [
        ("First round", start, True), ("Semifinals", start + 1, True), ("Final", start + 2, True)]
    games = {(int(g.round), int(g.t1_roster_id), int(g.t2_roster_id)): g for g in bracket.itertuples()}
    shown = 0
    for number, r in enumerate(view["rounds"], start=1):
        for card in r["games"]:
            (a, b) = card["slots"]
            ids = [next(k for k, v in names.items() if v == s["team"]) for s in (a, b)]
            g = games[(number, *ids)]
            assert card["label"] == {3: "Third place game", 5: "Fifth place game"}.get(g.place)
            for s, rid in zip((a, b), ids):
                assert filled(s) == (seed[rid], names[rid], f"{points[(start + number - 1, rid)]:.1f}", rid == g.winner_roster_id)
            shown += 1
    assert shown == len(bracket) == 7
    # Main games first in each round; the final comes before the third place game.
    assert [c["label"] for c in view["rounds"][1]["games"]] == [None, None, "Fifth place game"]
    assert [c["label"] for c in view["rounds"][2]["games"]] == [None, "Third place game"]
    final = bracket[bracket["place"] == 1].iloc[0]
    assert view["champion"] == {"team": names[int(final.winner_roster_id)], "seed": seed[int(final.winner_roster_id)]}


@pytest.mark.parametrize("season", FINISHED)
def test_the_first_round_is_3_v_6_and_4_v_5_with_seeds_1_and_2_on_a_bye(saved, season):
    bracket, team_weeks, names, league, _ = season_of(saved, season)
    first = bracket_view(bracket, team_weeks, names, league, league["playoff_week_start"])["rounds"][0]
    assert sorted(sorted(s["seed"] for s in card["slots"]) for card in first["games"]) == [[3, 6], [4, 5]]
    assert [b["seed"] for b in first["byes"]] == [1, 2]


@pytest.mark.parametrize("season", FINISHED)
def test_each_week_shows_only_what_was_known_by_then(saved, season):
    bracket, team_weeks, names, league, seed = season_of(saved, season)
    start = league["playoff_week_start"]
    first_week = bracket_view(bracket, team_weeks, names, league, start)
    first, semis, final = first_week["rounds"]
    assert first["played"] and not semis["played"] and not final["played"] and first_week["champion"] is None
    # Semifinals: the bye seeds meet the first-round winners, not yet played, so no scores or winners.
    winners = {seed[int(g.winner_roster_id)] for g in bracket[bracket["round"] == 1].itertuples()}
    losers = {seed[int(g.loser_roster_id)] for g in bracket[bracket["round"] == 1].itertuples()}
    slots = [s for card in semis["games"] for s in card["slots"]]
    assert all(not s["open"] and s["points"] is None and s["won"] is None for s in slots)
    assert {s["seed"] for s in slots} == {1, 2} | winners | losers
    # Final and third place: open slots named by the semifinal they come from.
    semi_seeds = [sorted(s["seed"] for s in card["slots"]) for card in semis["games"][:2]]
    texts = [s["text"] for card in final["games"] for s in card["slots"]]
    assert all(s["open"] for card in final["games"] for s in card["slots"])
    assert sorted(texts) == sorted([f"{kind} of {a} v {b}" for kind in ("Winner", "Loser") for a, b in semi_seeds])
    second_week = bracket_view(bracket, team_weeks, names, league, start + 1)
    assert [r["played"] for r in second_week["rounds"]] == [True, True, False] and second_week["champion"] is None
    assert not any(s["open"] for card in second_week["rounds"][2]["games"] for s in card["slots"])


def test_a_bracket_sleeper_has_not_filled_in_shows_the_seeds_and_open_slots():
    """Sleeper's provisional bracket: round 1 and the byes from the standings, later slots empty, no results."""
    team_weeks = pd.DataFrame([{"week": w, "roster_id": r, "points": 100.0 + r + w, "is_playoff": w >= 3,
                                "result": ("W" if r % 2 else "L") if w < 3 else None, "median_result": None}
                               for w in (1, 2, 3) for r in range(1, 9)])
    names = {r: f"Team {r}" for r in range(1, 9)}
    seed = {r: i + 1 for i, r in enumerate(seeding(standings_through(team_weeks, 2)))}
    by_seed = {s: r for r, s in seed.items()}
    rows = [(1, 1, by_seed[4], by_seed[5], None, None, None), (1, 2, by_seed[3], by_seed[6], None, None, None),
            (2, 3, by_seed[1], None, None, "W1", None), (2, 4, by_seed[2], None, None, "W2", None),
            (2, 5, None, None, "L1", "L2", 5), (3, 6, None, None, "W3", "W4", 1), (3, 7, None, None, "L3", "L4", 3)]
    bracket = pd.DataFrame(rows, columns=["round", "matchup_id", "t1_roster_id", "t2_roster_id", "t1_from", "t2_from", "place"])
    bracket["winner_roster_id"] = bracket["loser_roster_id"] = float("nan")
    view = bracket_view(bracket, team_weeks, names, {"playoff_week_start": 3}, 3)
    first, semis, final = view["rounds"]
    assert all(s["points"] is not None and s["won"] is None for card in first["games"] for s in card["slots"])
    assert [[s["seed"] if not s["open"] else s["text"] for s in card["slots"]] for card in semis["games"]] == [
        [1, "Winner of 4 v 5"], [2, "Winner of 3 v 6"], ["Loser of 4 v 5", "Loser of 3 v 6"]]
    assert [[s["text"] for s in card["slots"]] for card in final["games"]] == [
        ["Winner of 1 v 4/5", "Winner of 2 v 3/6"], ["Loser of 1 v 4/5", "Loser of 2 v 3/6"]]
    assert view["champion"] is None
