"""A small, made-up Sleeper league served in place of the real API, so the whole pipeline can run offline.

Six teams; lineup QB, RB, WR, FLEX plus two bench spots; weekly median game on; regular season
weeks 1-5 (a full round robin), playoffs from week 6. Scores are fixed pseudo-random numbers,
so every run sees the same league. `last_scored_leg` says how many weeks Sleeper has scored,
`state` is what /state/nfl reports, and `corrections` changes a player's score after the fact
(a stat correction). Week 1 has one preseason pickup (before the 2026-09-09 start) and one after
it, so a wrong season start date changes the transactions table.
"""

import random
from datetime import datetime
from zoneinfo import ZoneInfo

LEAGUE_ID = "1000000000000000000"
SEASON = "2026"
START_DATE = "2026-09-09"
TEAMS = 6
PLAYOFF_WEEK_START = 6
ROSTER_POSITIONS = ["QB", "RB", "WR", "FLEX", "BN", "BN"]
EASTERN = ZoneInfo("America/New_York")

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
    def __init__(self, last_scored_leg=3, state=IN_SEASON):
        self.last_scored_leg = last_scored_leg
        self.state = state
        self.corrections = {}  # {(week, player_id): points in cents}
        self.pairings = _round_robin(TEAMS, PLAYOFF_WEEK_START - 1)
        self.roster_players = {
            r: [f"{r}01", f"{r}02", f"{r}03", f"{r}04", f"{r}05", f"{r}06"] for r in range(1, TEAMS + 1)
        }  # QB, RB, WR, FLEX (RB), bench WR, bench TE
        positions = ["QB", "RB", "WR", "RB", "WR", "TE"]
        self.players = {
            pid: {"player_id": pid, "position": pos, "fantasy_positions": [pos], "full_name": f"Player {pid}",
                  "first_name": "Player", "last_name": pid, "team": "KC"}
            for r, pids in self.roster_players.items() for pid, pos in zip(pids, positions)
        }
        # Two free agents picked up in week 1: one before the season starts, one after.
        for pid, pos in (("701", "WR"), ("702", "RB")):
            self.players[pid] = {"player_id": pid, "position": pos, "fantasy_positions": [pos],
                                 "full_name": f"Free Agent {pid}", "team": "SF"}
        self.pickups = {  # player_id: (roster_id, transaction)
            "701": (1, {"transaction_id": "t1", "type": "free_agent", "created": _epoch_ms(2026, 9, 5, 12)}),
            "702": (2, {"transaction_id": "t2", "type": "waiver", "created": _epoch_ms(2026, 9, 12, 4),
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

    def _matchups(self, week):
        scored = week <= self.last_scored_leg
        rows = []
        for matchup_id, pair in enumerate(self.pairings[week], start=1):
            for roster_id in pair:
                players = self._team_players(roster_id)
                cents = {pid: self._cents(week, pid) if scored else 0 for pid in players}
                starters = players[:4]
                rows.append({
                    "roster_id": roster_id, "matchup_id": matchup_id,
                    "points": sum(cents[p] for p in starters) / 100,
                    "starters": starters, "starters_points": [cents[p] / 100 for p in starters],
                    "players": players, "players_points": {p: c / 100 for p, c in cents.items()},
                    "custom_points": None,
                })
        if scored:
            totals = [round(r["points"] * 100) for r in rows]
            assert len(set(totals)) == len(totals), f"week {week}: equal team scores would make a median tie"
        return rows

    def _rosters(self):
        totals = {r: {"wins": 0, "losses": 0, "ties": 0, "pf": 0, "pa": 0} for r in range(1, TEAMS + 1)}
        for week in range(1, self.last_scored_leg + 1):
            rows = {m["roster_id"]: round(m["points"] * 100) for m in self._matchups(week)}
            ordered = sorted(rows.values())
            median = (ordered[TEAMS // 2 - 1] + ordered[TEAMS // 2]) / 2
            for a, b in self.pairings[week]:
                for me, them in ((a, b), (b, a)):
                    t = totals[me]
                    t["pf"] += rows[me]
                    t["pa"] += rows[them]
                    t["wins" if rows[me] > rows[them] else "losses" if rows[me] < rows[them] else "ties"] += 1
                    t["wins" if rows[me] > median else "losses"] += 1
        return [
            {"roster_id": r, "owner_id": f"90000000000000000{r}", "co_owners": None, "players": self._team_players(r),
             "settings": {"wins": t["wins"], "losses": t["losses"], "ties": t["ties"],
                          "fpts": t["pf"] // 100, "fpts_decimal": t["pf"] % 100,
                          "fpts_against": t["pa"] // 100, "fpts_against_decimal": t["pa"] % 100}}
            for r, t in totals.items()
        ]

    def _transactions(self, week):
        moves = []
        for player_id, (roster_id, t) in self.pickups.items():
            if week == 1:
                moves.append({"status": "complete", "leg": 1, "adds": {player_id: roster_id}, "drops": None,
                              "roster_ids": [roster_id], "settings": None, "draft_picks": [], "waiver_budget": [], **t})
        moves.append({"transaction_id": f"failed{week}", "type": "waiver", "status": "failed", "leg": week,
                      "created": _epoch_ms(2026, 9, 9 + 7 * week, 4), "adds": {"701": 3}, "drops": None,
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
                    "settings": {"num_teams": TEAMS, "playoff_week_start": PLAYOFF_WEEK_START, "start_week": 1,
                                 "league_average_match": 1, "last_scored_leg": self.last_scored_leg}}
        if path == f"{league}/users":
            return [{"user_id": f"90000000000000000{r}", "display_name": f"manager{r}",
                     "metadata": {"team_name": f"Team {r}"}} for r in range(1, TEAMS + 1)]
        if path == f"{league}/rosters":
            return self._rosters()
        if path == f"{league}/drafts":
            return [{"draft_id": "800000000000000000", "season": SEASON, "status": "complete"}]
        if path == "/draft/800000000000000000/picks":
            return []
        for kind, build in (("matchups", self._matchups), ("transactions", self._transactions)):
            prefix = f"{league}/{kind}/"
            if path.startswith(prefix):
                return build(int(path.removeprefix(prefix)))
        raise AssertionError(f"the fake Sleeper has no response for {path}")
