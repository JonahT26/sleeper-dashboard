"""Build tidy tables in data/processed/ from the raw JSON in data/raw/{season}/.

Run with:  python -m sleeper_dash.transform

Reads saved files only (data/raw/ plus the players cache in data/cache/); never
calls the Sleeper API.
"""

import json
import statistics
from collections import defaultdict

import pandas as pd

from sleeper_dash import api
from sleeper_dash.config import PROJECT_ROOT, load_config
from sleeper_dash.validate import ValidationError, format_results, validate

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

TEAMS_COLUMNS = ["season", "roster_id", "owner_id", "co_owners", "display_name", "team_name"]
TEAM_WEEKS_COLUMNS = [
    "season", "week", "roster_id", "matchup_id", "points", "opponent_roster_id",
    "opponent_points", "margin", "result", "median_result", "is_playoff",
]
PLAYER_WEEKS_COLUMNS = [
    "season", "week", "roster_id", "slot_order", "lineup_slot", "player_id", "is_starter",
    "is_empty_slot", "points", "position", "full_name", "nfl_team",
]
TRANSACTIONS_COLUMNS = [
    "transaction_id", "season", "week", "is_preseason", "type", "status", "roster_id",
    "player_id", "player_name", "action", "waiver_bid", "created_at",
]
SCHEDULE_COLUMNS = ["season", "week", "roster_id", "matchup_id", "opponent_roster_id", "is_completed"]
WINNERS_BRACKET_COLUMNS = ["season", "round", "matchup_id", "t1_roster_id", "t2_roster_id", "t1_from", "t2_from",
                           "winner_roster_id", "loser_roster_id", "place"]
EMPTY_SLOT = "0"
TRADE_ASSETS_COLUMNS = [
    "transaction_id", "season", "week", "asset_order", "asset", "sender_roster_id", "receiver_roster_id",
    "faab_amount", "pick_season", "pick_round", "pick_original_roster_id", "created_at",
]
EASTERN = "America/New_York"


def read_raw(season, filename, raw_dir=None):
    path = (raw_dir or RAW_DIR) / str(season) / filename
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run `python -m sleeper_dash.extract` first.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_weekly(season, kind, raw_dir=None, required=True):
    """Return {week: records} from data/raw/{season}/{kind}/week_XX.json.

    kind is "matchups" or "transactions" (completed weeks only), or "schedule" (future
    regular-season weeks; the folder is absent once the regular season is over, so
    pass required=False).
    """
    folder = (raw_dir or RAW_DIR) / str(season) / kind
    if not folder.exists():
        if not required:
            return {}
        raise FileNotFoundError(f"{folder} is missing. Run `python -m sleeper_dash.extract` first.")
    weeks = {}
    for path in sorted(folder.glob("week_*.json")):
        with open(path, encoding="utf-8") as f:
            weeks[int(path.stem.removeprefix("week_"))] = json.load(f)
    return weeks


def read_matchups(season, raw_dir=None):
    return read_weekly(season, "matchups", raw_dir)


