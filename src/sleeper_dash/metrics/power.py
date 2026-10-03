"""Power score and weekly power rankings (docs/METRICS_SPEC.md section 6).

Run with:  python -m sleeper_dash.metrics.power   (rebuilds every metric table, checks, saves, and reports)

Pure functions: tables in, tables out. Every weight and parameter comes from
config.yaml metrics.power. Rankings are computed as of every completed week.
"""

import math

import pandas as pd

COMPONENTS = ["season_scoring", "recent_form", "roster_strength", "results"]
KEY = ["season", "week", "roster_id"]
POWER_RANKINGS_COLUMNS = KEY + ["rank", "rank_change", "power_score"] + COMPONENTS + [f"contrib_{c}" for c in COMPONENTS]
H2H_WINS = {"W": 1.0, "T": 0.5, "L": 0.0}
WEIGHT_TOLERANCE = 1e-6


def check_params(params, n_teams):
    """Stop with a clear message if the power settings in config.yaml can't work."""
    problems = []
    weights = params.get("weights") or {}
    if set(weights) != set(COMPONENTS):
        problems.append(f"weights must be exactly {COMPONENTS}; got {sorted(weights)}")
    elif any(not isinstance(w, (int, float)) or w < 0 for w in weights.values()):
        problems.append("every weight must be a number >= 0")
    elif abs(sum(weights.values()) - 1) > WEIGHT_TOLERANCE:
        problems.append(f"weights must sum to 1; they sum to {sum(weights.values()):.6f}")
    if not isinstance(params.get("recent_weeks"), int) or params["recent_weeks"] < 1:
        problems.append("recent_weeks must be a whole number of at least 1")
    if not isinstance(params.get("shrink_weeks"), (int, float)) or params["shrink_weeks"] < 0:
        problems.append("shrink_weeks must be a number >= 0")
    scale = params.get("scale")
    if not isinstance(scale, (int, float)) or scale <= 0:
        problems.append("scale must be a number > 0")
    elif n_teams > 1 and scale * (n_teams - 1) / math.sqrt(n_teams) > 50:
        problems.append(f"scale {scale} could push scores outside 0-100 with {n_teams} teams; "
                        f"the most it can be is {50 * math.sqrt(n_teams) / (n_teams - 1):.2f}")
    if problems:
        raise ValueError("config.yaml metrics.power: " + "; ".join(problems))


def components_as_of(team_weeks, lineups, through_week, recent_weeks):
    """The four raw components for every team, using completed weeks 1..through_week of one season."""
    so_far = team_weeks[team_weeks["week"] <= through_week]
    weeks = sorted(so_far["week"].unique())
    recent = so_far[so_far["week"].isin(weeks[-recent_weeks:])]
    regular = so_far[~so_far["is_playoff"].astype(bool) & so_far["result"].notna()]
    optimal = lineups[lineups["week"] <= through_week]
    return pd.DataFrame({
        "season_scoring": so_far.groupby("roster_id")["points"].mean(),
        "recent_form": recent.groupby("roster_id")["points"].mean(),
        "roster_strength": optimal.groupby("roster_id")["optimal_points"].mean(),
        "results": regular["result"].map(H2H_WINS).groupby(regular["roster_id"]).mean(),
    })


def standardise(values):
    """z-scores across teams with the population SD (divisor N); all zeros when there is no spread."""
    sd = values.std(ddof=0)
    if not sd > 1e-12:
        return values * 0.0
    return (values - values.mean()) / sd


def rank_teams(table):
    """Rank 1 = highest power score. Ties: season scoring, then head-to-head win %, then lower roster_id."""
    order = table.assign(_power=table["power_score"].round(9)).sort_values(
        ["_power", "season_scoring", "results", "roster_id"], ascending=[False, False, False, True]
    )
    return pd.Series(range(1, len(order) + 1), index=order.index)


