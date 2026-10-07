"""The Roster moves section (Phase 5; UI_GUIDE.md "Roster moves"; metrics in METRICS_SPEC.md section 9): the best
pickups (sliced by position), FAAB efficiency by team with each team's waiver claims, and this season's trades,
as of the selected week.

Pure: tables in, plain values and formatted strings out. Everything counts regular-season starts only, so in playoff
weeks the section shows the final regular-season numbers. Pickups and trades are as of the selected week: their points
come from start_credits up to that week, and moves made later aren't shown.
"""

import pandas as pd

TOP_PICKUPS = 5      # owner, 2026-10-05 (2a)
PICKUPS_LEFT_OUT = ("K", "DEF")  # too noisy for Best pickups; still counted in FAAB and pickup points (owner, 2026-10-06)
# Best pickups' position slicer (owner, 2026-10-06): "All" is every position but PICKUPS_LEFT_OUT; FLEX is RB, WR and TE.
POSITION_FILTERS = [("all", "All", None), ("qb", "QB", {"QB"}), ("rb", "RB", {"RB"}), ("wr", "WR", {"WR"}),
                    ("te", "TE", {"TE"}), ("flex", "FLEX", {"RB", "WR", "TE"})]
TRADES_SHOWN = 3     # the newest; earlier ones fold away (owner, 2026-10-05, 4a)
HOW = {"waiver": "waivers", "free_agent": "free agent"}
MINUS = "−"


def _one_dp(value):
    return f"{value:.1f}"


def _starts(n):
    return f"{n} start" if n == 1 else f"{n} starts"


def _when(p):
    return "before the season" if p.is_preseason else f"week {int(p.week)}"


def _pickup_how(p):
    bid = f", ${int(p.waiver_bid)}" if p.type == "waiver" and pd.notna(p.waiver_bid) else ""
    return f"{HOW.get(p.type, p.type)}{bid}, {_when(p)}"


def _got(players, faab):
    """'DJ Moore and $3', 'Shedeur Sanders', '$5', or 'nothing'."""
    parts = [players] if isinstance(players, str) and players else []
    if faab:
        parts.append(f"${int(faab)}")
    return " and ".join(parts) or "nothing"


def moves_view(tables, names, week, last_regular, params):
    """The section for one week, or None when there's nothing to show yet (no started pickup, no FAAB spent, no trade).

    tables: one season's start_credits, pickups, trades, metrics_season, and player_weeks (positions, so kickers and
    defenses can be left out of Best pickups; without it nobody is left out). names: {roster_id: team name}.
    last_regular: the last regular-season week. params: config.yaml metrics (transactions.min_faab_spend).
    """
    if any(name not in tables for name in ("start_credits", "pickups", "trades")):
        return None
    cutoff = min(week, last_regular)
    over = week >= last_regular
    credits = tables["start_credits"]
    so_far = credits[credits["week"] <= cutoff]

    earned = (so_far.dropna(subset=["transaction_id"]).groupby(["transaction_id", "player_id"])["points"]
              .agg(starts="size", points="sum").reset_index())
    made = tables["pickups"]
    made = made[made["week"] <= cutoff].drop(columns=["starts", "start_points"]).merge(
        earned, on=["transaction_id", "player_id"], how="left")
    made[["starts", "points"]] = made[["starts", "points"]].fillna(0)
    made = made.sort_values(["points", "week", "player_name"], ascending=[False, True, True])
    if "player_weeks" in tables:
        position = tables["player_weeks"].dropna(subset=["position"]).drop_duplicates("player_id").set_index("player_id")["position"]
        made["position"] = made["player_id"].map(position)
    else:
        made["position"] = None
    pickups = made[(made["points"] > 0) & ~made["position"].isin(PICKUPS_LEFT_OUT)]

    def top(rows):
        return [{"player": p.player_name, "team": names[p.roster_id], "how": _pickup_how(p), "starts": _starts(int(p.starts)),
                 "points": _one_dp(p.points)} for p in rows.head(TOP_PICKUPS).itertuples()]

    best = top(pickups)
    filters = [{"key": key, "label": label, "rows": top(pickups if keep is None else pickups[pickups["position"].isin(keep)])}
               for key, label, keep in POSITION_FILTERS]

    # Each team's waiver claims, every one ($0 bids and claims that never started included), so a team's rows add up
    # to its FAAB Spent and Points. Free-agent pickups cost nothing and aren't part of FAAB.
    claims = {}
    for c in made[made["type"] == "waiver"].itertuples():
        claims.setdefault(int(c.roster_id), []).append({
            "player": c.player_name, "when": _when(c),
            "starts": _starts(int(c.starts)) if c.starts else "never started",
            "bid": f"${int(c.waiver_bid) if pd.notna(c.waiver_bid) else 0}", "points": _one_dp(c.points)})

    season = tables["metrics_season"]
    season = season[season["through_week"] == week]
    faab = []
    if "faab_spent" in season and (season["faab_spent"] > 0).any():
        shown = season.assign(_shown=season["faab_points_per_dollar"].notna())
        shown = shown.sort_values(["_shown", "faab_points_per_dollar", "waiver_points", "roster_id"],
                                  ascending=[False, False, False, True])
        faab = [{"team": names[r.roster_id], "spent": f"${int(r.faab_spent)}", "points": _one_dp(r.waiver_points),
                 "per_dollar": _one_dp(r.faab_points_per_dollar) if pd.notna(r.faab_points_per_dollar) else "—",
                 "id": f"faab-{week}-{int(r.roster_id)}", "claims": claims.get(int(r.roster_id), [])}
                for r in shown.itertuples()]

    trades = tables["trades"]
    trades = trades[trades["week"] <= cutoff]
    traded = so_far[so_far["source"] == "trade"].groupby(["transaction_id", "roster_id"])["points"].sum()
    cards = []
    for tid in list(dict.fromkeys(trades["transaction_id"]))[::-1]:  # the table is in trade order; newest first
        rows = trades[trades["transaction_id"] == tid]
        sides = [{"roster_id": int(r.roster_id), "team": names[r.roster_id], "got": _got(r.players, r.faab_received),
                  "points": float(traded.get((tid, r.roster_id), 0.0))} for r in rows.itertuples()]
        a, b = sides
        if round(a["points"], 2) == round(b["points"], 2):
            result = "Even" if over else "Even so far"
        else:
            lead, trail = (a, b) if a["points"] > b["points"] else (b, a)
            result = f"{lead['team']} {'won' if over else 'ahead'} by {_one_dp(lead['points'] - trail['points'])}"
        for side in sides:
            side["points"] = _one_dp(side["points"])
        cards.append({"week": int(rows["week"].iloc[0]), "sides": sides, "result": result})

    if not (best or faab or cards):
        return None
    when = ("in the regular season; playoff weeks don't count" if week > last_regular else "this regular season")
    return {"subtitle": f"Points each move has put in the starting lineup {when}.",
            "pickups": best, "pickup_filters": filters, "faab": faab, "min_spend": f"${int(params['transactions']['min_faab_spend'])}",
            "trades": cards[:TRADES_SHOWN], "earlier_trades": cards[TRADES_SHOWN:]}
