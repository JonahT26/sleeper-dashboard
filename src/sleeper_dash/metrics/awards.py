"""Weekly awards (docs/METRICS_SPEC.md section 7).

Run with:  python -m sleeper_dash.metrics.awards   (rebuilds every metric table, checks, saves, and reports)

Pure functions: tables in, tables out. Which awards appear, and in what order, comes from
config.yaml metrics.awards.enabled. Captions follow docs/UI_GUIDE.md: factual and specific,
points to 1 decimal place, percentages as whole numbers, sentence case.
"""

import pandas as pd

AWARDS_COLUMNS = ["season", "week", "award", "award_name", "roster_id", "value", "caption", "player_id"]
AWARD_NAMES = {  # display names, sentence case per UI_GUIDE.md
    "top_score": "Top score",
    "lowest_score": "Lowest score",
    "heartbreaker": "Heartbreaker",
    "robbery": "Robbery",
    "blowout": "Blowout",
    "nail_biter": "Nail-biter",
    "bench_blunder": "Bench blunder",
    "perfect_lineup": "Perfect lineup",
    "mvp": "MVP",
    "pickup_of_the_week": "Pickup of the week",
    "asleep_at_the_wheel": "Asleep at the wheel",
}
PICKUP_TYPES = {"waiver": "added off waivers", "free_agent": "added as a free agent"}


def check_params(params):
    """Stop with a clear message if metrics.awards.enabled lists an unknown award."""
    enabled = params.get("enabled")
    if not isinstance(enabled, list) or not enabled:
        raise ValueError("config.yaml metrics.awards.enabled must be a list of award keys")
    unknown = [key for key in enabled if key not in AWARD_NAMES]
    if unknown:
        raise ValueError(f"config.yaml metrics.awards.enabled has unknown award(s) {unknown}; known: {list(AWARD_NAMES)}")
    if len(set(enabled)) != len(enabled):
        raise ValueError("config.yaml metrics.awards.enabled lists an award twice")


def ordinal(n):
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def pts(x):
    return f"{x:.1f}"


def _winners(frame, column, highest, tiebreak=None):
    """Rows holding the best value of `column` (ties: `tiebreak` (column, highest) pairs, then co-winners)."""
    if frame.empty:
        return frame
    best = frame[column].max() if highest else frame[column].min()
    rows = frame[(frame[column] - best).abs() < 1e-9]
    for col, high in tiebreak or []:
        target = rows[col].max() if high else rows[col].min()
        rows = rows[(rows[col] - target).abs() < 1e-9]
    return rows


def _week_awards(week_teams, week_players, lineups, acquisitions, names):
    """Every defined award for one week, as {award key: list of row dicts}."""
    teams = week_teams.assign(score_rank=week_teams["points"].rank(method="min", ascending=False).astype(int))
    played = teams[teams["result"].notna()]
    winners, losers = played[played["result"] == "W"], played[played["result"] == "L"]
    starters = week_players[week_players["is_starter"].astype(bool)]
    out = {}

    def rows(frame, value_col, caption, player=None):
        return [{"roster_id": int(r["roster_id"]), "value": float(r[value_col]), "caption": caption(r),
                 "player_id": player(r) if player else None} for _, r in frame.iterrows()]

    out["top_score"] = rows(_winners(teams, "points", True), "points",
                            lambda r: f"Put up {pts(r['points'])}, the best of the week.")
    out["lowest_score"] = rows(_winners(teams, "points", False), "points",
                               lambda r: f"Managed {pts(r['points'])}. Everyone else did better.")
    out["heartbreaker"] = rows(_winners(losers, "points", True), "points",
                               lambda r: f"Scored {pts(r['points'])}, {ordinal(r['score_rank'])}-best of the week, and still lost.")
    out["robbery"] = rows(_winners(winners, "points", False), "points",
                          lambda r: f"Won with {pts(r['points'])}, the {ordinal(r['score_rank'])}-best score.")
    out["blowout"] = rows(_winners(winners, "margin", True), "margin",
                          lambda r: f"Beat {names[int(r['opponent_roster_id'])]} by {pts(r['margin'])}.")
    out["nail_biter"] = rows(_winners(winners, "margin", False), "margin",
                             lambda r: f"Edged {names[int(r['opponent_roster_id'])]} by {pts(r['margin'])}.")

    lineup = teams.merge(lineups[["roster_id", "bench_points_lost", "efficiency"]], on="roster_id")
    blunders = lineup[lineup["bench_points_lost"] > 0]  # a perfect lineup left nothing on the bench: not a blunder
    out["bench_blunder"] = rows(_winners(blunders, "bench_points_lost", True, [("efficiency", False)]), "bench_points_lost",
                                lambda r: f"Left {pts(r['bench_points_lost'])} points on the bench.")
    out["perfect_lineup"] = rows(_winners(lineup.dropna(subset=["efficiency"]), "efficiency", True, [("points", True)]), "efficiency",
                                 lambda r: "Started the best possible lineup: 100%." if r["efficiency"] >= 1 - 1e-9
                                 else f"Got {r['efficiency']:.0%} of the points the best lineup would have scored.")

    real = starters[~starters["is_empty_slot"].astype(bool)]
    out["mvp"] = rows(_winners(real, "points", True), "points",
                      lambda r: f"{r['full_name']} scored {pts(r['points'])}.", lambda r: r["player_id"])

    pickups = real.merge(acquisitions, on=["roster_id", "player_id"], how="inner")
    pickups = pickups[pickups["type"].isin(PICKUP_TYPES)]
    out["pickup_of_the_week"] = rows(
        _winners(pickups, "points", True), "points",
        lambda r: f"{r['full_name']}, {PICKUP_TYPES[r['type']]} "
                  f"{'before the season' if r['is_preseason'] else 'in week ' + str(int(r['added_week']))}, scored {pts(r['points'])}.",
        lambda r: r["player_id"])

    zeros = starters[starters["points"] == 0].groupby("roster_id").size().rename("zero_starters").reset_index()
    zeros = zeros.merge(lineup[["roster_id", "bench_points_lost"]], on="roster_id")
    out["asleep_at_the_wheel"] = rows(
        _winners(zeros, "zero_starters", True, [("bench_points_lost", True)]), "zero_starters",
        lambda r: f"Started {int(r['zero_starters'])} player{'s' if r['zero_starters'] != 1 else ''} who scored 0.")
    return out


