"""Playoff odds by simulating the rest of the season (docs/METRICS_SPEC.md section 8).

Run with:  python -m sleeper_dash.metrics.playoff_odds   (rebuilds every metric table, checks, saves, and reports)

Pure functions: tables in, tables out. Parameters come from config.yaml metrics.playoff_odds; the
playoff format comes from the league settings and must be the one verified in the spec.

For each completed regular-season week t from min_weeks on:
1. Relative scores d = points − that week's league mean (a league-wide swing changes no result).
2. Each team's strength: m̂ = t/(t+k) · mean d, uncertainty v = σ̂²/(t+k), with σ̂ the pooled
   within-team SD of d this season (one value for every team) and k = shrink_weeks.
3. Simulate: each team's true mean once per simulated season ~ N(m̂, v); each remaining week's
   score = true mean + N(0, σ̂²). Head-to-head games from the schedule, the median game from the
   same scores, seeding by wins then points for, then the bracket.
4. Summarise: playoff, bye, seed, and title odds (counts ÷ simulations), average final record,
   and Clinched / Out from a bound that proves them.
"""

import numpy as np
import pandas as pd

KEY = ["season", "week", "roster_id"]
# The one playoff format verified against Sleeper (METRICS_SPEC.md section 8); anything else stops the run.
VERIFIED_FORMAT = {"playoff_teams": 6, "playoff_round_type": 0, "playoff_seed_type": 0}
BYES = 2  # seeds 1 and 2 skip the first playoff week
PLAYOFF_ROUNDS = 3
SEEDS = list(range(1, VERIFIED_FORMAT["playoff_teams"] + 1))
PLAYOFF_ODDS_COLUMNS = (KEY + ["strength", "strength_sd", "score_sd", "p_playoffs", "p_bye"]
                        + [f"p_seed_{s}" for s in SEEDS] + ["p_title", "avg_wins", "avg_losses", "clinched", "out"])
PROBABILITY_DECIMALS = 6  # counts ÷ simulations; exact for 10,000 simulations
AVERAGE_DECIMALS = 4


def check_params(params):
    """Stop with a clear message if the playoff odds settings in config.yaml can't work."""
    problems = []
    sims = params.get("simulations")
    if not isinstance(sims, int) or isinstance(sims, bool) or sims < 1:
        problems.append("simulations must be a whole number of at least 1")
    seed = params.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        problems.append("seed must be a whole number of at least 0")
    k = params.get("shrink_weeks")
    if not isinstance(k, (int, float)) or isinstance(k, bool) or not k > 0:
        problems.append("shrink_weeks must be a number above 0")
    min_weeks = params.get("min_weeks")
    if not isinstance(min_weeks, int) or isinstance(min_weeks, bool) or min_weeks < 2:
        problems.append("min_weeks must be a whole number of at least 2 (the score SD needs two weeks per team)")
    if problems:
        raise ValueError("config.yaml metrics.playoff_odds: " + "; ".join(problems))


def league_format(league):
    """The league settings the simulation needs, after checking they are the verified format."""
    settings = league.get("settings") or {}
    problems = [f"{key} is {settings.get(key)!r}, expected {value}" for key, value in VERIFIED_FORMAT.items()
                if settings.get(key) != value]
    n_teams, median = settings.get("num_teams"), bool(settings.get("league_average_match"))
    if not isinstance(n_teams, int) or n_teams < VERIFIED_FORMAT["playoff_teams"]:
        problems.append(f"num_teams is {n_teams!r}; the playoffs need at least {VERIFIED_FORMAT['playoff_teams']} teams")
    elif median and n_teams % 2:
        problems.append(f"the median game with an odd number of teams ({n_teams}) has no defined rule")
    if problems:
        raise ValueError(
            "Playoff odds support only the playoff format verified in docs/METRICS_SPEC.md section 8 (6 teams, "
            "byes for seeds 1 and 2, one week per round, no reseeding). League settings: " + "; ".join(problems)
            + ". Update the spec and the code before running again.")
    return {"n_teams": n_teams, "median": median, "regular_weeks": int(settings["playoff_week_start"]) - 1}