def build_power_rankings(team_weeks, lineups, params):
    """Power score, rank, and rank change for every team as of every completed week.

    For week t: each component is standardised across teams (population SD), scaled by the
    early-season factor f = t / (t + shrink_weeks), and turned into a score 50 + scale·f·z.
    A component's contribution = weight × score; the power score is their sum, so the league
    mean is exactly 50. Rank change = previous week's rank − this week's rank (null in week 1).
    """
    n_teams = team_weeks.groupby(["season", "week"])["roster_id"].nunique().max()
    check_params(params, n_teams)
    weights = params["weights"]
    frames = []
    for season in sorted(team_weeks["season"].unique()):
        season_weeks = team_weeks[team_weeks["season"] == season]
        season_lineups = lineups[lineups["season"] == season]
        for count, week in enumerate(sorted(season_weeks["week"].unique()), start=1):
            table = components_as_of(season_weeks, season_lineups, week, params["recent_weeks"])
            if table.isna().any().any():
                missing = table[table.isna().any(axis=1)].index.tolist()
                raise ValueError(f"Week {week}: power score components missing for roster(s) {missing}.")
            factor = count / (count + params["shrink_weeks"])
            for c in COMPONENTS:
                table[f"contrib_{c}"] = weights[c] * (50 + params["scale"] * factor * standardise(table[c]))
            table["power_score"] = table[[f"contrib_{c}" for c in COMPONENTS]].sum(axis=1)
            table = table.rename_axis("roster_id").reset_index()
            table["rank"] = rank_teams(table)  # aligned on the row labels
            table.insert(0, "season", season)
            table.insert(1, "week", week)
            frames.append(table)

    rankings = pd.concat(frames, ignore_index=True).sort_values(KEY).reset_index(drop=True)
    previous = rankings.groupby(["season", "roster_id"])["rank"].shift(1)
    rankings["rank_change"] = (previous - rankings["rank"]).astype("Int64")
    return rankings[POWER_RANKINGS_COLUMNS].astype({"season": "int64", "week": "int64", "roster_id": "int64", "rank": "int64"})


def main():
    from sleeper_dash.metrics import rebuild_from_saved

    tables, metric_tables, config = rebuild_from_saved()
    report(metric_tables["power_rankings"], tables, config.metrics["power"])


def report(rankings, tables, params):
    names = tables["teams"].set_index("roster_id")["team_name"]
    week = int(rankings["week"].max())
    weights = params["weights"]
    latest = rankings[rankings["week"] == week].sort_values("rank").copy()
    count = rankings["week"].nunique()
    factor = count / (count + params["shrink_weeks"])

    latest["team"] = latest["roster_id"].map(names)
    latest["move"] = latest["rank_change"].map(lambda c: "—" if pd.isna(c) else ("▲" if c > 0 else "▼" if c < 0 else "=") + (str(abs(int(c))) if c else ""))
    # Contribution relative to an average team (50 x weight), so it's clear what lifts or sinks each score.
    for c in COMPONENTS:
        latest[f"{c}_vs_avg"] = (latest[f"contrib_{c}"] - 50 * weights[c]).map(lambda x: f"{x:+.1f}")
    latest["power"] = latest["power_score"].round(1)
    latest["raw"] = latest.apply(lambda r: f"{r['season_scoring']:.1f} / {r['recent_form']:.1f} / {r['roster_strength']:.1f} / {r['results']:.3f}", axis=1)

    print(f"\nPOWER RANKINGS AS OF WEEK {week}  (weights: " + ", ".join(f"{c} {weights[c]:.2f}" for c in COMPONENTS)
          + f"; early-season factor f = {count}/({count}+{params['shrink_weeks']}) = {factor:.2f})")
    print("  Each component column is its contribution above (+) or below (-) an average team; power = 50 + their sum.")
    columns = ["rank", "move", "team", "power"] + [f"{c}_vs_avg" for c in COMPONENTS] + ["raw"]
    print(latest[columns].rename(columns={f"{c}_vs_avg": c for c in COMPONENTS} | {"raw": "raw: pts/wk / recent / optimal / h2h win%"}).to_string(index=False))

    print("\n  Stored contributions (weight x component score; these sum to the power score):")
    stored = latest[["team"] + [f"contrib_{c}" for c in COMPONENTS] + ["power_score"]].round(2)
    print("  " + stored.to_string(index=False).replace("\n", "\n  "))

    history = rankings.pivot_table(index="roster_id", columns="week", values="rank").astype(int)
    history.columns = [f"wk{w}" for w in history.columns]
    history.insert(0, "team", history.index.map(names))
    print("\n  Rank by week:")
    print("  " + history.sort_values(f"wk{week}").to_string(index=False).replace("\n", "\n  "))
    means = rankings.groupby("week")["power_score"].mean()
    print(f"\n  League mean power score by week: {', '.join(f'{m:.6f}' for m in means)}; "
          f"range this week {latest['power_score'].min():.1f}–{latest['power_score'].max():.1f}")


if __name__ == "__main__":
    main()