def read_players(path=None):
    """Load the cached /players/nfl file that extract keeps up to date."""
    path = path or api.PLAYERS_CACHE_PATH
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run `python -m sleeper_dash.extract` first.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _clean_text(value):
    """Strip stray whitespace and treat blank strings as missing."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def build_teams(league, rosters, users):
    """One row per fantasy team per season. Key: (season, roster_id).

    Rosters are left-joined to users on owner_id, so a team with no owner keeps
    its row with empty names. team_name is the user's metadata.team_name when
    set, otherwise their display_name.
    """
    roster_df = pd.DataFrame(
        {
            "roster_id": [r["roster_id"] for r in rosters],
            "owner_id": [r.get("owner_id") for r in rosters],
            "co_owners": [r.get("co_owners") or [] for r in rosters],
        }
    )
    user_df = pd.DataFrame(
        {
            "owner_id": [u["user_id"] for u in users],
            "display_name": [_clean_text(u.get("display_name")) for u in users],
            "user_team_name": [_clean_text((u.get("metadata") or {}).get("team_name")) for u in users],
        },
        columns=["owner_id", "display_name", "user_team_name"],
    )

    teams = roster_df.merge(user_df, on="owner_id", how="left", validate="many_to_one")
    teams["team_name"] = teams["user_team_name"].fillna(teams["display_name"])
    teams["season"] = int(league["season"])

    teams = teams[TEAMS_COLUMNS].sort_values("roster_id").reset_index(drop=True)
    teams = teams.astype(
        {
            "season": "int64",
            "roster_id": "int64",
            "owner_id": "string",
            "display_name": "string",
            "team_name": "string",
        }
    )
    if teams.duplicated(["season", "roster_id"]).any():
        raise ValueError("teams has duplicate (season, roster_id) rows; check rosters.json.")
    return teams


def _result(points, other):
    if points > other:
        return "W"
    if points < other:
        return "L"
    return "T"


def build_team_weeks(league, matchups_by_week):
    """One row per team per completed week. Key: (season, week, roster_id).

    Opponents are the two teams sharing a matchup_id in a week; a team with no
    matchup_id (e.g. a playoff bye) gets null opponent, margin, and result.
    result is head-to-head only. When the league plays a weekly median game,
    median_result is a separate column: W above that week's median of all team
    scores, L below. Median games are assumed to be regular season only. A score
    exactly equal to the median raises, because no tie rule has been decided.
    """
    settings = league["settings"]
    season = int(league["season"])
    playoff_start = settings["playoff_week_start"]
    plays_median = settings.get("league_average_match") == 1

    rows = []
    for week, matchups in sorted(matchups_by_week.items()):
        is_playoff = week >= playoff_start
        points = {m["roster_id"]: round(m["points"], 2) for m in matchups}
        if len(points) != len(matchups):
            raise ValueError(f"Week {week}: a roster_id appears more than once in matchups.")

        teams_in_matchup = defaultdict(list)
        for m in matchups:
            if m.get("matchup_id") is not None:
                teams_in_matchup[m["matchup_id"]].append(m["roster_id"])
        for matchup_id, roster_ids in teams_in_matchup.items():
            if len(roster_ids) != 2:
                raise ValueError(
                    f"Week {week}: matchup_id {matchup_id} has {len(roster_ids)} team(s); expected 2."
                )
        opponent = {}
        for a, b in teams_in_matchup.values():
            opponent[a], opponent[b] = b, a

        median = None
        if plays_median and not is_playoff:
            median = statistics.median(points.values())
            tied = sorted(rid for rid, p in points.items() if p == median)
            if tied:
                raise ValueError(
                    f"Week {week}: roster(s) {tied} scored exactly the weekly median ({median}). "
                    "Median ties are not handled yet; decide a rule before continuing."
                )

        for m in matchups:
            roster_id = m["roster_id"]
            opp = opponent.get(roster_id)
            own_points = points[roster_id]
            opp_points = points[opp] if opp is not None else None
            row = {
                "season": season,
                "week": week,
                "roster_id": roster_id,
                "matchup_id": m.get("matchup_id"),
                "points": own_points,
                "opponent_roster_id": opp,
                "opponent_points": opp_points,
                "margin": round(own_points - opp_points, 2) if opp is not None else None,
                "result": _result(own_points, opp_points) if opp is not None else None,
                "is_playoff": is_playoff,
            }
            if plays_median:
                row["median_result"] = None if median is None else ("W" if own_points > median else "L")
            rows.append(row)

    columns = [c for c in TEAM_WEEKS_COLUMNS if plays_median or c != "median_result"]
    team_weeks = pd.DataFrame(rows, columns=columns)
    dtypes = {
        "season": "int64", "week": "int64", "roster_id": "int64", "matchup_id": "Int64",
        "points": "float64", "opponent_roster_id": "Int64", "opponent_points": "float64",
        "margin": "float64", "result": "string", "median_result": "string", "is_playoff": "bool",
    }
    team_weeks = team_weeks.astype({c: t for c, t in dtypes.items() if c in columns})
    return team_weeks.sort_values(["week", "roster_id"]).reset_index(drop=True)


def build_schedule(league, matchups_by_week, schedule_by_week):
    """Regular-season pairings for every week, played and still to come. Key: (season, week, roster_id).

    Completed weeks come from the saved matchups; future regular-season weeks from the
    schedule files, which Sleeper publishes ahead of time with 0 points. Playoff weeks are
    left out: playoff opponents come from the bracket, not the schedule.
    """
    season = int(league["season"])
    playoff_start = league["settings"]["playoff_week_start"]
    overlap = sorted(set(matchups_by_week) & set(schedule_by_week))
    if overlap:
        raise ValueError(f"Week(s) {overlap} are in both the completed matchups and the future schedule.")

    weeks = [(w, m, True) for w, m in matchups_by_week.items()] + [(w, m, False) for w, m in schedule_by_week.items()]
    rows = []
    for week, records, completed in sorted(weeks, key=lambda item: item[0]):
        if week >= playoff_start:
            continue
        teams_in_matchup = defaultdict(list)
        for m in records:
            if m.get("matchup_id") is not None:
                teams_in_matchup[m["matchup_id"]].append(m["roster_id"])
        opponent = {}
        for matchup_id, roster_ids in teams_in_matchup.items():
            if len(roster_ids) != 2:
                raise ValueError(f"Schedule week {week}: matchup_id {matchup_id} has {len(roster_ids)} team(s); expected 2.")
            a, b = roster_ids
            opponent[a], opponent[b] = b, a
        for m in records:
            rows.append({"season": season, "week": week, "roster_id": m["roster_id"], "matchup_id": m.get("matchup_id"),
                         "opponent_roster_id": opponent.get(m["roster_id"]), "is_completed": completed})

    schedule = pd.DataFrame(rows, columns=SCHEDULE_COLUMNS).astype(
        {"season": "int64", "week": "int64", "roster_id": "int64", "matchup_id": "Int64",
         "opponent_roster_id": "Int64", "is_completed": "bool"}
    )
    if schedule.duplicated(["season", "week", "roster_id"]).any():
        raise ValueError("schedule has duplicate (season, week, roster_id) rows.")
    return schedule.sort_values(["week", "roster_id"]).reset_index(drop=True)


def _bracket_source(source):
    """Where a bracket slot's team comes from: {"w": 1} is "W1" (winner of matchup 1), {"l": 2} is "L2"."""
    if not source:
        return None
    (kind, matchup), = source.items()
    return f"{kind.upper()}{matchup}"


