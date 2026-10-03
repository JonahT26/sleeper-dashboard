"""All-play record, expected wins, and luck (docs/METRICS_SPEC.md sections 1 and 2).

Run with:  python -m sleeper_dash.metrics.allplay   (rebuilds from the saved tables, checks, saves, and reports)

Pure functions: tables in, tables out. Reading and saving files happens in main().

- All-play covers every week and every team, playoffs included (owner decision).
- Expected wins, actual wins, and luck cover regular-season head-to-head games only;
  from the first playoff week on, their season-to-date totals stay frozen.
"""

import pandas as pd

KEY = ["season", "week", "roster_id"]
METRICS_TEAM_WEEKS_COLUMNS = KEY + [
    "allplay_wins", "allplay_losses", "allplay_ties", "allplay_win_pct", "actual_wins", "expected_wins", "luck",
]
METRICS_SEASON_COLUMNS = ["season", "through_week", "roster_id"] + [
    "allplay_wins", "allplay_losses", "allplay_ties", "allplay_win_pct",
    "h2h_wins", "h2h_losses", "h2h_ties", "games", "actual_wins", "expected_wins", "luck",
]
ACTUAL_WINS = {"W": 1.0, "T": 0.5, "L": 0.0}  # head-to-head result -> actual wins


def allplay_team_weeks(team_weeks):
    """Weekly all-play record for every team-week (spec section 1).

    Each team is compared with every other team that scored that week (n_w teams):
    wins = teams with fewer points, losses = teams with more, ties = teams with equal points.
    Points are compared at 2 decimal places. Win % = (wins + ½ ties) ÷ (n_w − 1).
    """
    rows = team_weeks[KEY].copy()
    points = team_weeks["points"].round(2)
    by_week = points.groupby([team_weeks["season"], team_weeks["week"]])
    at_or_below = by_week.rank(method="max").astype("int64")    # teams scoring <= this team, itself included
    below = by_week.rank(method="min").astype("int64") - 1      # teams scoring < this team
    teams = by_week.transform("size").astype("int64")

    rows["allplay_wins"] = below
    rows["allplay_ties"] = at_or_below - below - 1
    rows["allplay_losses"] = teams - at_or_below
    others = teams - 1
    rows["allplay_win_pct"] = ((below + 0.5 * rows["allplay_ties"]) / others).where(others > 0)
    return rows


def build_metrics_team_weeks(team_weeks):
    """One row per team per completed week: all-play record, actual wins, expected wins, and luck.

    Actual wins = 1 / ½ / 0 for a head-to-head win / tie / loss. Expected wins = that week's
    all-play win %. Luck = actual − expected. The last three are null in playoff weeks
    (spec section 2) and for any team-week without a head-to-head game.
    """
    table = allplay_team_weeks(team_weeks)
    has_game = ~team_weeks["is_playoff"].astype(bool) & team_weeks["result"].notna()
    table["actual_wins"] = team_weeks["result"].map(ACTUAL_WINS).where(has_game).astype("float64")
    table["expected_wins"] = table["allplay_win_pct"].where(has_game)
    table["luck"] = table["actual_wins"] - table["expected_wins"]
    table = table[METRICS_TEAM_WEEKS_COLUMNS].astype(
        {"season": "int64", "week": "int64", "roster_id": "int64", "allplay_wins": "int64",
         "allplay_losses": "int64", "allplay_ties": "int64", "allplay_win_pct": "float64",
         "actual_wins": "float64", "expected_wins": "float64", "luck": "float64"}
    )
    return table.sort_values(KEY).reset_index(drop=True)


def build_metrics_season(metrics_team_weeks):
    """Season-to-date totals for every team as of every completed week (key: season, through_week, roster_id).

    All-play sums every week through `through_week`; win % = (Σ wins + ½ Σ ties) ÷ Σ comparisons.
    Head-to-head record, games, actual wins, expected wins, and luck sum regular-season
    weeks only, so they stop changing once the playoffs start.
    """
    weekly = metrics_team_weeks.assign(
        h2h_wins=(metrics_team_weeks["actual_wins"] == 1.0).astype("int64"),
        h2h_losses=(metrics_team_weeks["actual_wins"] == 0.0).astype("int64"),
        h2h_ties=(metrics_team_weeks["actual_wins"] == 0.5).astype("int64"),
        games=metrics_team_weeks["actual_wins"].notna().astype("int64"),
    )
    sums = ["allplay_wins", "allplay_losses", "allplay_ties", "h2h_wins", "h2h_losses", "h2h_ties", "games",
            "actual_wins", "expected_wins", "luck"]

    frames = []
    for (season, through_week) in weekly[["season", "week"]].drop_duplicates().sort_values(["season", "week"]).itertuples(index=False):
        so_far = weekly[(weekly["season"] == season) & (weekly["week"] <= through_week)]
        totals = so_far.groupby("roster_id")[sums].sum().reset_index()  # sum of all-null luck is 0: no games yet
        totals.insert(0, "season", season)
        totals.insert(1, "through_week", through_week)
        frames.append(totals)

    season = pd.concat(frames, ignore_index=True)
    comparisons = season["allplay_wins"] + season["allplay_losses"] + season["allplay_ties"]
    season["allplay_win_pct"] = ((season["allplay_wins"] + 0.5 * season["allplay_ties"]) / comparisons).where(comparisons > 0)
    season = season[METRICS_SEASON_COLUMNS].astype(
        {"season": "int64", "through_week": "int64", "roster_id": "int64", "allplay_win_pct": "float64",
         "actual_wins": "float64", "expected_wins": "float64", "luck": "float64"}
    )
    return season.sort_values(["season", "through_week", "roster_id"]).reset_index(drop=True)