def standings_through(team_weeks, week):
    """Regular-season standings through `week`: wins, losses, ties (head-to-head plus median), points for.

    `standing` = wins + ½ ties, the first seeding key. Index: roster_id, in roster_id order.
    """
    games = team_weeks[(team_weeks["week"] <= week) & ~team_weeks["is_playoff"].astype(bool)]
    by_team = games.groupby("roster_id")
    h2h = games["result"]
    median = games["median_result"] if "median_result" in games else pd.Series(index=games.index, dtype=object)
    table = pd.DataFrame({
        "wins": ((h2h == "W").astype(int) + (median == "W").astype(int)).groupby(games["roster_id"]).sum(),
        "losses": ((h2h == "L").astype(int) + (median == "L").astype(int)).groupby(games["roster_id"]).sum(),
        "ties": (h2h == "T").astype(int).groupby(games["roster_id"]).sum(),
        "points_for": by_team["points"].sum().round(2),
    }).sort_index()
    table["standing"] = table["wins"] + 0.5 * table["ties"]
    return table


def seeding(standings):
    """roster_ids in seed order: standing (wins + ½ ties), then points for, both highest first."""
    return standings.sort_values(["standing", "points_for"], ascending=False, kind="stable").index.tolist()


def tied_at_cutoff(standings, places):
    """Groups of teams level on wins and points for (to 2 dp) that straddle or sit inside the top `places`.

    Seeding among them has no known rule (spec: the run stops at the end of the regular season).
    """
    order = seeding(standings)
    key = standings[["standing", "points_for"]].round(2).apply(tuple, axis=1)
    groups = []
    for value in key[order[:places]].unique():
        tied = [rid for rid in order if key[rid] == value]
        if len(tied) > 1:
            groups.append(tied)
    return groups


def _relative_scores(team_weeks, week, teams):
    """Week × team array of points minus that week's league mean, regular-season weeks 1..week."""
    games = team_weeks[(team_weeks["week"] <= week) & ~team_weeks["is_playoff"].astype(bool)]
    points = games.pivot(index="week", columns="roster_id", values="points").reindex(columns=teams)
    if points.isna().any().any():
        raise ValueError(f"Playoff odds through week {week}: some teams have no score in some weeks.")
    values = points.to_numpy(dtype="float64")
    return values - values.mean(axis=1, keepdims=True)


def strength_estimates(d, shrink_weeks):
    """(m̂ per team, posterior SD per team, pooled score SD σ̂) from a week × team array of relative scores."""
    t, n = d.shape
    team_means = d.mean(axis=0)
    sigma = float(np.sqrt(((d - team_means) ** 2).sum() / (n * (t - 1))))
    strength = t / (t + shrink_weeks) * team_means
    strength_sd = np.full(n, sigma / np.sqrt(t + shrink_weeks))
    return strength, strength_sd, sigma


def _remaining_opponents(schedule, season, week, regular_weeks, teams):
    """For each regular-season week after `week`: an array giving each team's opponent's column, or −1 for no game."""
    column = {rid: i for i, rid in enumerate(teams)}
    future = schedule[(schedule["season"] == season) & (schedule["week"] > week) & (schedule["week"] <= regular_weeks)]
    weeks = []
    for w in range(week + 1, regular_weeks + 1):
        rows = future[future["week"] == w]
        if len(rows) != len(teams):
            raise ValueError(f"Playoff odds: the schedule for week {w} lists {len(rows)} teams, expected {len(teams)}.")
        opponents = np.full(len(teams), -1)
        for rid, opp in zip(rows["roster_id"], rows["opponent_roster_id"]):
            if pd.notna(opp):
                opponents[column[int(rid)]] = column[int(opp)]
        weeks.append(opponents)
    return weeks


def _play(scores, a, b):
    """Winners of games between team columns a and b (arrays over simulations); the higher seed (a) wins exact ties."""
    rows = np.arange(len(a))
    return np.where(scores[rows, a] >= scores[rows, b], a, b)


