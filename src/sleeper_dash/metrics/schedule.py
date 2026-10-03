"""Strength of schedule, played and remaining (docs/METRICS_SPEC.md section 5).

Run with:  python -m sleeper_dash.metrics.schedule   (rebuilds every metric table, checks, saves, and reports)

Pure functions: tables in, tables out. Parameters come from config.yaml metrics.schedule.
"""

import pandas as pd

SEASON_KEY = ["season", "through_week", "roster_id"]
SEASON_COLUMNS = SEASON_KEY + ["sos_played", "sos_remaining", "sos_games_played", "sos_games_remaining"]


def strength_of_schedule(team_weeks, schedule, params):
    """SOS for every team as of every completed week t (points per week; positive = harder).

    Opponent strength S_j(t) = team j's mean points over all completed weeks 1..t (playoffs
    included). Baseline B_i(t) = mean S of the other N − 1 teams. SOS played = mean S of the
    regular-season opponents in weeks 1..t, minus B_i(t); SOS remaining = the same over the
    regular-season weeks after t, from the published schedule. Each game counts once, so an
    opponent faced twice counts twice. Both values are null until min_weeks weeks are
    complete; remaining is null when no regular-season games are left. The game counts are
    always filled in.
    """
    min_weeks = params["min_weeks"]
    frames = []
    for season, through_week in team_weeks[["season", "week"]].drop_duplicates().sort_values(["season", "week"]).itertuples(index=False):
        strength = team_weeks[(team_weeks["season"] == season) & (team_weeks["week"] <= through_week)].groupby("roster_id")["points"].mean()
        baseline = (strength.sum() - strength) / (len(strength) - 1)
        completed_weeks = team_weeks.loc[(team_weeks["season"] == season) & (team_weeks["week"] <= through_week), "week"].nunique()

        games = schedule[(schedule["season"] == season) & schedule["opponent_roster_id"].notna()]
        games = games.assign(opponent_strength=games["opponent_roster_id"].astype("int64").map(strength))
        played = games[games["week"] <= through_week].groupby("roster_id")["opponent_strength"]
        remaining = games[games["week"] > through_week].groupby("roster_id")["opponent_strength"]

        table = pd.DataFrame(index=strength.index)
        table["sos_played"] = played.mean() - baseline
        table["sos_remaining"] = remaining.mean() - baseline
        table["sos_games_played"] = played.size().reindex(table.index, fill_value=0)
        table["sos_games_remaining"] = remaining.size().reindex(table.index, fill_value=0)
        if completed_weeks < min_weeks:
            table[["sos_played", "sos_remaining"]] = float("nan")
        table = table.rename_axis("roster_id").reset_index()
        table.insert(0, "season", season)
        table.insert(1, "through_week", through_week)
        frames.append(table)

    sos = pd.concat(frames, ignore_index=True)[SEASON_COLUMNS]
    # Adding 0.0 turns -0.0 (rounding noise around an exact zero) into 0.0.
    sos[["sos_played", "sos_remaining"]] = sos[["sos_played", "sos_remaining"]].astype("float64").round(2) + 0.0
    return sos.astype(
        {"season": "int64", "through_week": "int64", "roster_id": "int64",
         "sos_games_played": "int64", "sos_games_remaining": "int64"}
    ).sort_values(SEASON_KEY).reset_index(drop=True)


def main():
    from sleeper_dash.metrics import rebuild_from_saved

    tables, metric_tables, _ = rebuild_from_saved()
    report(metric_tables["metrics_season"], tables)


def report(season, tables):
    team_weeks, schedule = tables["team_weeks"], tables["schedule"]
    names = tables["teams"].set_index("roster_id")["team_name"]
    week = int(season["through_week"].max())
    strength = team_weeks[team_weeks["week"] <= week].groupby("roster_id")["points"].mean()
    latest = season[season["through_week"] == week].copy()
    latest["team_name"] = latest["roster_id"].map(names)
    latest["own_ppw"] = latest["roster_id"].map(strength).round(1)

    def opponents(rid, played):
        rows = schedule[(schedule["roster_id"] == rid) & ((schedule["week"] <= week) == played)]
        return ", ".join(f"{strength[int(o)]:.0f}" for o in rows["opponent_roster_id"].dropna())

    latest["opponents_ppw_played"] = latest["roster_id"].map(lambda r: opponents(r, True))
    latest = latest.sort_values("sos_played", ascending=False)

    print(f"\nSTRENGTH OF SCHEDULE THROUGH WEEK {week}, sorted by SOS played "
          "(opponents' points per week minus the average of the other 11 teams; + = harder)")
    columns = ["team_name", "own_ppw", "opponents_ppw_played", "sos_played", "sos_games_played", "sos_remaining", "sos_games_remaining"]
    print(latest[columns].to_string(index=False))
    print(f"\n  League points per week: mean {strength.mean():.1f}, SD across teams {strength.std():.1f}, "
          f"range {strength.min():.1f}–{strength.max():.1f}")
    print(f"  SOS played range {latest['sos_played'].min():+.1f} to {latest['sos_played'].max():+.1f}; "
          f"remaining range {latest['sos_remaining'].min():+.1f} to {latest['sos_remaining'].max():+.1f}")


if __name__ == "__main__":
    main()
