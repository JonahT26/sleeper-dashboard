"""Tests for the weekly awards (METRICS_SPEC.md section 7). All data is hand-built."""

import pandas as pd
import pytest

from sleeper_dash.metrics.awards import AWARD_NAMES, AWARDS_COLUMNS, build_awards, check_params, ordinal
from sleeper_dash.transform import build_team_weeks
from sleeper_dash.validate import check_awards

ALL_AWARDS = {"enabled": list(AWARD_NAMES)}
LEAGUE = {"season": "2026", "settings": {"playoff_week_start": 15, "league_average_match": 0}}
TEAMS = pd.DataFrame({"roster_id": [1, 2, 3, 4], "team_name": ["Team One", "Team Two", "Team Three", "Team Four"]})


def make_team_weeks(scores_and_pairs, week=1, league=LEAGUE):
    """scores_and_pairs: {roster_id: (points, matchup_id or None)}."""
    records = [{"roster_id": r, "matchup_id": m, "points": p} for r, (p, m) in scores_and_pairs.items()]
    return build_team_weeks(league, {week: records})


# Week 1: Team One 150 beat Team Two 100 (by 50); Team Four 130 beat Team Three 120 (by 10).
WEEK_1 = {1: (150.0, 1), 2: (100.0, 1), 3: (120.0, 2), 4: (130.0, 2)}


def make_lineups(team_weeks, lost):
    """lost: {roster_id: points left on the bench}."""
    frame = team_weeks[["season", "week", "roster_id", "points"]].copy()
    frame["bench_points_lost"] = frame["roster_id"].map(lost).astype(float)
    frame["efficiency"] = frame["points"] / (frame["points"] + frame["bench_points_lost"])
    return frame.drop(columns="points")


def make_players(rows, week=1):
    """rows: (roster_id, player_id, name, points, is_starter[, is_empty_slot])."""
    return pd.DataFrame([{"season": 2026, "week": week, "roster_id": r[0], "player_id": r[1], "full_name": r[2],
                          "points": r[3], "is_starter": r[4], "is_empty_slot": r[5] if len(r) > 5 else False} for r in rows])


def make_moves(rows):
    """rows: (transaction_id, week, type, roster_id, player_id, action, created_at[, is_preseason])."""
    return pd.DataFrame([{"transaction_id": r[0], "season": 2026, "week": r[1], "type": r[2], "roster_id": r[3], "player_id": r[4],
                          "action": r[5], "created_at": pd.Timestamp(r[6], tz="America/New_York"),
                          "is_preseason": r[7] if len(r) > 7 else False} for r in rows],
                        columns=["transaction_id", "season", "week", "type", "roster_id", "player_id", "action", "created_at", "is_preseason"])


PLAYERS = make_players([
    (1, "p1", "Star Back", 41.26, True), (1, "p2", "Bench Guy", 12.0, False),
    (2, "p3", "Waiver Wideout", 24.14, True), (2, "p4", "Benched Stud", 30.0, False),
    (3, "p5", "Trade Target", 28.0, True), (3, "p6", "Drafted Guy", 20.0, True),
    (4, "p7", "Twice Moved", 26.0, True), (4, "p8", "Free Agent Kicker", 9.0, True),
])
MOVES = make_moves([
    ("t1", 1, "waiver", 2, "p3", "add", "2026-09-10 03:00"),           # Team Two claimed p3 off waivers
    ("t2", 1, "trade", 3, "p5", "add", "2026-09-11 12:00"),            # Team Three traded for p5: not a pickup
    ("t3", 1, "waiver", 1, "p7", "add", "2026-09-10 03:00"),           # Team One claimed p7 ...
    ("t4", 1, "trade", 4, "p7", "add", "2026-09-12 12:00"),            # ... then traded him to Team Four: a trade, not a pickup
    ("t5", 1, "free_agent", 4, "p8", "add", "2026-09-01 12:00", True), # preseason free-agent add
])


def awards_for(team_weeks=None, lost=None, players=PLAYERS, moves=MOVES, params=ALL_AWARDS):
    team_weeks = make_team_weeks(WEEK_1) if team_weeks is None else team_weeks
    lineups = make_lineups(team_weeks, lost or {1: 0.0, 2: 30.0, 3: 5.5, 4: 0.0})
    return build_awards(team_weeks, lineups, players, moves, TEAMS, params)


