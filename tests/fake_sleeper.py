"""A small, made-up Sleeper league served in place of the real API, so the whole pipeline can run offline.

Six teams; lineup QB, RB, WR, FLEX plus two bench spots; weekly median game on; regular season
weeks 1-5 (a full round robin), playoffs from week 6. Scores are fixed pseudo-random numbers,
so every run sees the same league. Six teams make the playoffs (seeds 1 and 2 on a bye, the format
playoff odds support), so in this league everyone qualifies. `last_scored_leg` says how many weeks Sleeper has scored,
`state` is what /state/nfl reports, and `corrections` changes a player's score after the fact
(a stat correction). Week 1 has one preseason pickup (before the 2026-09-09 start) and one after
it, so a wrong season start date changes the transactions table.

Playoffs: `PlayoffLeague()` is an 8-team version (round robin weeks 1-7, playoffs from week 8, a
6-team winners bracket with byes for seeds 1 and 2, and a consolation game), shaped like what
Sleeper returned for this league's real 2025 playoffs. `behaviours` switches on the other ways
Sleeper might report playoff weeks (see PLAYOFF_BEHAVIOURS), so tests can show what the pipeline
does in each case.

/winners_bracket is built the way Sleeper builds it: seeds from the regular-season standings so far
(wins including the median game, then points for), seeds 3 v 6 and 4 v 5 in round 1, seeds 1 and 2
waiting for those winners in round 2, then the final, 3rd-place and 5th-place games. Like Sleeper's,
it doesn't change once the regular season is over, whatever the roster standings count.
"""

import random
import statistics
from datetime import datetime
from zoneinfo import ZoneInfo

LEAGUE_ID = "1000000000000000000"
SEASON = "2026"
START_DATE = "2026-09-09"
TEAMS = 6
PLAYOFF_WEEK_START = 6
ROSTER_POSITIONS = ["QB", "RB", "WR", "FLEX", "BN", "BN"]
EASTERN = ZoneInfo("America/New_York")
FREE_AGENTS = (("9901", "WR"), ("9902", "RB"))
WEEK_MS = 7 * 24 * 3600 * 1000

# Playoff weeks of the 8-team league: winners-bracket games, consolation games; anyone else has no game.
PLAYOFFS_8 = {
    8: {"winners": [(3, 6), (4, 5)], "consolation": [(7, 8)]},           # seeds 1 and 2 have a bye
    9: {"winners": [(1, 6), (2, 5), (3, 4)], "consolation": [(7, 8)]},   # semifinals, 5th place, consolation
}
# Ways Sleeper might report playoff weeks, beyond what it did in 2025 (the default: none switched on).
PLAYOFF_BEHAVIOURS = {
    "no_consolation_games": "eliminated teams have no matchup_id (no consolation bracket)",
    "no_game_teams_unscored": "teams without a game have an empty lineup and 0 points",
    "no_game_teams_missing": "teams without a game are left out of the matchups response",
    "roster_wins_include_playoff_games": "roster wins/losses count playoff head-to-head games",
    "roster_wins_include_playoff_median": "roster wins/losses also count a median game in playoff weeks",
    "roster_points_include_playoffs": "roster fpts/fpts_against count playoff weeks",
}

# /state/nfl as Sleeper reports it at different times of year. Only IN_SEASON describes 2026 with a date.
IN_SEASON = {"season": "2026", "season_type": "regular", "week": 4, "leg": 4, "season_start_date": START_DATE,
             "previous_season": "2025", "league_season": "2026"}
STATES = {
    "in season (week 4 under way)": IN_SEASON,
    "week 5 under way, week 4 not yet scored": {**IN_SEASON, "week": 5, "leg": 5},
    "off-season, still 2026": {**IN_SEASON, "season_type": "off", "week": 0, "leg": 0},
    "off-season, rolled over to 2027": {"season": "2027", "season_type": "off", "week": 0, "leg": 0,
                                        "season_start_date": None, "previous_season": "2026", "league_season": "2027"},
    "next season's preseason": {"season": "2027", "season_type": "pre", "week": 1, "leg": 1,
                                "season_start_date": "2027-09-08", "previous_season": "2026", "league_season": "2027"},
    "next season under way": {"season": "2027", "season_type": "regular", "week": 3, "leg": 3,
                              "season_start_date": "2027-09-08", "previous_season": "2026", "league_season": "2027"},
    "2026 with no start date": {**IN_SEASON, "season_start_date": None},
}


def _epoch_ms(year, month, day, hour):
    return int(datetime(year, month, day, hour, tzinfo=EASTERN).timestamp() * 1000)


