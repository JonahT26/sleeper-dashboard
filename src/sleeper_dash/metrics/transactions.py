"""Transactions (METRICS_SPEC.md section 9): pickup value, FAAB efficiency, and trade outcomes.

Run with:  python -m sleeper_dash.metrics.transactions   (rebuilds every metric table; prints this season's pickups,
                                                          FAAB efficiency, and trades)

One idea under all three: every regular-season start is credited to the starting team's most recent acquisition
of that player (a waiver, free-agent, trade, or commissioner add in weeks 1..that week, or "draft" when the team
has no recorded add of him). Pickup value sums a pickup's credits; FAAB efficiency divides a team's waiver-claim
credits by its winning bids; a trade side's points are the credits to that trade on that team. Regular season only
(owner, 2026-10-05): playoff starts earn no credits. Pure functions: DataFrames in, DataFrames out.
"""

import pandas as pd

PICKUP_TYPES = ("waiver", "free_agent")
DRAFT = "draft"  # no recorded add by the team: drafted, or on the roster from the start
START_CREDITS_COLUMNS = ["season", "week", "roster_id", "player_id", "points", "source", "transaction_id"]
PICKUPS_COLUMNS = ["season", "transaction_id", "week", "is_preseason", "type", "roster_id", "player_id", "player_name",
                   "waiver_bid", "starts", "start_points"]
TRADES_COLUMNS = ["season", "transaction_id", "week", "roster_id", "partner_roster_id", "players_received", "players",
                  "faab_received", "starts", "start_points", "partner_start_points", "margin", "result"]
SEASON_COLUMNS = ["pickup_points", "waiver_points", "faab_spent", "faab_points_per_dollar", "trades", "trade_margin"]
SEASON_KEY = ["season", "through_week", "roster_id"]


def check_params(params):
    spend = params.get("min_faab_spend")
    if isinstance(spend, bool) or not isinstance(spend, (int, float)) or spend < 0:
        raise ValueError("metrics.transactions.min_faab_spend must be a number of dollars, at least 0")


def _regular_weeks(team_weeks):
    return sorted(int(w) for w in team_weeks.loc[~team_weeks["is_playoff"].astype(bool), "week"].unique())


def _adds(transactions):
    adds = transactions[transactions["action"] == "add"]
    return adds.assign(_when=pd.to_datetime(adds["created_at"], utc=True, format="ISO8601"))  # text when read back from CSV


def build_start_credits(player_weeks, transactions, team_weeks):
    """One row per regular-season start of a real player, credited to the team's most recent acquisition of him."""
    regular = _regular_weeks(team_weeks)
    starts = player_weeks[player_weeks["is_starter"].astype(bool) & ~player_weeks["is_empty_slot"].astype(bool)
                          & player_weeks["week"].isin(regular)]
    starts = starts[["season", "week", "roster_id", "player_id", "points"]].reset_index(drop=True)
    starts["_start"] = starts.index
    adds = _adds(transactions)[["season", "roster_id", "player_id", "week", "type", "transaction_id", "_when"]]
    joined = starts.merge(adds.rename(columns={"week": "_added"}), on=["season", "roster_id", "player_id"], how="inner")
    joined = joined[joined["_added"] <= joined["week"]].sort_values(["_when", "transaction_id"])
    latest = joined.drop_duplicates("_start", keep="last").set_index("_start")
    starts["source"] = latest["type"].reindex(starts["_start"]).fillna(DRAFT).to_numpy()
    starts["transaction_id"] = latest["transaction_id"].reindex(starts["_start"]).to_numpy()
    credits = starts[START_CREDITS_COLUMNS].astype({"season": "int64", "week": "int64", "roster_id": "int64",
                                                    "player_id": "string", "points": "float64", "source": "string",
                                                    "transaction_id": "string"})
    return credits.sort_values(["season", "week", "roster_id", "player_id"]).reset_index(drop=True)