def build_winners_bracket(league, bracket):
    """Sleeper's winners bracket, one row per bracket game. Key: (season, matchup_id).

    During the regular season Sleeper publishes a provisional bracket from the current standings
    (teams filled in for the first round and the byes, no winners yet); playoff odds check our seeding
    against it (METRICS_SPEC.md section 8, sanity check 8). Before Sleeper has one, the table is empty.
    """
    season = int(league["season"])
    rows = [{"season": season, "round": g["r"], "matchup_id": g["m"], "t1_roster_id": g.get("t1"), "t2_roster_id": g.get("t2"),
             "t1_from": _bracket_source(g.get("t1_from")), "t2_from": _bracket_source(g.get("t2_from")),
             "winner_roster_id": g.get("w"), "loser_roster_id": g.get("l"), "place": g.get("p")}
            for g in bracket or []]
    table = pd.DataFrame(rows, columns=WINNERS_BRACKET_COLUMNS).astype(
        {"season": "int64", "round": "int64", "matchup_id": "int64", "t1_roster_id": "Int64", "t2_roster_id": "Int64",
         "t1_from": "object", "t2_from": "object", "winner_roster_id": "Int64", "loser_roster_id": "Int64", "place": "Int64"})
    return table.sort_values(["round", "matchup_id"]).reset_index(drop=True)


def _player_name(info):
    """full_name, or first + last name for entries without one (team defenses)."""
    full = _clean_text(info.get("full_name"))
    if full:
        return full
    parts = [_clean_text(info.get("first_name")), _clean_text(info.get("last_name"))]
    return " ".join(p for p in parts if p) or None


