"""Metric modules (docs/METRICS_SPEC.md). Each is a set of pure functions; this file combines them.

Most modules add columns to the same two tables:
- metrics_team_weeks: one row per team per completed week (key: season, week, roster_id)
- metrics_season: one row per team as of every completed week (key: season, through_week, roster_id)
The power score has its own table, power_rankings (key: season, week, roster_id), and so do
the weekly awards (key: season, week, award, roster_id) and playoff odds (key: season, week, roster_id).
"""

TEAM_WEEK_KEY = ["season", "week", "roster_id"]
SEASON_KEY = ["season", "through_week", "roster_id"]


def build_metric_tables(tables, params, league=None):
    """Build every metric table from the tidy and lineup tables.

    params = config.yaml metrics section. league = Sleeper's league.json, whose playoff settings playoff
    odds need; without it (some tests) playoff_odds is left out.
    """
    from sleeper_dash.lineup import efficiency_season
    from sleeper_dash.metrics import allplay, awards, consistency, playoff_odds, power, schedule

    team_weeks = tables["team_weeks"]
    allplay_weekly = allplay.build_metrics_team_weeks(team_weeks)
    consistency_weekly = consistency.consistency_team_weeks(team_weeks, params["consistency"])

    allplay_season = allplay.build_metrics_season(allplay_weekly)

    weekly = allplay_weekly.merge(consistency_weekly, on=TEAM_WEEK_KEY, validate="one_to_one")
    season = (
        allplay_season
        .merge(consistency.consistency_season(team_weeks, consistency_weekly, params["consistency"]), on=SEASON_KEY, validate="one_to_one")
        .merge(schedule.strength_of_schedule(team_weeks, tables["schedule"], params["schedule"]), on=SEASON_KEY, validate="one_to_one")
        .merge(efficiency_season(tables["lineups_optimal"]), on=SEASON_KEY, validate="one_to_one")
    )
    if len(weekly) != len(team_weeks) or len(season) != len(allplay_season):
        raise ValueError("Metric tables lost rows while combining; check that every module covers the same team-weeks.")
    rankings = power.build_power_rankings(team_weeks, tables["lineups_optimal"], params["power"])
    weekly_awards = awards.build_awards(team_weeks, tables["lineups_optimal"], tables["player_weeks"],
                                        tables["transactions"], tables["teams"], params["awards"])
    built = {"metrics_team_weeks": weekly, "metrics_season": season, "power_rankings": rankings, "awards": weekly_awards}
    if league is not None:
        built["playoff_odds"] = playoff_odds.build_playoff_odds(team_weeks, tables["schedule"], league, params["playoff_odds"])
    return built


def rebuild_from_saved():
    """For the metric modules' command-line reports: rebuild every metric table from the saved
    tidy and lineup tables, validate, and save. Returns (input tables, metric tables, config)."""
    from sleeper_dash.config import PROJECT_ROOT, load_config
    from sleeper_dash.transform import read_raw, save_tables
    from sleeper_dash.validate import BASE_TABLES, ValidationError, load_tables, validate

    config = load_config()
    league, rosters = read_raw(config.season, "league.json"), read_raw(config.season, "rosters.json")
    tables = load_tables(names=BASE_TABLES + ["lineups_optimal", "lineups_optimal_players"])
    metric_tables = build_metric_tables(tables, config.metrics, league)
    try:
        validate({**tables, **metric_tables}, league, rosters)
    except ValidationError as error:
        raise SystemExit(str(error))
    for name, path in save_tables(metric_tables).items():
        print(f"Saved {len(metric_tables[name])} rows to {path.relative_to(PROJECT_ROOT).as_posix()}")
    return tables, metric_tables, config