def build_pickups(transactions, credits, team_weeks):
    """One row per waiver or free-agent add made in the regular season (preseason included), with its credits so far."""
    adds = _adds(transactions)
    adds = adds[adds["type"].isin(PICKUP_TYPES) & adds["week"].isin(_regular_weeks(team_weeks))]
    earned = (credits.dropna(subset=["transaction_id"]).groupby(["transaction_id", "player_id"])["points"]
              .agg(starts="size", start_points="sum").reset_index())
    table = adds.merge(earned, on=["transaction_id", "player_id"], how="left")
    table = table.assign(starts=table["starts"].fillna(0), start_points=table["start_points"].fillna(0.0).round(2))
    table = table.sort_values(["_when", "transaction_id"])[PICKUPS_COLUMNS]
    return table.astype({"season": "int64", "transaction_id": "string", "week": "int64", "is_preseason": "bool",
                         "type": "string", "roster_id": "int64", "player_id": "string", "player_name": "string",
                         "waiver_bid": "Int64", "starts": "int64", "start_points": "float64"}).reset_index(drop=True)


def _trade_sides(transactions, trade_assets, team_weeks):
    """{transaction_id: (season, week, [roster A, roster B])} for regular-season trades that moved at least one player."""
    regular = _regular_weeks(team_weeks)
    moves = transactions[(transactions["type"] == "trade") & transactions["week"].isin(regular)]
    sides = {}
    for tid, rows in moves.groupby("transaction_id", sort=False):
        teams = set(rows["roster_id"].astype(int))
        assets = trade_assets[trade_assets["transaction_id"] == tid]
        teams |= set(assets["sender_roster_id"].astype(int)) | set(assets["receiver_roster_id"].astype(int))
        if len(teams) != 2:
            raise ValueError(f"Trade {tid} involves {len(teams)} teams; trade outcomes are defined for two "
                             "(METRICS_SPEC.md section 9). Update the spec before running again.")
        sides[tid] = (int(rows["season"].iloc[0]), int(rows["week"].iloc[0]), sorted(teams))
    return sides


def build_trades(transactions, trade_assets, credits, team_weeks, through_week=None):
    """One row per side of each regular-season trade that moved players: credits from the players it received."""
    if through_week is not None:
        credits = credits[credits["week"] <= through_week]
    earned = credits[credits["source"] == "trade"].groupby(["transaction_id", "roster_id"])["points"].agg(["size", "sum"])
    faab = trade_assets[trade_assets["asset"] == "faab"].groupby(["transaction_id", "receiver_roster_id"])["faab_amount"].sum()
    received = transactions[(transactions["type"] == "trade") & (transactions["action"] == "add")]
    rows = []
    for tid, (season, week, teams) in _trade_sides(transactions, trade_assets, team_weeks).items():
        if through_week is not None and week > through_week:
            continue
        points = {r: float(earned["sum"].get((tid, r), 0.0)) for r in teams}
        for me, partner in (teams, teams[::-1]):
            got = received[(received["transaction_id"] == tid) & (received["roster_id"] == me)]
            margin = round(points[me] - points[partner], 2)
            rows.append({"season": season, "transaction_id": tid, "week": week, "roster_id": me, "partner_roster_id": partner,
                         "players_received": len(got), "players": ", ".join(got["player_name"].fillna(got["player_id"])),
                         "faab_received": int(faab.get((tid, me), 0)), "starts": int(earned["size"].get((tid, me), 0)),
                         "start_points": round(points[me], 2), "partner_start_points": round(points[partner], 2),
                         "margin": margin, "result": "won" if margin > 0 else "lost" if margin < 0 else "even"})
    table = pd.DataFrame(rows, columns=TRADES_COLUMNS)
    return table.astype({"season": "int64", "transaction_id": "string", "week": "int64", "roster_id": "int64",
                         "partner_roster_id": "int64", "players_received": "int64", "players": "string",
                         "faab_received": "int64", "starts": "int64", "start_points": "float64",
                         "partner_start_points": "float64", "margin": "float64", "result": "string"})