def simulate(standings, strength, strength_sd, sigma, opponents, fmt, sims, rng):
    """Simulate the rest of the season `sims` times. Returns counts and totals over simulations.

    Draw order (fixed: changing it changes the numbers): every team's true mean, then every team's
    score for each remaining regular-season week, then each playoff week.
    """
    n, weeks_left = len(standings), len(opponents)
    true_mean = strength + strength_sd * rng.standard_normal((sims, n))
    noise = rng.standard_normal((sims, weeks_left + PLAYOFF_ROUNDS, n))
    scores = true_mean[:, None, :] + sigma * noise

    wins = np.zeros((sims, n))
    points = np.zeros((sims, n))
    for g, opp in enumerate(opponents):
        week = scores[:, g, :]
        has_game = opp >= 0
        beat = np.zeros((sims, n), dtype=bool)
        beat[:, has_game] = week[:, has_game] > week[:, opp[has_game]]
        wins += beat
        if fmt["median"]:
            ranks = week.argsort(axis=1).argsort(axis=1)  # 0 = lowest score of the week
            wins += ranks >= n // 2
        points += week  # one week at a time, so the sum is the same on every machine

    final_standing = standings["standing"].to_numpy() + wins
    final_points = standings["points_for"].to_numpy() + points
    # Seed order per simulation: standing, then points for, highest first (lexsort sorts by the last key first).
    order = np.lexsort((-final_points, -final_standing), axis=1)
    seed_of = np.empty_like(order)
    np.put_along_axis(seed_of, order, np.arange(n)[None, :].repeat(sims, axis=0), axis=1)

    playoff = scores[:, weeks_left:, :]
    s = [order[:, i] for i in range(len(SEEDS))]  # s[0] is seed 1's column in every simulation
    w45 = _play(playoff[:, 0, :], s[3], s[4])
    w36 = _play(playoff[:, 0, :], s[2], s[5])
    finalist_a = _play(playoff[:, 1, :], s[0], w45)
    finalist_b = _play(playoff[:, 1, :], s[1], w36)
    champion = _play(playoff[:, 2, :], finalist_a, finalist_b)

    return {
        "seed_counts": np.stack([(seed_of == i).sum(axis=0) for i in range(len(SEEDS))], axis=1),  # team × seed
        "title_counts": np.bincount(champion, minlength=n),
        "simulated_wins": wins.sum(axis=0),
    }


def proven_status(standings, games_left, places):
    """(clinched, out) per team from a bound, ignoring that remaining opponents play each other.

    games_left: each team's remaining games (head-to-head plus median). Clinched: at most places − 1
    other teams can still reach this team's current standing. Out: at least `places` other teams
    already stand above this team's best possible finish.
    """
    current = standings["standing"].to_numpy()
    best = current + games_left
    clinched, out = [], []
    for i in range(len(current)):
        others = np.arange(len(current)) != i
        clinched.append(int((best[others] >= current[i]).sum()) <= places - 1)
        out.append(int((current[others] > best[i]).sum()) >= places)
    return np.array(clinched), np.array(out)


def odds_for_week(team_weeks, schedule, season, week, fmt, params):
    """One week's playoff odds table: one row per team, in roster_id order."""
    standings = standings_through(team_weeks, week)
    teams = standings.index.tolist()
    if len(teams) != fmt["n_teams"]:
        raise ValueError(f"Playoff odds through week {week}: {len(teams)} teams have results, expected {fmt['n_teams']}.")
    places = VERIFIED_FORMAT["playoff_teams"]
    d = _relative_scores(team_weeks, week, teams)
    strength, strength_sd, sigma = strength_estimates(d, params["shrink_weeks"])
    opponents = _remaining_opponents(schedule, season, week, fmt["regular_weeks"], teams)
    games_left = sum((opp >= 0).astype(int) for opp in opponents) if opponents else np.zeros(len(teams), dtype=int)
    if fmt["median"]:
        games_left = games_left + len(opponents)

    if not opponents:  # regular season over: the standings are final, so seeding is known
        ties = tied_at_cutoff(standings, places)
        if ties:
            raise ValueError(f"Week {week}: teams {ties} are level on wins and points for at the end of the regular "
                             "season, and no tiebreak rule beyond points for is known (METRICS_SPEC.md section 8).")

    seed = np.random.SeedSequence([params["seed"], int(season), int(week)])
    sims = params["simulations"]
    result = simulate(standings, strength, strength_sd, sigma, opponents, fmt, sims, np.random.default_rng(seed))

    seed_p = result["seed_counts"] / sims
    clinched, out = proven_status(standings, games_left, places)
    if not opponents:
        clinched, out = seed_p.sum(axis=1) == 1, seed_p.sum(axis=1) == 0
    # Games over the whole regular season: 2R with a median game, R without, when every team plays every week.
    total_games = standings[["wins", "losses", "ties"]].sum(axis=1).to_numpy() + games_left
    avg_wins = standings["wins"].to_numpy() + result["simulated_wins"] / sims

    table = pd.DataFrame({
        "season": int(season), "week": int(week), "roster_id": teams,
        "strength": np.round(strength, AVERAGE_DECIMALS), "strength_sd": np.round(strength_sd, AVERAGE_DECIMALS),
        "score_sd": round(sigma, AVERAGE_DECIMALS),
        "p_playoffs": np.round(seed_p.sum(axis=1), PROBABILITY_DECIMALS),
        "p_bye": np.round(seed_p[:, :BYES].sum(axis=1), PROBABILITY_DECIMALS),
        **{f"p_seed_{s}": np.round(seed_p[:, s - 1], PROBABILITY_DECIMALS) for s in SEEDS},
        "p_title": np.round(result["title_counts"] / sims, PROBABILITY_DECIMALS),
        "avg_wins": np.round(avg_wins, AVERAGE_DECIMALS),
        "avg_losses": np.round(total_games - avg_wins - standings["ties"].to_numpy(), AVERAGE_DECIMALS),
        "clinched": clinched, "out": out,
    })
    return table