def build_player_weeks(league, matchups_by_week, players):
    """One row per lineup slot or bench spot per team per week. Key: (season, week, roster_id, slot_order).

    Starters are aligned to the non-bench entries of roster_positions, so the
    i-th starter fills the i-th starting slot (slot_order = i, from 0). Bench
    rows follow in the order of the matchup's players list, with lineup_slot
    "BN"; injured-reserve players are included as bench (owner decision). An
    empty starting slot ("0") is kept as a row with is_empty_slot and 0 points.
    Position, name, and NFL team come from the players cache and describe the
    player today, not in that week.
    """
    season = int(league["season"])
    starter_slots = [slot for slot in league["roster_positions"] if slot != "BN"]

    rows = []
    for week, matchups in sorted(matchups_by_week.items()):
        for m in matchups:
            roster_id = m["roster_id"]
            starters, starter_points = m["starters"], m["starters_points"]
            if not len(starters) == len(starter_points) == len(starter_slots):
                raise ValueError(
                    f"Week {week}, roster {roster_id}: {len(starters)} starters and "
                    f"{len(starter_points)} starter points, but the league has {len(starter_slots)} starting slots."
                )
            base = {"season": season, "week": week, "roster_id": roster_id}
            for order, (slot, player_id, points) in enumerate(zip(starter_slots, starters, starter_points)):
                empty = player_id == EMPTY_SLOT
                rows.append({**base, "slot_order": order, "lineup_slot": slot, "player_id": player_id,
                             "is_starter": True, "is_empty_slot": empty, "points": 0.0 if empty else points})

            starter_ids = set(starters)
            bench = [pid for pid in m["players"] if pid not in starter_ids]
            for order, player_id in enumerate(bench, start=len(starter_slots)):
                if player_id not in m["players_points"]:
                    raise ValueError(f"Week {week}, roster {roster_id}: no points for bench player {player_id}.")
                rows.append({**base, "slot_order": order, "lineup_slot": "BN", "player_id": player_id,
                             "is_starter": False, "is_empty_slot": False, "points": m["players_points"][player_id]})

    player_weeks = pd.DataFrame(rows, columns=PLAYER_WEEKS_COLUMNS)
    info = player_weeks["player_id"].map(lambda pid: players.get(pid) or {})
    player_weeks["position"] = info.map(lambda i: i.get("position"))
    player_weeks["full_name"] = info.map(_player_name)
    player_weeks["nfl_team"] = info.map(lambda i: i.get("team"))
    player_weeks["points"] = player_weeks["points"].round(2)

    player_weeks = player_weeks.astype(
        {
            "season": "int64", "week": "int64", "roster_id": "int64", "slot_order": "int64",
            "lineup_slot": "string", "player_id": "string", "is_starter": "bool", "is_empty_slot": "bool",
            "points": "float64", "position": "string", "full_name": "string", "nfl_team": "string",
        }
    )
    if player_weeks.duplicated(["season", "week", "roster_id", "slot_order"]).any():
        raise ValueError("player_weeks has duplicate (season, week, roster_id, slot_order) rows.")
    return player_weeks.sort_values(["week", "roster_id", "slot_order"]).reset_index(drop=True)


def build_transactions(league, transactions_by_week, players, season_start_date):
    """One row per player move in completed transactions. Key: (transaction_id, player_id, action).

    Each player in `drops` becomes a "drop" row for the team releasing them and
    each player in `adds` an "add" row for the team receiving them, so a 1-for-1
    trade is 4 rows. waiver_bid is set on the add rows of waiver claims only, so
    summing it never double-counts FAAB. Week 1 moves created before
    season_start_date (midnight US Eastern) are flagged is_preseason. Draft picks
    and FAAB traded in trades are not player moves and are not represented.
    """
    season = int(league["season"])
    preseason_cutoff = pd.Timestamp(season_start_date, tz=EASTERN)

    rows = []
    for week, transactions in sorted(transactions_by_week.items()):
        for t in transactions:
            if t["leg"] != week:
                raise ValueError(f"Transaction {t['transaction_id']} has leg {t['leg']} but is in the week {week} file.")
            if t["status"] != "complete":
                continue
            created_at = pd.Timestamp(t["created"], unit="ms", tz="UTC").tz_convert(EASTERN)
            bid = (t.get("settings") or {}).get("waiver_bid") if t["type"] == "waiver" else None
            for action, moves in (("drop", t.get("drops")), ("add", t.get("adds"))):
                for player_id, roster_id in (moves or {}).items():
                    rows.append(
                        {
                            "transaction_id": t["transaction_id"],
                            "season": season,
                            "week": week,
                            "is_preseason": week == 1 and created_at < preseason_cutoff,
                            "type": t["type"],
                            "status": t["status"],
                            "roster_id": roster_id,
                            "player_id": player_id,
                            "player_name": _player_name(players.get(player_id) or {}),
                            "action": action,
                            "waiver_bid": bid if action == "add" else None,
                            "created_at": created_at,
                        }
                    )

    moves = pd.DataFrame(rows, columns=TRANSACTIONS_COLUMNS)
    moves = moves.astype(
        {
            "transaction_id": "string", "season": "int64", "week": "int64", "is_preseason": "bool",
            "type": "string", "status": "string", "roster_id": "int64", "player_id": "string",
            "player_name": "string", "action": "string", "waiver_bid": "Int64",
            "created_at": f"datetime64[ns, {EASTERN}]",
        }
    )
    if moves.duplicated(["transaction_id", "player_id", "action"]).any():
        raise ValueError("transactions has duplicate (transaction_id, player_id, action) rows.")
    return moves.sort_values(["created_at", "transaction_id", "action"], ascending=[True, True, False]).reset_index(drop=True)


