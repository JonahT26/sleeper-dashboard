"""The Playoffs section (Phase 5; UI_GUIDE.md "Playoffs"): Sleeper's winners bracket as of a playoff week.

Pure: tables in, plain values and formatted strings out. Shown only in playoff weeks. The bracket table is
Sleeper's latest snapshot, so each week shows only what was known by then: round r is played in week
playoff_week_start + r − 1 (the verified format: one week per round, no reseeding, METRICS_SPEC.md section 8),
a team reaches a later round's slot only once the game that sends it there has been played, and a result
shows only from its round's week. Seeds are our seeding of the final regular-season standings (wins, then
points for), which the pipeline's "Seeding matches Sleeper's bracket" check compares with Sleeper's.
Points are each team's score that week from team_weeks; the winner is Sleeper's.
"""

import pandas as pd

from sleeper_dash.metrics.playoff_odds import BYES, seeding, standings_through

ROUND_NAMES = {1: "First round", 2: "Semifinals", 3: "Final"}
PLACE_NAMES = {3: "Third place game", 5: "Fifth place game"}  # the final (place 1) is its round's main game


def _source(value):
    """('W', 3) for "W3", or None for a seeded slot."""
    return (value[0], int(value[1:])) if isinstance(value, str) and value[:1] in ("W", "L") else None


def bracket_view(bracket, team_weeks, names, league, week):
    """Everything the Playoffs section shows for `week`, or None outside the playoffs (the section is hidden).

    bracket: one season's winners_bracket rows. team_weeks: that season's team_weeks. names: {roster_id: team name}.
    league: the run record's league settings (playoff_week_start).
    """
    start = league.get("playoff_week_start")
    if bracket is None or bracket.empty or start is None or week < start:
        return None
    games = {int(g.matchup_id): g for g in bracket.itertuples()}
    regular = team_weeks[~team_weeks["is_playoff"].astype(bool)]
    seed = {roster: i + 1 for i, roster in enumerate(seeding(standings_through(regular, start - 1)))}
    points = team_weeks.set_index(["week", "roster_id"])["points"]

    def round_week(game):
        return start + int(game.round) - 1

    def team_in(game, slot):
        """The roster in slot 1 or 2 as of `week`, or None while the game that sends it there is still to be played."""
        roster, source = getattr(game, f"t{slot}_roster_id"), _source(getattr(game, f"t{slot}_from"))
        if pd.isna(roster) or (source and round_week(games[source[1]]) > week):
            return None
        return int(roster)

    def possible_seeds(game, slot):
        """Seeds that can still fill a slot: its team's seed once known, otherwise every seed in the game it comes from."""
        roster = team_in(game, slot)
        if roster is not None:
            return [seed[roster]]
        source = _source(getattr(game, f"t{slot}_from"))
        return sorted(possible_seeds(games[source[1]], 1) + possible_seeds(games[source[1]], 2)) if source else []

    def label(game):
        """'4 v 5', or '1 v 4/5' when a slot is still open."""
        return " v ".join("/".join(str(s) for s in possible_seeds(game, slot)) for slot in (1, 2))

    def slot_view(game, slot, played):
        roster = team_in(game, slot)
        if roster is None:
            kind, source = _source(getattr(game, f"t{slot}_from"))
            return {"open": True, "text": f"{'Winner' if kind == 'W' else 'Loser'} of {label(games[source])}"}
        score = points.get((round_week(game), roster)) if played else None
        won = (int(game.winner_roster_id) == roster) if played and pd.notna(game.winner_roster_id) else None
        return {"open": False, "seed": seed[roster], "team": names[roster],
                "points": None if score is None or pd.isna(score) else f"{score:.1f}", "won": won}

    rounds = []
    for number in sorted(int(r) for r in bracket["round"].unique()):
        in_round = [g for g in games.values() if int(g.round) == number]
        in_round.sort(key=lambda g: (pd.notna(g.place) and int(g.place) != 1, g.place if pd.notna(g.place) else 0, g.matchup_id))
        played = round_week(in_round[0]) <= week
        cards = [{"label": PLACE_NAMES.get(int(g.place)) if pd.notna(g.place) else None,
                  "slots": [slot_view(g, 1, played), slot_view(g, 2, played)]} for g in in_round]
        byes = []
        if number == 1:  # seeds 1 and 2 wait in round 2's seeded slots
            byes = sorted(({"seed": seed[int(roster)], "team": names[int(roster)]}
                           for g in games.values() if int(g.round) == 2
                           for roster, source in ((g.t1_roster_id, g.t1_from), (g.t2_roster_id, g.t2_from))
                           if pd.notna(roster) and _source(source) is None), key=lambda b: b["seed"])
        rounds.append({"name": ROUND_NAMES.get(number, f"Round {number}"), "week": start + number - 1,
                       "played": played, "games": cards, "byes": byes})

    final = next((g for g in games.values() if pd.notna(g.place) and int(g.place) == 1), None)
    champion = None
    if final is not None and round_week(final) <= week and pd.notna(final.winner_roster_id):
        champion = {"team": names[int(final.winner_roster_id)], "seed": seed[int(final.winner_roster_id)]}
    return {"subtitle": f"Seeded by the final regular-season standings, one round a week. "
                        f"The top {BYES} seeds skip the first round.",
            "champion": champion, "rounds": rounds}