def build_playoff_odds(team_weeks, schedule, league, params):
    """Playoff odds for every team as of every completed regular-season week from min_weeks on."""
    check_params(params)
    fmt = league_format(league)
    frames = []
    for season in sorted(team_weeks["season"].unique()):
        season_weeks = team_weeks[team_weeks["season"] == season]
        regular = sorted(int(w) for w in season_weeks.loc[~season_weeks["is_playoff"].astype(bool), "week"].unique())
        for week in regular:
            if params["min_weeks"] <= week <= fmt["regular_weeks"]:
                frames.append(odds_for_week(season_weeks, schedule, season, week, fmt, params))
    if not frames:
        return pd.DataFrame({c: pd.Series(dtype="bool" if c in ("clinched", "out") else "int64" if c in KEY else "float64")
                             for c in PLAYOFF_ODDS_COLUMNS})
    odds = pd.concat(frames, ignore_index=True)[PLAYOFF_ODDS_COLUMNS]
    # Adding 0.0 turns -0.0 into 0.0, so files don't change on rounding noise.
    floats = [c for c in PLAYOFF_ODDS_COLUMNS if c not in KEY + ["clinched", "out"]]
    odds[floats] = odds[floats].astype("float64") + 0.0
    return odds.astype({"season": "int64", "week": "int64", "roster_id": "int64"}).sort_values(KEY).reset_index(drop=True)


def main():
    from sleeper_dash.metrics import rebuild_from_saved

    tables, metric_tables, config = rebuild_from_saved()
    report(metric_tables["playoff_odds"], tables, config.metrics["playoff_odds"])


def pct(p):
    return f"{p * 100:.1f}%"


def report(odds, tables, params):
    if odds.empty:
        print(f"\nPLAYOFF ODDS: none yet (they start at week {params['min_weeks']}).")
        return
    names = tables["teams"].set_index("roster_id")["team_name"]
    week = int(odds["week"].max())
    latest = odds[odds["week"] == week].copy()
    standings = standings_through(tables["team_weeks"], week)
    latest["team"] = latest["roster_id"].map(names)
    latest["record"] = latest["roster_id"].map(lambda r: f"{standings.at[r, 'wins']}–{standings.at[r, 'losses']}")
    latest["PF"] = latest["roster_id"].map(standings["points_for"])
    latest["proj"] = latest.apply(lambda r: f"{r.avg_wins:.1f}–{r.avg_losses:.1f}", axis=1)
    latest = latest.sort_values(["p_playoffs", "p_bye", "avg_wins"], ascending=False)
    print(f"\nPLAYOFF ODDS AFTER WEEK {week}  ({params['simulations']:,} simulations, shrink_weeks {params['shrink_weeks']}, "
          f"score SD {latest['score_sd'].iloc[0]:.1f})")
    shown = latest[["team", "record", "PF", "strength", "proj", "p_playoffs", "p_bye"] + [f"p_seed_{s}" for s in SEEDS]
                   + ["p_title", "clinched", "out"]].copy()
    for c in ["p_playoffs", "p_bye", "p_title"] + [f"p_seed_{s}" for s in SEEDS]:
        shown[c] = shown[c].map(pct)
    shown["strength"] = shown["strength"].map(lambda x: f"{x:+.1f}")
    print(shown.to_string(index=False))
    print(f"\n  Sums: playoffs {latest['p_playoffs'].sum():.4f}, byes {latest['p_bye'].sum():.4f}, "
          f"titles {latest['p_title'].sum():.4f}; average final wins {latest['avg_wins'].sum():.2f}")


if __name__ == "__main__":
    main()