def build_trade_assets(league, transactions_by_week):
    """One row per FAAB transfer or draft pick inside a completed trade. Key: (transaction_id, asset_order).

    These aren't player moves, so `transactions` doesn't hold them (Phase 5, METRICS_SPEC.md section 9). FAAB comes
    from a trade's `waiver_budget` ([{"amount", "sender", "receiver"}], roster IDs); picks from `draft_picks`
    (previous_owner_id gives the pick, owner_id receives it, roster_id is the team whose pick it originally was).
    Trades of FAAB only, with no players, are here and nowhere else.
    """
    season = int(league["season"])
    rows = []
    for week, transactions in sorted(transactions_by_week.items()):
        for t in transactions:
            if t["status"] != "complete" or t["type"] != "trade":
                continue
            created_at = pd.Timestamp(t["created"], unit="ms", tz="UTC").tz_convert(EASTERN)
            base = {"transaction_id": t["transaction_id"], "season": season, "week": week, "created_at": created_at}
            assets = [{"asset": "faab", "sender_roster_id": f["sender"], "receiver_roster_id": f["receiver"],
                       "faab_amount": f["amount"]} for f in t.get("waiver_budget") or []]
            assets += [{"asset": "pick", "sender_roster_id": p["previous_owner_id"], "receiver_roster_id": p["owner_id"],
                        "pick_season": int(p["season"]), "pick_round": p["round"], "pick_original_roster_id": p["roster_id"]}
                       for p in t.get("draft_picks") or []]
            rows += [{**base, "asset_order": i, **a} for i, a in enumerate(assets)]
    assets = pd.DataFrame(rows, columns=TRADE_ASSETS_COLUMNS).astype({
        "transaction_id": "string", "season": "int64", "week": "int64", "asset_order": "int64", "asset": "string",
        "sender_roster_id": "int64", "receiver_roster_id": "int64", "faab_amount": "Int64", "pick_season": "Int64",
        "pick_round": "Int64", "pick_original_roster_id": "Int64", "created_at": f"datetime64[ns, {EASTERN}]"})
    return assets.sort_values(["created_at", "transaction_id", "asset_order"]).reset_index(drop=True)


def faab_balances(transactions, trade_assets, rosters, budget):
    """FAAB per team: budget, winning bids, FAAB received and sent in trades, what's left, and Sleeper's own
    `waiver_budget_used` with the gap (METRICS_SPEC.md section 9, "FAAB balance report"; printed, never a stopping
    check: Sleeper's current-season figure includes the week in progress, and 2021-2024 have unexplained gaps)."""
    faab = trade_assets[trade_assets["asset"] == "faab"]
    table = pd.DataFrame({
        "spent": transactions[transactions["action"] == "add"].groupby("roster_id")["waiver_bid"].sum(),
        "received": faab.groupby("receiver_roster_id")["faab_amount"].sum(),
        "sent": faab.groupby("sender_roster_id")["faab_amount"].sum(),
    }).reindex(sorted(r["roster_id"] for r in rosters)).fillna(0).astype("int64")
    table.index.name = "roster_id"
    table.insert(0, "budget", int(budget))
    table["left"] = table["budget"] - table["spent"] + table["received"] - table["sent"]
    table["sleeper_used"] = table.index.map({r["roster_id"]: (r["settings"] or {}).get("waiver_budget_used", 0) for r in rosters})
    table["gap"] = table["sleeper_used"] - (table["budget"] - table["left"])
    return table