def build_allplay_tables(tables):
    """Add-on for the pipeline: {metrics_team_weeks, metrics_season} from team_weeks."""
    weekly = build_metrics_team_weeks(tables["team_weeks"])
    return {"metrics_team_weeks": weekly, "metrics_season": build_metrics_season(weekly)}


def record_text(wins, losses, ties):
    """Display rule from the spec: "41–14", with ties only when there are any ("41–13–1")."""
    return f"{wins}–{losses}" + (f"–{ties}" if ties else "")


def main():
    from sleeper_dash.config import PROJECT_ROOT, load_config
    from sleeper_dash.transform import read_raw, save_tables
    from sleeper_dash.validate import BASE_TABLES, ValidationError, load_tables, validate

    season = load_config().season
    league, rosters = read_raw(season, "league.json"), read_raw(season, "rosters.json")
    tables = load_tables(names=BASE_TABLES)
    metric_tables = build_allplay_tables(tables)
    try:
        validate({**tables, **metric_tables}, league, rosters)
    except ValidationError as error:
        raise SystemExit(str(error))
    for name, path in save_tables(metric_tables).items():
        print(f"Saved {len(metric_tables[name])} rows to {path.relative_to(PROJECT_ROOT).as_posix()}")

    names = tables["teams"].set_index("roster_id")["team_name"]
    _report_season(metric_tables["metrics_season"], tables["team_weeks"], names)
    _report_weekly(metric_tables["metrics_team_weeks"])


def _report_season(season, team_weeks, names):
    latest = season[season["through_week"] == season["through_week"].max()].copy()
    week = int(latest["through_week"].iloc[0])
    points = team_weeks[team_weeks["week"] <= week].groupby("roster_id")["points"].sum()
    latest["team_name"] = latest["roster_id"].map(names)
    latest["record"] = [record_text(*r) for r in latest[["h2h_wins", "h2h_losses", "h2h_ties"]].itertuples(index=False)]
    latest["all_play"] = [record_text(*r) for r in latest[["allplay_wins", "allplay_losses", "allplay_ties"]].itertuples(index=False)]
    latest["all_play_pct"] = (100 * latest["allplay_win_pct"]).round(1)
    latest["points_for"] = latest["roster_id"].map(points).round(2)
    totals = latest[["actual_wins", "expected_wins", "luck"]].sum()  # before rounding for display
    latest["actual_wins"] = latest["actual_wins"].round(1)
    latest["expected_wins"] = latest["expected_wins"].round(2)
    latest["luck_signed"] = latest["luck"].map(lambda x: f"{x:+.2f}")
    latest = latest.sort_values(["luck", "expected_wins"], ascending=[False, False])

    print(f"\nSEASON THROUGH WEEK {week}, sorted by luck (actual head-to-head wins minus expected wins)")
    columns = ["team_name", "record", "all_play", "all_play_pct", "points_for", "actual_wins", "expected_wins", "luck_signed"]
    print(latest[columns].rename(columns={"all_play_pct": "all_play_%", "luck_signed": "luck"}).to_string(index=False))
    print(f"\n  League totals: actual wins {totals['actual_wins']:.1f}, expected wins {totals['expected_wins']:.6f}, "
          f"luck {totals['luck']:+.6f}")
    print(f"  Luck: SD across teams {latest['luck'].std():.2f}; luckiest {latest['luck'].max():+.2f}, unluckiest {latest['luck'].min():+.2f}")


def _report_weekly(weekly):
    print("\nINVARIANTS BY WEEK")
    summary = weekly.groupby("week").agg(
        teams=("roster_id", "size"),
        min_W_plus_L_plus_T=("allplay_wins", lambda s: int((s + weekly.loc[s.index, "allplay_losses"] + weekly.loc[s.index, "allplay_ties"]).min())),
        max_W_plus_L_plus_T=("allplay_wins", lambda s: int((s + weekly.loc[s.index, "allplay_losses"] + weekly.loc[s.index, "allplay_ties"]).max())),
        all_play_ties=("allplay_ties", "sum"),
        actual_wins=("actual_wins", "sum"),
        expected_wins=("expected_wins", "sum"),
        luck_sum=("luck", "sum"),
    )
    summary["expected_wins"] = summary["expected_wins"].round(6)
    summary["luck_sum"] = summary["luck_sum"].map(lambda x: f"{x:+.1e}")
    print(summary.to_string())


if __name__ == "__main__":
    main()