def season_columns(transactions, trade_assets, credits, team_weeks, params):
    """Season-to-date pickup points, waiver points, FAAB spent and efficiency, trades and their net margin,
    one row per team per completed week (metrics_season's key). Playoff weeks keep the final regular-season values."""
    regular = _regular_weeks(team_weeks)
    bids = transactions[(transactions["action"] == "add") & (transactions["type"] == "waiver")]
    rows = []
    for (season, week), teams in team_weeks.groupby(["season", "week"], sort=True):
        cutoff = max([w for w in regular if w <= week], default=0)
        so_far = credits[(credits["season"] == season) & (credits["week"] <= cutoff)]
        pickup = so_far[so_far["source"].isin(PICKUP_TYPES)].groupby("roster_id")["points"].sum()
        waiver = so_far[so_far["source"] == "waiver"].groupby("roster_id")["points"].sum()
        spent = bids[(bids["season"] == season) & (bids["week"] <= cutoff)].groupby("roster_id")["waiver_bid"].sum()
        trades = build_trades(transactions[transactions["season"] == season], trade_assets, so_far, team_weeks, cutoff)
        count, margin = trades.groupby("roster_id").size(), trades.groupby("roster_id")["margin"].sum()
        for roster in sorted(int(r) for r in teams["roster_id"]):
            s, w = int(spent.get(roster, 0)), round(float(waiver.get(roster, 0.0)), 2)
            rows.append({"season": int(season), "through_week": int(week), "roster_id": roster,
                         "pickup_points": round(float(pickup.get(roster, 0.0)), 2), "waiver_points": w, "faab_spent": s,
                         "faab_points_per_dollar": round(w / s, 4) if s and s >= params["min_faab_spend"] else None,
                         "trades": int(count.get(roster, 0)), "trade_margin": round(float(margin.get(roster, 0.0)), 2)})
    return pd.DataFrame(rows, columns=SEASON_KEY + SEASON_COLUMNS).astype(
        {"faab_spent": "int64", "trades": "int64", "faab_points_per_dollar": "float64"})


def build_transaction_tables(team_weeks, player_weeks, transactions, trade_assets, params):
    """{start_credits, pickups, trades, season}: the three tables plus the columns metrics_season gains."""
    check_params(params)
    credits = build_start_credits(player_weeks, transactions, team_weeks)
    return {"start_credits": credits,
            "pickups": build_pickups(transactions, credits, team_weeks),
            "trades": build_trades(transactions, trade_assets, credits, team_weeks).reset_index(drop=True),
            "season": season_columns(transactions, trade_assets, credits, team_weeks, params)}


def main():
    from sleeper_dash.metrics import rebuild_from_saved

    _, built, config = rebuild_from_saved()
    report(built, config)


def report(built, config):
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    pickups, trades, season = built["pickups"], built["trades"], built["metrics_season"]
    credits = built["start_credits"]
    print(f"\nTRANSACTIONS, {config.season} (regular season; METRICS_SPEC.md section 9)")
    share = (credits.groupby("source")["points"].sum() / credits["points"].sum() * 100).round(1)
    print("  Starter points by how the player was acquired (%): " + ", ".join(f"{k} {v}" for k, v in share.items()))
    print(f"  Pickups: {len(pickups)}, of which {int((pickups['starts'] == 0).sum())} never started")
    print("\n  Best pickups so far:")
    print("  " + pickups.sort_values("start_points", ascending=False).head(8)[
        ["week", "type", "roster_id", "player_name", "waiver_bid", "starts", "start_points"]].to_string(index=False).replace("\n", "\n  "))
    latest = season[season["through_week"] == season["through_week"].max()]
    print("\n  Season to date by team:")
    print("  " + latest[["roster_id"] + SEASON_COLUMNS].to_string(index=False).replace("\n", "\n  "))
    print("\n  Trades (one row per side):")
    print("  " + (trades.to_string(index=False).replace("\n", "\n  ") if len(trades) else "none"))


if __name__ == "__main__":
    main()