def season_start_date(state, league, configured):
    """The season's start date: config.yaml's value, cross-checked against /state/nfl when it can be.

    The date never comes from /state/nfl, which only describes the current NFL season: after
    Sleeper moves on (off-season, next season, or a past season being rebuilt) the configured
    date is used alone. While /state/nfl describes the league's season and gives a date, the
    two must agree, which catches a typo in config.yaml.
    """
    reported = state.get("season_start_date")
    if str(state.get("season")) == str(league["season"]) and reported and reported != configured:
        raise ValueError(
            f"config.yaml says season {league['season']} started {configured}, but Sleeper says it "
            f"started {reported}. Correct season_start_dates in config.yaml."
        )
    return configured


def _standings(team_weeks, teams):
    """Season-to-date records and points from team_weeks, for display and reconciliation."""
    by_team = team_weeks.groupby("roster_id")
    count = lambda col, value: by_team[col].apply(lambda s: int((s == value).sum()))
    table = pd.DataFrame(
        {
            "W": count("result", "W"),
            "L": count("result", "L"),
            "T": count("result", "T"),
            "PF": by_team["points"].sum().round(2),
            "PA": by_team["opponent_points"].sum().round(2),
        }
    )
    if "median_result" in team_weeks:
        table["med_W"] = count("median_result", "W")
        table["med_L"] = count("median_result", "L")
    names = teams.set_index("roster_id")["team_name"]
    table.insert(0, "team_name", names.reindex(table.index))
    return table.reset_index()


def save_table(df, name, processed_dir=None):
    """Write a table to data/processed/{name}.csv. List columns are stored as JSON text.

    Saved with a byte-order mark (utf-8-sig) so Excel shows non-English characters correctly.
    """
    out = df.copy()
    for column in out.columns:
        if any(isinstance(v, list) for v in out[column]):
            out[column] = out[column].map(json.dumps)
    processed_dir = processed_dir or PROCESSED_DIR
    processed_dir.mkdir(parents=True, exist_ok=True)
    path = processed_dir / f"{name}.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def build_tables(season, configured_start_date):
    """Build every tidy table from saved files. Returns (tables, league, rosters, season_start_date)."""
    league = read_raw(season, "league.json")
    rosters = read_raw(season, "rosters.json")
    users = read_raw(season, "users.json")
    matchups = read_matchups(season)
    players = read_players()
    start_date = season_start_date(read_raw(season, "state.json"), league, configured_start_date)
    transactions = read_weekly(season, "transactions")

    tables = {
        "teams": build_teams(league, rosters, users),
        "team_weeks": build_team_weeks(league, matchups),
        "player_weeks": build_player_weeks(league, matchups, players),
        "transactions": build_transactions(league, transactions, players, start_date),
        "trade_assets": build_trade_assets(league, transactions),
        "schedule": build_schedule(league, matchups, read_weekly(season, "schedule", required=False)),
        "winners_bracket": build_winners_bracket(league, read_raw(season, "winners_bracket.json")),
    }
    return tables, league, rosters, start_date


def save_tables(tables, processed_dir=None):
    """Save every table to data/processed/; returns {name: path}."""
    return {name: save_table(table, name, processed_dir) for name, table in tables.items()}