def latest_acquisitions(transactions, week):
    """Each team's most recent add of each player in weeks 1..week, with how it happened."""
    adds = transactions[(transactions["action"] == "add") & (transactions["week"] <= week)]
    adds = (adds.assign(_when=pd.to_datetime(adds["created_at"], utc=True))  # text when read back from CSV
            .sort_values(["_when", "transaction_id"]).drop_duplicates(["roster_id", "player_id"], keep="last"))
    return adds[["roster_id", "player_id", "type", "is_preseason"]].assign(added_week=adds["week"])


def build_awards(team_weeks, lineups, player_weeks, transactions, teams, params):
    """One row per enabled award per week (more when co-winners tie, none when nobody is eligible)."""
    check_params(params)
    names = teams.set_index("roster_id")["team_name"]
    out = []
    for (season, week), week_teams in team_weeks.groupby(["season", "week"], sort=True):
        key = (player_weeks["season"] == season) & (player_weeks["week"] == week)
        week_lineups = lineups[(lineups["season"] == season) & (lineups["week"] == week)]
        season_moves = transactions[transactions["season"] == season]
        awards = _week_awards(week_teams, player_weeks[key], week_lineups, latest_acquisitions(season_moves, week), names)
        for award in params["enabled"]:
            winners = awards[award]
            if award == "mvp" or award == "pickup_of_the_week":
                winners = _one_row_per_team(winners)
            for row in winners:
                out.append({"season": season, "week": week, "award": award, "award_name": AWARD_NAMES[award], **row})
    table = pd.DataFrame(out, columns=AWARDS_COLUMNS)
    order = {award: i for i, award in enumerate(params["enabled"])}
    table = table.assign(_order=table["award"].map(order)).sort_values(["season", "week", "_order", "roster_id"]).drop(columns="_order")
    return table.astype({"season": "int64", "week": "int64", "roster_id": "int64", "value": "float64",
                         "award": "string", "award_name": "string", "caption": "string", "player_id": "string"}).reset_index(drop=True)


def _one_row_per_team(rows):
    """If two players on the same team tie for a player award, keep one row naming both."""
    by_team = {}
    for row in rows:
        if row["roster_id"] in by_team:
            first = by_team[row["roster_id"]]
            first["caption"] = first["caption"].replace(" scored", " and " + row["caption"].split(" scored")[0] + " both scored", 1)
        else:
            by_team[row["roster_id"]] = dict(row)
    return list(by_team.values())


def main():
    from sleeper_dash.metrics import rebuild_from_saved

    tables, metric_tables, _ = rebuild_from_saved()
    report(metric_tables["awards"], tables)


def report(awards, tables):
    names = tables["teams"].set_index("roster_id")["team_name"]
    week = int(awards["week"].max())
    latest = awards[awards["week"] == week].copy()
    latest["team"] = latest["roster_id"].map(names)
    print(f"\nWEEK {week} AWARDS")
    for r in latest.itertuples():
        print(f"\n  {r.award_name}\n    {r.team}\n    {r.caption}")
    print(f"\n  {len(latest)} awards; {latest['roster_id'].nunique()} different teams; "
          f"most awarded: {latest['team'].value_counts().idxmax()} ({latest['team'].value_counts().max()})")

    history = awards.assign(team=awards["roster_id"].map(names)).pivot_table(
        index="award_name", columns="week", values="team", aggfunc=lambda s: " & ".join(s), sort=False)
    history.columns = [f"wk{w}" for w in history.columns]
    print("\n  Winners by week:")
    print("  " + history.to_string().replace("\n", "\n  "))


if __name__ == "__main__":
    main()