def _round_robin(teams, weeks):
    """Circle-method pairings: {week: [(a, b), ...]} with every team once a week."""
    ids = list(range(1, teams + 1))
    pairings = {}
    for week in range(1, weeks + 1):
        pairings[week] = [(ids[i], ids[-1 - i]) for i in range(teams // 2)]
        ids = [ids[0], ids[-1]] + ids[1:-1]
    return pairings


class FakeSleeper:
    def __init__(self, last_scored_leg=3, state=IN_SEASON, teams=TEAMS, playoff_week_start=PLAYOFF_WEEK_START,
                 playoffs=None, behaviours=()):
        unknown = set(behaviours) - set(PLAYOFF_BEHAVIOURS)
        assert not unknown, f"unknown behaviours {unknown}"
        self.last_scored_leg = last_scored_leg
        self.state = state
        self.teams = teams
        self.playoff_week_start = playoff_week_start
        self.behaviours = set(behaviours)
        self.corrections = {}  # {(week, player_id): points in cents}
        self.pairings = _round_robin(teams, playoff_week_start - 1)
        for week, games in (playoffs or {}).items():
            consolation = [] if "no_consolation_games" in self.behaviours else games["consolation"]
            self.pairings[week] = games["winners"] + consolation
        self.roster_players = {
            r: [f"{r}01", f"{r}02", f"{r}03", f"{r}04", f"{r}05", f"{r}06"] for r in range(1, teams + 1)
        }  # QB, RB, WR, FLEX (RB), bench WR, bench TE
        positions = ["QB", "RB", "WR", "RB", "WR", "TE"]
        self.players = {
            pid: {"player_id": pid, "position": pos, "fantasy_positions": [pos], "full_name": f"Player {pid}",
                  "first_name": "Player", "last_name": pid, "team": "KC"}
            for r, pids in self.roster_players.items() for pid, pos in zip(pids, positions)
        }
        # Two free agents picked up in week 1: one before the season starts, one after.
        for pid, pos in FREE_AGENTS:
            self.players[pid] = {"player_id": pid, "position": pos, "fantasy_positions": [pos],
                                 "full_name": f"Free Agent {pid}", "team": "SF"}
        self.pickups = {  # player_id: (roster_id, transaction)
            "9901": (1, {"transaction_id": "t1", "type": "free_agent", "created": _epoch_ms(2026, 9, 5, 12)}),
            "9902": (2, {"transaction_id": "t2", "type": "waiver", "created": _epoch_ms(2026, 9, 12, 4),
                        "settings": {"waiver_bid": 7}}),
        }

    # --- scores ----------------------------------------------------------------------------------

    def _team_players(self, roster_id):
        extra = [pid for pid, (rid, _) in self.pickups.items() if rid == roster_id]
        return self.roster_players[roster_id] + extra

    def _cents(self, week, player_id):
        if (week, player_id) in self.corrections:
            return self.corrections[(week, player_id)]
        return random.Random(f"{week}-{player_id}").randint(200, 3200)

    def _row(self, week, roster_id, matchup_id, scored):
        players = self._team_players(roster_id)
        cents = {pid: self._cents(week, pid) if scored else 0 for pid in players}
        starters = players[:4]
        return {
            "roster_id": roster_id, "matchup_id": matchup_id,
            "points": sum(cents[p] for p in starters) / 100,
            "starters": starters, "starters_points": [cents[p] / 100 for p in starters],
            "players": players, "players_points": {p: c / 100 for p, c in cents.items()},
            "custom_points": None,
        }

    def _matchups(self, week):
        scored = week <= self.last_scored_leg
        rows = []
        for matchup_id, pair in enumerate(self.pairings[week], start=1):
            rows += [self._row(week, roster_id, matchup_id, scored) for roster_id in pair]
        paired = {r["roster_id"] for r in rows}
        for roster_id in range(1, self.teams + 1):  # playoff weeks: byes and eliminated teams
            if roster_id in paired or "no_game_teams_missing" in self.behaviours:
                continue
            row = self._row(week, roster_id, None, scored)
            if "no_game_teams_unscored" in self.behaviours:
                row.update(points=0.0, starters=[], starters_points=[], players=[], players_points={})
            rows.append(row)
        if scored and week < self.playoff_week_start:
            totals = [round(r["points"] * 100) for r in rows]
            assert len(set(totals)) == len(totals), f"week {week}: equal team scores would make a median tie"
        return sorted(rows, key=lambda r: r["roster_id"])

    def _rosters(self):
        totals = {r: {"wins": 0, "losses": 0, "ties": 0, "pf": 0, "pa": 0} for r in range(1, self.teams + 1)}
        b = self.behaviours
        for week in range(1, self.last_scored_leg + 1):
            playoff = week >= self.playoff_week_start
            rows = {m["roster_id"]: round(m["points"] * 100) for m in self._matchups(week)}
            ordered = sorted(rows.values())
            median = statistics.median(ordered)
            count_results = not playoff or "roster_wins_include_playoff_games" in b
            count_median = not playoff or "roster_wins_include_playoff_median" in b
            count_points = not playoff or "roster_points_include_playoffs" in b
            for a, c in self.pairings[week]:
                for me, them in ((a, c), (c, a)):
                    t = totals[me]
                    if count_points:
                        t["pa"] += rows[them]
                    if count_results:
                        t["wins" if rows[me] > rows[them] else "losses" if rows[me] < rows[them] else "ties"] += 1
            for me, points in rows.items():
                t = totals[me]
                if count_points:
                    t["pf"] += points
                if count_median:
                    t["wins" if points > median else "losses"] += 1
        return [
            {"roster_id": r, "owner_id": f"90000000000000000{r}", "co_owners": None, "players": self._team_players(r),
             "settings": {"wins": t["wins"], "losses": t["losses"], "ties": t["ties"],
                          "fpts": t["pf"] // 100, "fpts_decimal": t["pf"] % 100,
                          "fpts_against": t["pa"] // 100, "fpts_against_decimal": t["pa"] % 100}}
            for r, t in totals.items()
        ]

    def _seeds(self):
        """roster_ids by regular-season wins (head-to-head plus median), then points for, both highest first."""
        wins = {r: 0 for r in range(1, self.teams + 1)}
        points = dict.fromkeys(wins, 0)
        for week in range(1, min(self.last_scored_leg, self.playoff_week_start - 1) + 1):
            rows = {m["roster_id"]: round(m["points"] * 100) for m in self._matchups(week)}
            median = statistics.median(rows.values())
            for a, c in self.pairings[week]:
                wins[a if rows[a] > rows[c] else c] += 1
            for r, cents in rows.items():
                wins[r] += cents > median
                points[r] += cents
        return sorted(wins, key=lambda r: (wins[r], points[r]), reverse=True)

    def _winners_bracket(self):
        if self.last_scored_leg < 1:
            return None  # Sleeper has no bracket before any week is scored
        s = self._seeds()
        return [
            {"r": 1, "m": 1, "t1": s[3], "t2": s[4], "w": None, "l": None},
            {"r": 1, "m": 2, "t1": s[2], "t2": s[5], "w": None, "l": None},
            {"r": 2, "m": 3, "t1": s[0], "t2": None, "t2_from": {"w": 1}, "w": None, "l": None},
            {"r": 2, "m": 4, "t1": s[1], "t2": None, "t2_from": {"w": 2}, "w": None, "l": None},
            {"r": 2, "m": 5, "p": 5, "t1": None, "t2": None, "t1_from": {"l": 1}, "t2_from": {"l": 2}, "w": None, "l": None},
            {"r": 3, "m": 6, "p": 1, "t1": None, "t2": None, "t1_from": {"w": 3}, "t2_from": {"w": 4}, "w": None, "l": None},
            {"r": 3, "m": 7, "p": 3, "t1": None, "t2": None, "t1_from": {"l": 3}, "t2_from": {"l": 4}, "w": None, "l": None},
        ]

    def _transactions(self, week):
        moves = []
        for player_id, (roster_id, t) in self.pickups.items():
            if week == 1:
                moves.append({"status": "complete", "leg": 1, "adds": {player_id: roster_id}, "drops": None,
                              "roster_ids": [roster_id], "settings": None, "draft_picks": [], "waiver_budget": [], **t})
        moves.append({"transaction_id": f"failed{week}", "type": "waiver", "status": "failed", "leg": week,
                      "created": _epoch_ms(2026, 9, 9, 4) + week * WEEK_MS, "adds": {"9901": 3}, "drops": None,
                      "roster_ids": [3], "settings": {"waiver_bid": 1}, "draft_picks": [], "waiver_budget": []})
        return moves

    # --- the API -------------------------------------------------------------------------------

    def get(self, path):
        league = f"/league/{LEAGUE_ID}"
        if path == "/state/nfl":
            return dict(self.state)
        if path == "/players/nfl":
            return self.players
        if path == league:
            return {"league_id": LEAGUE_ID, "name": "Fake League", "season": SEASON, "status": "in_season",
                    "roster_positions": ROSTER_POSITIONS,
                    "settings": {"num_teams": self.teams, "playoff_week_start": self.playoff_week_start, "start_week": 1,
                                 "league_average_match": 1, "last_scored_leg": self.last_scored_leg,
                                 "playoff_teams": 6, "playoff_round_type": 0, "playoff_seed_type": 0}}
        if path == f"{league}/users":
            return [{"user_id": f"90000000000000000{r}", "display_name": f"manager{r}",
                     "metadata": {"team_name": f"Team {r}"}} for r in range(1, self.teams + 1)]
        if path == f"{league}/rosters":
            return self._rosters()
        if path == f"{league}/winners_bracket":
            return self._winners_bracket()
        if path == f"{league}/drafts":
            return [{"draft_id": "800000000000000000", "season": SEASON, "status": "complete"}]
        if path == "/draft/800000000000000000/picks":
            return []
        for kind, build in (("matchups", self._matchups), ("transactions", self._transactions)):
            prefix = f"{league}/{kind}/"
            if path.startswith(prefix):
                return build(int(path.removeprefix(prefix)))
        raise AssertionError(f"the fake Sleeper has no response for {path}")


def PlayoffLeague(behaviours=(), last_scored_leg=9):
    """The 8-team league scored through its first playoff week (8, like week 15) and second (9)."""
    state = {**IN_SEASON, "week": last_scored_leg + 1, "leg": last_scored_leg + 1}
    return FakeSleeper(last_scored_leg=last_scored_leg, state=state, teams=8, playoff_week_start=8,
                       playoffs=PLAYOFFS_8, behaviours=behaviours)