def main():
    from sleeper_dash.seasons import build_managers, stack, with_known_gaps
    from sleeper_dash.validate import check_managers, validate_seasons

    config = load_config()
    by_season, start_dates = {}, {}
    for season in config.seasons:
        season_tables, league, rosters, start_dates[season] = build_tables(season, config.start_date(season))
        by_season[season] = (season_tables, league, with_known_gaps(rosters, config.sleeper_points_gaps.get(season, [])))
    teams = pd.concat([t["teams"] for t, _, _ in by_season.values()], ignore_index=True)
    managers = build_managers(teams)

    # Check every season before saving, so tables that fail never overwrite the last good ones.
    try:
        results = validate_seasons(by_season, extra=[check_managers(managers, teams)])
    except ValidationError as error:
        raise SystemExit(str(error))
    print(format_results(results))
    print()

    stacked = {**stack({season: t for season, (t, _, _) in by_season.items()}), "managers": managers}
    for name, path in save_tables(stacked).items():
        print(f"Saved {len(stacked[name])} rows to {path.relative_to(PROJECT_ROOT).as_posix()}")

    tables, league, rosters = by_season[config.season]  # the reports below describe the current season
    start_date = start_dates[config.season]

    teams, team_weeks = tables["teams"], tables["team_weeks"]
    player_weeks, transactions = tables["player_weeks"], tables["transactions"]
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    weeks = sorted(int(w) for w in team_weeks["week"].unique())
    print(f"\nWeeks covered: {weeks}; playoff rows: {int(team_weeks['is_playoff'].sum())}")
    _report_standings(team_weeks, teams, rosters)
    _report_player_weeks(player_weeks, team_weeks)
    _report_transactions(transactions, teams, rosters, start_date)
    _report_faab(transactions, tables["trade_assets"], teams, rosters, league)


def _report_faab(transactions, trade_assets, teams, rosters, league):
    balances = faab_balances(transactions, trade_assets, rosters, league["settings"].get("waiver_budget", 0))
    balances.insert(0, "team_name", teams.set_index("roster_id")["team_name"])
    print(f"\nFAAB (trade_assets: {int((trade_assets['asset'] == 'faab').sum())} FAAB transfers, "
          f"{int((trade_assets['asset'] == 'pick').sum())} draft picks)")
    print("  " + balances.to_string().replace("\n", "\n  "))
    print(f"  {int((balances['gap'] == 0).sum())} of {len(balances)} teams match Sleeper's budget used. A gap is "
          "expected while a week is in progress: Sleeper counts its claims and trades, this table doesn't yet.")


def _report_transactions(moves, teams, rosters, start_date):
    print("\nTRANSACTIONS (completed only)")
    print(f"  Rows: {len(moves)} player moves in {moves['transaction_id'].nunique()} transactions; "
          f"preseason (before {start_date}): {moves.loc[moves['is_preseason'], 'transaction_id'].nunique()} transactions")

    by_type = moves.groupby("type").agg(
        transactions=("transaction_id", "nunique"),
        adds=("action", lambda s: int((s == "add").sum())),
        drops=("action", lambda s: int((s == "drop").sum())),
    )
    print("\n  By type:")
    print("  " + by_type.to_string().replace("\n", "\n  "))

    adds = moves[moves["action"] == "add"]
    by_team = pd.DataFrame(
        {
            "adds": adds.groupby("roster_id").size(),
            "drops": moves[moves["action"] == "drop"].groupby("roster_id").size(),
            "waiver_wins": adds[adds["type"] == "waiver"].groupby("roster_id")["transaction_id"].nunique(),
            "trades": moves[moves["type"] == "trade"].groupby("roster_id")["transaction_id"].nunique(),
            "faab_spent": adds.groupby("roster_id")["waiver_bid"].sum(),
        }
    ).reindex(teams["roster_id"]).fillna(0).astype(int)
    by_team["sleeper_faab_now"] = by_team.index.map({r["roster_id"]: r["settings"]["waiver_budget_used"] for r in rosters})
    by_team["faab_diff"] = by_team["sleeper_faab_now"] - by_team["faab_spent"]
    by_team.insert(0, "team_name", teams.set_index("roster_id")["team_name"])
    by_team = by_team.sort_values(["adds", "faab_spent"], ascending=False)
    print("\n  By team (sorted by adds):")
    print("  " + by_team.to_string().replace("\n", "\n  "))
    print(f"\n  Teams where FAAB spent through completed weeks differs from Sleeper's current figure: "
          f"{int((by_team['faab_diff'] != 0).sum())}")
    print("  (Sleeper's waiver_budget_used also counts the in-progress week and FAAB traded between teams;")
    print("   this table covers completed weeks and player moves only.)")

    recent = moves.merge(teams[["roster_id", "team_name"]], on="roster_id")
    recent = recent.sort_values(["created_at", "transaction_id", "action"], ascending=[False, True, True])
    latest_ids = recent["transaction_id"].drop_duplicates().head(5)
    recent = recent[recent["transaction_id"].isin(latest_ids)].copy()
    recent["created_at"] = recent["created_at"].dt.strftime("%a %b %d %I:%M %p ET")
    print("\n  Five most recent transactions (all their moves):")
    columns = ["created_at", "week", "type", "team_name", "action", "player_name", "waiver_bid"]
    print("  " + recent[columns].to_string(index=False).replace("\n", "\n  "))


