"""Consistency: volatility, floor and ceiling, boom and bust weeks (docs/METRICS_SPEC.md section 4).

Run with:  python -m sleeper_dash.metrics.consistency   (rebuilds every metric table, checks, saves, and reports)

Pure functions: tables in, tables out. Parameters come from config.yaml metrics.consistency.
Every week and every team counts, playoffs included (owner decision).
"""

import pandas as pd

KEY = ["season", "week", "roster_id"]
SEASON_KEY = ["season", "through_week", "roster_id"]
TEAM_WEEK_COLUMNS = KEY + ["points_vs_median", "is_boom", "is_bust"]
SEASON_COLUMNS = SEASON_KEY + [
    "weeks", "volatility", "floor", "ceiling", "boom_weeks", "bust_weeks", "boom_rate", "bust_rate",
]


def check_params(params):
    """Stop with a clear message if the consistency settings in config.yaml can't work."""
    problems = []
    if not params.get("boom_margin", 0) > 0 or not params.get("bust_margin", 0) > 0:
        problems.append("boom_margin and bust_margin must both be greater than 0 (otherwise a week could be both)")
    if not 0 <= params.get("floor_pct", -1) <= params.get("ceiling_pct", -1) <= 1:
        problems.append("floor_pct and ceiling_pct must satisfy 0 <= floor_pct <= ceiling_pct <= 1")
    if not isinstance(params.get("min_weeks"), int) or params["min_weeks"] < 2:
        problems.append("min_weeks must be a whole number of at least 2 (a standard deviation needs two weeks)")
    if problems:
        raise ValueError("config.yaml metrics.consistency: " + "; ".join(problems))


def consistency_team_weeks(team_weeks, params):
    """Per team-week: score relative to that week's league median, and whether it was a boom or a bust.

    points_vs_median = points − median of every team's points that week, rounded to 3 dp
    (a median of 2-dp scores has at most 3 dp), so a score exactly on a threshold counts.
    """
    check_params(params)
    points = team_weeks["points"].round(2)
    median = points.groupby([team_weeks["season"], team_weeks["week"]]).transform("median")
    table = team_weeks[KEY].copy()
    table["points_vs_median"] = (points - median).round(3)
    table["is_boom"] = table["points_vs_median"] >= params["boom_margin"]
    table["is_bust"] = table["points_vs_median"] <= -params["bust_margin"]
    return table[TEAM_WEEK_COLUMNS].sort_values(KEY).reset_index(drop=True)


def consistency_season(team_weeks, weekly, params):
    """Season-to-date consistency for every team as of every completed week.

    volatility = sample SD (n − 1) of points_vs_median; floor and ceiling = the floor_pct and
    ceiling_pct percentiles of weekly points (linear interpolation). All three are null until
    a team has min_weeks weeks. Boom and bust counts and rates are shown from week 1.
    """
    check_params(params)
    data = weekly.merge(team_weeks[KEY + ["points"]], on=KEY, validate="one_to_one")
    frames = []
    for season, through_week in data[["season", "week"]].drop_duplicates().sort_values(["season", "week"]).itertuples(index=False):
        so_far = data[(data["season"] == season) & (data["week"] <= through_week)].groupby("roster_id")
        table = pd.DataFrame({
            "weeks": so_far.size(),
            "volatility": so_far["points_vs_median"].std(ddof=1),
            "floor": so_far["points"].quantile(params["floor_pct"], interpolation="linear"),
            "ceiling": so_far["points"].quantile(params["ceiling_pct"], interpolation="linear"),
            "boom_weeks": so_far["is_boom"].sum(),
            "bust_weeks": so_far["is_bust"].sum(),
        })
        too_few = table["weeks"] < params["min_weeks"]
        table.loc[too_few, ["volatility", "floor", "ceiling"]] = float("nan")
        table["boom_rate"] = table["boom_weeks"] / table["weeks"]
        table["bust_rate"] = table["bust_weeks"] / table["weeks"]
        table = table.reset_index()
        table.insert(0, "season", season)
        table.insert(1, "through_week", through_week)
        frames.append(table)

    season = pd.concat(frames, ignore_index=True)[SEASON_COLUMNS]
    season[["volatility", "floor", "ceiling"]] = season[["volatility", "floor", "ceiling"]].round(2)
    return season.astype(
        {"season": "int64", "through_week": "int64", "roster_id": "int64", "weeks": "int64",
         "boom_weeks": "int64", "bust_weeks": "int64"}
    ).sort_values(SEASON_KEY).reset_index(drop=True)


def main():
    from sleeper_dash.metrics import rebuild_from_saved

    tables, metric_tables, config = rebuild_from_saved()
    report(metric_tables["metrics_season"], metric_tables["metrics_team_weeks"], tables, config.metrics["consistency"])


def report(season, weekly, tables, params):
    names = tables["teams"].set_index("roster_id")["team_name"]
    week = int(season["through_week"].max())
    latest = season[season["through_week"] == week].copy()
    points = tables["team_weeks"][tables["team_weeks"]["week"] <= week].groupby("roster_id")["points"]
    latest["team_name"] = latest["roster_id"].map(names)
    latest["mean_points"] = latest["roster_id"].map(points.mean()).round(1)
    latest["weekly_scores"] = latest["roster_id"].map(points.apply(lambda s: " / ".join(f"{p:.1f}" for p in s)))
    vs_median = weekly[weekly["week"] <= week].groupby("roster_id")["points_vs_median"]
    latest["vs_median"] = latest["roster_id"].map(vs_median.apply(lambda s: " / ".join(f"{d:+.1f}" for d in s)))
    latest = latest.sort_values("volatility", ascending=False)

    print(f"\nCONSISTENCY THROUGH WEEK {week}, sorted by volatility (SD of score minus the weekly league median)")
    print(f"  Boom: >= median + {params['boom_margin']}; bust: <= median - {params['bust_margin']}; "
          f"floor/ceiling = {params['floor_pct']:.0%}/{params['ceiling_pct']:.0%} percentiles of weekly points")
    columns = ["team_name", "weekly_scores", "vs_median", "mean_points", "volatility", "floor", "ceiling", "boom_weeks", "bust_weeks"]
    print(latest[columns].to_string(index=False))
    league = weekly[weekly["week"] <= week]
    print(f"\n  League: {int(league['is_boom'].sum())} booms and {int(league['is_bust'].sum())} busts in {len(league)} team-weeks "
          f"({league['is_boom'].mean():.0%} / {league['is_bust'].mean():.0%}); "
          f"volatility median {latest['volatility'].median():.1f}, range {latest['volatility'].min():.1f}–{latest['volatility'].max():.1f}")


if __name__ == "__main__":
    main()