def only(awards, key):
    rows = awards[awards["award"] == key]
    assert len(rows) == 1, f"{key}: {len(rows)} rows"
    return rows.iloc[0]


# --- Each award's winner, value, and caption ----------------------------------------------------

def test_score_and_matchup_awards():
    a = awards_for()
    assert (only(a, "top_score")["roster_id"], only(a, "top_score")["caption"]) == (1, "Put up 150.0, the best of the week.")
    assert (only(a, "lowest_score")["roster_id"], only(a, "lowest_score")["caption"]) == (2, "Managed 100.0. Everyone else did better.")
    assert (only(a, "heartbreaker")["roster_id"], only(a, "heartbreaker")["caption"]) == (3, "Scored 120.0, 3rd-best of the week, and still lost.")
    assert (only(a, "robbery")["roster_id"], only(a, "robbery")["caption"]) == (4, "Won with 130.0, the 2nd-best score.")
    assert (only(a, "blowout")["roster_id"], only(a, "blowout")["value"], only(a, "blowout")["caption"]) == (1, 50.0, "Beat Team Two by 50.0.")
    assert (only(a, "nail_biter")["roster_id"], only(a, "nail_biter")["caption"]) == (4, "Edged Team Three by 10.0.")


def test_lineup_awards():
    a = awards_for()
    assert (only(a, "bench_blunder")["roster_id"], only(a, "bench_blunder")["caption"]) == (2, "Left 30.0 points on the bench.")
    perfect = only(a, "perfect_lineup")                                # Teams One and Four were both perfect
    assert perfect["roster_id"] == 1 and perfect["value"] == 1.0       # tiebreak: higher points
    assert perfect["caption"] == "Started the best possible lineup: 100%."


def test_bench_blunder_tiebreak_is_lower_efficiency():
    a = awards_for(lost={1: 20.0, 2: 20.0, 3: 0.0, 4: 0.0})           # Team Two scored less, so its efficiency is lower
    assert only(a, "bench_blunder")["roster_id"] == 2


def test_nobody_wins_bench_blunder_when_every_lineup_was_perfect():
    a = awards_for(lost={1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0})
    assert "bench_blunder" not in set(a["award"])


def test_mvp_is_the_top_starter_not_a_benched_player():
    mvp = only(awards_for(), "mvp")
    assert (mvp["roster_id"], mvp["player_id"], mvp["value"]) == (1, "p1", 41.26)
    assert mvp["caption"] == "Star Back scored 41.3."                  # 1 decimal place


def test_pickup_rules():
    # Candidates who started: p3 (waiver, 24.14) qualifies; p5 (trade) does not; p6 (drafted) does not;
    # p7 (waiver, then traded: latest acquisition is a trade) does not; p8 (preseason free agent) qualifies.
    pickup = only(awards_for(), "pickup_of_the_week")
    assert (pickup["roster_id"], pickup["player_id"]) == (2, "p3")
    assert pickup["caption"] == "Waiver Wideout, added off waivers in week 1, scored 24.1."


def test_preseason_and_free_agent_pickup_caption():
    players = PLAYERS[PLAYERS["player_id"] != "p3"]
    pickup = only(awards_for(players=players), "pickup_of_the_week")
    assert pickup["caption"] == "Free Agent Kicker, added as a free agent before the season, scored 9.0."


def test_a_player_added_mid_week_counts_for_that_week():
    moves = pd.concat([MOVES, make_moves([("t6", 2, "free_agent", 3, "p9", "add", "2026-09-19 12:00")])])  # Saturday add
    team_weeks = make_team_weeks(WEEK_1, week=2)
    players = make_players([(3, "p9", "Saturday Pickup", 35.0, True), (1, "p1", "Star Back", 20.0, True)], week=2)
    pickup = only(awards_for(team_weeks=team_weeks, players=players, moves=moves), "pickup_of_the_week")
    assert pickup["caption"] == "Saturday Pickup, added as a free agent in week 2, scored 35.0."


def test_asleep_at_the_wheel_counts_zero_starters_including_empty_slots():
    players = pd.concat([PLAYERS, make_players([(3, "0", None, 0.0, True, True), (3, "p10", "No Show", 0.0, True),
                                                (2, "p11", "Also Out", 0.0, True)])])
    asleep = only(awards_for(players=players), "asleep_at_the_wheel")
    assert (asleep["roster_id"], asleep["value"], asleep["caption"]) == (3, 2.0, "Started 2 players who scored 0.")
    assert "asleep_at_the_wheel" not in set(awards_for()["award"])     # only awarded when someone started a zero