def _report_player_weeks(player_weeks, team_weeks):
    starters = player_weeks[player_weeks["is_starter"]]
    starter_totals = starters.groupby(["week", "roster_id"])["points"].sum().round(2)
    team_points = team_weeks.set_index(["week", "roster_id"])["points"]
    mismatches = int(((starter_totals - team_points.reindex(starter_totals.index)).abs() > 0.005).sum())
    bench = player_weeks[~player_weeks["is_starter"]]

    print("\nPLAYER_WEEKS")
    print(f"  Rows: {len(player_weeks)} ({len(starters)} starter slots, {len(bench)} bench spots)")
    print(f"  Bench spots per team-week: {bench.groupby(['week', 'roster_id']).size().value_counts().sort_index().to_dict()}")
    print(f"  Empty starting slots: {int(player_weeks['is_empty_slot'].sum())}")
    print(f"  Players not found in cache: {int((player_weeks['position'].isna() & ~player_weeks['is_empty_slot']).sum())}")
    print(f"  Team-weeks where starter points != team score: {mismatches} of {len(starter_totals)}")
    print("\n  Starters by slot (rows) and player position (columns):")
    crosstab = pd.crosstab(starters["lineup_slot"], starters["position"])
    order = list(dict.fromkeys(starters["lineup_slot"]))
    print("  " + crosstab.reindex(order).to_string().replace("\n", "\n  "))


def _report_standings(team_weeks, teams, rosters):
    table = _standings(team_weeks, teams)
    sleeper = pd.DataFrame(
        {
            "roster_id": [r["roster_id"] for r in rosters],
            "sl_W": [r["settings"]["wins"] for r in rosters],
            "sl_L": [r["settings"]["losses"] for r in rosters],
            "sl_T": [r["settings"]["ties"] for r in rosters],
            "sl_PF": [r["settings"]["fpts"] + r["settings"]["fpts_decimal"] / 100 for r in rosters],
            "sl_PA": [r["settings"]["fpts_against"] + r["settings"]["fpts_against_decimal"] / 100 for r in rosters],
        }
    )
    table = table.merge(sleeper, on="roster_id")
    has_median = "med_W" in table
    table["record"] = table.W.astype(str) + "–" + table.L.astype(str) + "–" + table["T"].astype(str)
    total_W = table.W + (table.med_W if has_median else 0)
    total_L = table.L + (table.med_L if has_median else 0)
    table["matches_sleeper"] = (
        (total_W == table.sl_W) & (total_L == table.sl_L) & (table["T"] == table.sl_T)
        & ((table.PF - table.sl_PF).abs() < 0.005) & ((table.PA - table.sl_PA).abs() < 0.005)
    )
    columns = ["team_name", "record", "PF", "PA"]
    if has_median:
        table["median"] = table.med_W.astype(str) + "–" + table.med_L.astype(str)
        table["overall"] = total_W.astype(str) + "–" + total_L.astype(str)
        columns += ["median", "overall"]
    table = table.assign(total_W=total_W).sort_values(["total_W", "PF"], ascending=False)
    print("\nSTANDINGS (head-to-head record; sorted by overall wins, then points for)")
    print(table[columns + ["matches_sleeper"]].to_string(index=False))
    print(f"\nAll teams match Sleeper's own season totals: {bool(table['matches_sleeper'].all())}")


if __name__ == "__main__":
    main()