# --- Ties, playoffs, and the head-to-head tie rule ----------------------------------------------

def test_exact_ties_give_co_winners():
    team_weeks = make_team_weeks({1: (150.0, 1), 2: (100.0, 1), 3: (150.0, 2), 4: (130.0, 2)})
    tops = awards_for(team_weeks=team_weeks)
    tops = tops[tops["award"] == "top_score"]
    assert sorted(tops["roster_id"]) == [1, 3] and (tops["value"] == 150.0).all()


def test_a_tied_game_makes_neither_team_eligible_for_matchup_awards():
    team_weeks = make_team_weeks({1: (110.0, 1), 2: (110.0, 1), 3: (120.0, 2), 4: (130.0, 2)})
    a = awards_for(team_weeks=team_weeks)
    for key in ("heartbreaker", "robbery", "blowout", "nail_biter"):
        assert not set(a.loc[a["award"] == key, "roster_id"]) & {1, 2}
    assert only(a, "heartbreaker")["roster_id"] == 3 and only(a, "robbery")["roster_id"] == 4


def test_playoff_week_matchup_awards_skip_teams_without_a_game():
    playoffs = {**LEAGUE, "settings": {**LEAGUE["settings"], "playoff_week_start": 1}}
    team_weeks = make_team_weeks({1: (150.0, None), 2: (100.0, None), 3: (120.0, 1), 4: (130.0, 1)}, league=playoffs)
    a = awards_for(team_weeks=team_weeks)
    assert only(a, "top_score")["roster_id"] == 1                      # score awards: every team
    assert only(a, "blowout")["roster_id"] == 4 and only(a, "heartbreaker")["roster_id"] == 3


def test_matchup_awards_are_skipped_when_nobody_played():
    team_weeks = make_team_weeks({1: (150.0, None), 2: (100.0, None), 3: (120.0, None), 4: (130.0, None)})
    a = awards_for(team_weeks=team_weeks)
    assert not {"heartbreaker", "robbery", "blowout", "nail_biter"} & set(a["award"])


# --- Config, output, copy, validation -----------------------------------------------------------

def test_only_enabled_awards_appear_in_config_order():
    a = awards_for(params={"enabled": ["mvp", "top_score", "blowout"]})
    assert a["award"].tolist() == ["mvp", "top_score", "blowout"]
    assert list(a.columns) == AWARDS_COLUMNS


@pytest.mark.parametrize("enabled, message", [(["top_score", "closest_game"], "unknown"), ([], "list"), (["mvp", "mvp"], "twice")])
def test_bad_award_config_stops_the_run(enabled, message):
    with pytest.raises(ValueError, match=message):
        check_params({"enabled": enabled})


def test_ordinals():
    assert [ordinal(n) for n in (1, 2, 3, 4, 10, 11, 12, 13, 21, 22, 23)] == \
        ["1st", "2nd", "3rd", "4th", "10th", "11th", "12th", "13th", "21st", "22nd", "23rd"]


def test_copy_rules():
    a = awards_for()
    assert a["award_name"].map(lambda s: s == "MVP" or (s[0].isupper() and s[1:] == s[1:].lower())).all()   # sentence case
    assert a["caption"].str.endswith(".").all()
    assert not a["caption"].str.contains(r"\d+\.\d{2}").any()                                                 # never 2 decimals


def test_validation_passes_and_catches_wrong_winners():
    team_weeks = make_team_weeks(WEEK_1)
    lineups = make_lineups(team_weeks, {1: 0.0, 2: 30.0, 3: 5.5, 4: 0.0})
    a = build_awards(team_weeks, lineups, PLAYERS, MOVES, TEAMS, ALL_AWARDS)
    assert check_awards(a, team_weeks, lineups).passed
    broken = a.copy()
    broken.loc[broken["award"] == "robbery", "roster_id"] = 1       # Team One won, but with the top score
    broken.loc[broken["award"] == "top_score", "value"] = 140.0
    detail = check_awards(broken, team_weeks, lineups).detail
    assert "is not this team's score" in detail and "not the week's top score" in detail
