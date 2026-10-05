"""Integrity and reconciliation checks on the tidy tables.

Run with:  python -m sleeper_dash.validate   (checks the saved CSVs in data/processed/)

transform runs the same checks on its tables before saving them, so tables that
fail never overwrite the ones in data/processed/.
"""

import sys
from dataclasses import dataclass

import pandas as pd

TOLERANCE = 0.01  # points

KEYS = {
    "teams": ["season", "roster_id"],
    "team_weeks": ["season", "week", "roster_id"],
    "player_weeks": ["season", "week", "roster_id", "slot_order"],
    "transactions": ["transaction_id", "player_id", "action"],
    "schedule": ["season", "week", "roster_id"],
    "winners_bracket": ["season", "matchup_id"],
    "lineups_optimal":["season", "week", "roster_id"],
    "lineups_optimal_players": ["season", "week", "roster_id", "slot_order"],
    "metrics_team_weeks": ["season", "week", "roster_id"],
    "metrics_season": ["season", "through_week", "roster_id"],
    "power_rankings": ["season", "week", "roster_id"],
    "awards": ["season", "week", "award", "roster_id"],
    "playoff_odds": ["season", "week", "roster_id"],
    "managers": ["owner_id"],
}
LUCK_TOLERANCE = 1e-6  # wins
BASE_TABLES = ["teams", "team_weeks", "player_weeks", "transactions", "schedule", "winners_bracket"]  # built by transform
HISTORY_TABLES = ["managers"]                                                      # across seasons (seasons.py)
METRIC_TABLES = [name for name in KEYS if name not in BASE_TABLES + HISTORY_TABLES]  # built by lineup and metrics


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


class ValidationError(Exception):
    """One or more checks failed; the message lists every failure."""


def _result(name, problems, ok_detail):
    return CheckResult(name, not problems, "; ".join(problems) if problems else ok_detail)


def check_team_rows_per_week(team_weeks, league):
    """Every completed week, from the league's start week on, has one row per team."""
    expected = league["settings"]["num_teams"]
    counts = team_weeks.groupby("week").size()
    if counts.empty:
        return CheckResult("Every week has one row per team", True, "no completed weeks yet")
    problems = [f"week {w}: {n} rows, expected {expected}" for w, n in counts.items() if n != expected]
    start = 1  # not Sleeper's start_week, which is wrong for 2020 (see _regular_weeks)
    missing = sorted(set(range(start, counts.index.max() + 1)) - set(counts.index))
    if missing:
        problems.append(f"weeks missing entirely: {missing}")
    return _result("Every week has one row per team", problems, f"{len(counts)} weeks x {expected} teams")


def check_matchup_pairs(team_weeks):
    """Every non-null matchup_id appears exactly twice in its week."""
    games = team_weeks.dropna(subset=["matchup_id"]).groupby(["week", "matchup_id"]).size()
    problems = [f"week {w}, matchup {int(m)}: {n} teams" for (w, m), n in games.items() if n != 2]
    return _result("Each matchup has exactly 2 teams", problems, f"{len(games)} matchups checked")


def check_starter_points(player_weeks, team_weeks):
    """Starter points add up to the team's score in every team-week (within TOLERANCE)."""
    starters = player_weeks[player_weeks["is_starter"]]
    sums = starters.groupby(["week", "roster_id"])["points"].sum().rename("starter_points").reset_index()
    merged = team_weeks[["week", "roster_id", "points"]].merge(sums, on=["week", "roster_id"], how="outer")
    problems = []
    for row in merged.itertuples():
        if pd.isna(row.points) or pd.isna(row.starter_points):
            problems.append(f"week {row.week}, roster {row.roster_id}: missing from one of the tables")
        elif abs(row.points - row.starter_points) > TOLERANCE:
            problems.append(f"week {row.week}, roster {row.roster_id}: team {row.points:.2f} vs starters {row.starter_points:.2f}")
    return _result("Starter points equal team points", problems, f"{len(merged)} team-weeks within {TOLERANCE}")


def _sleeper_totals(rosters):
    def total(settings, whole, decimal):
        return settings.get(whole, 0) + settings.get(decimal, 0) / 100

    return {
        r["roster_id"]: {
            "W": r["settings"].get("wins", 0),
            "L": r["settings"].get("losses", 0),
            "T": r["settings"].get("ties", 0),
            "PF": total(r["settings"], "fpts", "fpts_decimal"),
            "PA": total(r["settings"], "fpts_against", "fpts_against_decimal"),
        }
        for r in rosters
    }


# Sleeper's roster totals have counted the regular season only (this league's 2025 season). In
# playoff weeks either standard is accepted (owner decision 2026-10-03): the totals must match one
# standard for every team, or the run stops. Before the playoffs every standard is the same.
REGULAR_SEASON = "regular season"


def _record_standards(team_weeks):
    """{standard: {roster_id: (W, L, T)}}: head-to-head plus median games, under each way Sleeper might count."""
    plays_median = "median_result" in team_weeks
    playoff = team_weeks[team_weeks["is_playoff"]]
    playoff_median = pd.Series("", index=playoff.index)
    if plays_median and len(playoff):  # transform plays no median in playoff weeks; compute the one Sleeper might
        median = playoff.groupby("week")["points"].transform("median")
        playoff_median = playoff_median.mask(playoff["points"] > median, "W").mask(playoff["points"] < median, "L")

    def records(include_games, include_median):
        rows = team_weeks if include_games else team_weeks[~team_weeks["is_playoff"]]
        out = {}
        for roster_id in sorted(team_weeks["roster_id"].unique()):
            games = rows[rows["roster_id"] == roster_id]
            w, l, t = (int((games["result"] == k).sum()) for k in ("W", "L", "T"))
            if plays_median:
                regular = games[~games["is_playoff"]]
                w += int((regular["median_result"] == "W").sum())
                l += int((regular["median_result"] == "L").sum())
                if include_median:
                    mine = playoff_median[playoff["roster_id"] == roster_id]
                    w, l = w + int((mine == "W").sum()), l + int((mine == "L").sum())
            out[int(roster_id)] = (w, l, t)
        return out

    standards = {REGULAR_SEASON: records(False, False)}
    if len(playoff):
        standards["regular season + playoff games"] = records(True, False)
        if plays_median:
            standards["regular season + playoff games and median"] = records(True, True)
    return standards


def _points_standards(team_weeks):
    """{standard: {roster_id: (points for, points against)}} under each way Sleeper might count."""
    def totals(for_rows, against_rows):
        return {int(rid): (for_rows.loc[for_rows["roster_id"] == rid, "points"].sum(),
                           against_rows.loc[against_rows["roster_id"] == rid, "opponent_points"].sum())
                for rid in sorted(team_weeks["roster_id"].unique())}

    playoff, has_game = team_weeks["is_playoff"], team_weeks["opponent_points"].notna()
    regular = team_weeks[~playoff]
    standards = {REGULAR_SEASON: totals(regular, regular)}
    if playoff.any():  # points against only exist where there was a game, so both playoff standards share them
        standards["regular season + playoff games"] = totals(team_weeks[~playoff | has_game], team_weeks)
        standards["regular season + every playoff week"] = totals(team_weeks, team_weeks)
    return standards


def _matching_standard(standards, sleeper, matches):
    """The first standard under which every team matches Sleeper, or None."""
    for name, ours in standards.items():
        if all(rid in ours and matches(ours[rid], sleeper[rid]) for rid in sleeper):
            return name
    return None


def check_records(team_weeks, rosters, league):
    """W-L-T matches Sleeper's roster settings, counting median games if the league plays them.

    Regular season only, as Sleeper counts it; in playoff weeks a standard that also counts playoff
    games (and a playoff median) is accepted too, as long as one standard fits every team.
    """
    sleeper = {rid: (s["W"], s["L"], s["T"]) for rid, s in _sleeper_totals(rosters).items()}
    standards = _record_standards(team_weeks)
    standard = _matching_standard(standards, sleeper, lambda ours, theirs: ours == theirs)
    problems = []
    if standard is None:
        regular = standards[REGULAR_SEASON]
        for roster_id, theirs in sorted(sleeper.items()):
            ours = regular.get(roster_id, (0, 0, 0))
            if ours != theirs:
                problems.append(f"roster {roster_id}: ours {'–'.join(map(str, ours))}, Sleeper {'–'.join(map(str, theirs))}")
        if len(standards) > 1:
            problems.append(f"no counting standard fits every team (tried: {', '.join(standards)})")
    note = "including median games" if league["settings"].get("league_average_match") == 1 else "head-to-head"
    return _result("Records match Sleeper", problems, f"{len(rosters)} teams, {note}; {standard or REGULAR_SEASON}")


def check_points_for_against(team_weeks, rosters):
    """Points for and against match Sleeper's fpts and fpts_against (within TOLERANCE).

    Regular season only, as Sleeper counts it; in playoff weeks a standard that also counts playoff
    points is accepted too, as long as one standard fits every team. Sleeper's totals arrive with any known
    gaps from config.yaml sleeper_points_gaps already added back (seasons.with_known_gaps); the detail says how many.
    """
    sleeper = {rid: (s["PF"], s["PA"]) for rid, s in _sleeper_totals(rosters).items()}
    known = sum(bool(r["settings"].get("known_points_gap")) for r in rosters)
    allowed = f"; {known} team(s) with a known Sleeper gap from config.yaml" if known else ""
    standards = _points_standards(team_weeks)
    close = lambda ours, theirs: abs(ours[0] - theirs[0]) <= TOLERANCE and abs(ours[1] - theirs[1]) <= TOLERANCE
    standard = _matching_standard(standards, sleeper, close)
    problems = []
    if standard is None:
        regular = standards[REGULAR_SEASON]
        for roster_id, (spf, spa) in sorted(sleeper.items()):
            pf, pa = regular.get(roster_id, (0.0, 0.0))
            if abs(pf - spf) > TOLERANCE:
                problems.append(f"roster {roster_id}: points for {pf:.2f} vs Sleeper {spf:.2f}")
            if abs(pa - spa) > TOLERANCE:
                problems.append(f"roster {roster_id}: points against {pa:.2f} vs Sleeper {spa:.2f}")
        if len(standards) > 1:
            problems.append(f"no counting standard fits every team (tried: {', '.join(standards)})")
    if problems and known:
        problems.append(f"after adding back {known} team(s)' known gaps from config.yaml sleeper_points_gaps")
    return _result("Points for/against match Sleeper", problems,
                   f"{len(rosters)} teams within {TOLERANCE}; {standard or REGULAR_SEASON}{allowed}")


def _regular_weeks(league):
    """Week 1 to the week before the playoffs. Sleeper's start_week setting is ignored: in 2020 it says 4,
    yet weeks 1-3 were played and count in Sleeper's own standings (owner, 2026-10-05)."""
    return list(range(1, league["settings"]["playoff_week_start"]))


def check_schedule(schedule, team_weeks, league):
    """The regular-season schedule is complete, symmetric, and agrees with the games already played.

    Every regular-season week has one row per team; pairings are symmetric (A plays B, B
    plays A); completed weeks are exactly the weeks in team_weeks and their pairings match it.
    """
    problems = []
    teams = league["settings"]["num_teams"]
    counts = schedule.groupby("week").size()
    for week in _regular_weeks(league):
        if counts.get(week, 0) != teams:
            problems.append(f"week {week}: {counts.get(week, 0)} schedule rows, expected {teams}")

    games = schedule.dropna(subset=["opponent_roster_id"])
    pairs = games.merge(games, left_on=["week", "roster_id", "opponent_roster_id"],
                        right_on=["week", "opponent_roster_id", "roster_id"], how="left", suffixes=("", "_other"))
    problems += [f"week {r.week}, roster {r.roster_id}: opponent {r.opponent_roster_id} doesn't list it back"
                 for r in pairs[pairs["matchup_id_other"].isna()].itertuples()]

    played_weeks = set(team_weeks["week"])
    wrong_flag = schedule[schedule["is_completed"].astype(bool) != schedule["week"].isin(played_weeks)]
    problems += [f"week {w}: is_completed is wrong" for w in sorted(wrong_flag["week"].unique())]

    regular = team_weeks[~team_weeks["is_playoff"].astype(bool)][["week", "roster_id", "opponent_roster_id"]]
    merged = regular.merge(schedule[["week", "roster_id", "opponent_roster_id"]], on=["week", "roster_id"], how="left", suffixes=("", "_sched"))
    ours, scheduled = merged["opponent_roster_id"].astype("Int64"), merged["opponent_roster_id_sched"].astype("Int64")
    mismatch = merged[(ours != scheduled).fillna(ours.isna() != scheduled.isna())]
    problems += [f"week {r.week}, roster {r.roster_id}: played {r.opponent_roster_id}, schedule says {r.opponent_roster_id_sched}"
                 for r in mismatch.itertuples()]
    return _result("Schedule is complete and matches games played", problems,
                   f"{len(_regular_weeks(league))} regular-season weeks x {teams} teams")


def check_consistency_and_sos(weekly, season, league):
    """Consistency and strength-of-schedule invariants (METRICS_SPEC.md sections 4 and 5).

    No week is both a boom and a bust; floor <= ceiling; volatility >= 0; booms + busts <= weeks.
    Games played + remaining = regular-season weeks, and games played = regular-season weeks so far.
    """
    problems = []
    both = weekly[weekly["is_boom"].astype(bool) & weekly["is_bust"].astype(bool)]
    problems += [f"week {r.week}, roster {r.roster_id}: both a boom and a bust" for r in both.itertuples()]
    where = lambda r: f"through week {r.through_week}, roster {r.roster_id}"
    problems += [f"{where(r)}: floor {r.floor} above ceiling {r.ceiling}" for r in season[season["floor"] > season["ceiling"]].itertuples()]
    problems += [f"{where(r)}: negative volatility" for r in season[season["volatility"] < 0].itertuples()]
    problems += [f"{where(r)}: more booms + busts than weeks" for r in season[season["boom_weeks"] + season["bust_weeks"] > season["weeks"]].itertuples()]

    regular = _regular_weeks(league)
    total = season["sos_games_played"] + season["sos_games_remaining"]
    problems += [f"{where(r)}: {r.sos_games_played} + {r.sos_games_remaining} games, expected {len(regular)}"
                 for r in season[total != len(regular)].itertuples()]
    so_far = season["through_week"].map(lambda t: sum(w <= t for w in regular))
    problems += [f"{where(r)}: {r.sos_games_played} games played, expected {so_far[r.Index]}"
                 for r in season[season["sos_games_played"] != so_far].itertuples()]
    return _result("Consistency and schedule metrics are consistent", problems,
                   f"{len(season)} team-season rows; every team has {len(regular)} regular-season games")


def check_power_rankings(rankings, team_weeks):
    """Power score invariants (METRICS_SPEC.md section 6, sanity checks 1, 2, and 6).

    One row per team per completed week; contributions sum to the power score; the league
    mean is 50 every week; scores lie in 0-100; ranks are 1..N with no duplicates; rank_change
    = previous week's rank − this week's rank.
    """
    problems = []
    key = ["season", "week", "roster_id"]
    merged = team_weeks[key].merge(rankings[key], on=key, how="outer", indicator="source")
    problems += [f"week {r.week}, roster {r.roster_id}: in only one of team_weeks and power_rankings"
                 for r in merged[merged["source"] != "both"].itertuples()]

    contributions = rankings[[c for c in rankings.columns if c.startswith("contrib_")]].sum(axis=1)
    problems += [f"week {r.week}, roster {r.roster_id}: contributions don't sum to the power score"
                 for r in rankings[(contributions - rankings["power_score"]).abs() > LUCK_TOLERANCE].itertuples()]
    problems += [f"week {r.week}, roster {r.roster_id}: power score {r.power_score:.2f} outside 0-100"
                 for r in rankings[~rankings["power_score"].between(0, 100)].itertuples()]
    for (season, week), g in rankings.groupby(["season", "week"]):
        if abs(g["power_score"].mean() - 50) > LUCK_TOLERANCE:
            problems.append(f"week {week}: league mean power score {g['power_score'].mean():.6f}, not 50")
        if sorted(g["rank"]) != list(range(1, len(g) + 1)):
            problems.append(f"week {week}: ranks are not 1..{len(g)} without duplicates")

    ordered = rankings.sort_values(key)
    previous = ordered.groupby(["season", "roster_id"])["rank"].shift(1)
    expected = (previous - ordered["rank"]).astype("Int64")
    actual = ordered["rank_change"].astype("Int64")
    wrong = ordered[(expected != actual).fillna(expected.isna() != actual.isna())]
    problems += [f"week {r.week}, roster {r.roster_id}: rank_change {r.rank_change} is wrong" for r in wrong.itertuples()]
    return _result("Power rankings are consistent", problems,
                   f"{rankings['week'].nunique()} weeks; mean 50, contributions add up, ranks 1-{rankings['roster_id'].nunique()}")


def check_awards(awards, team_weeks, lineups):
    """Weekly award invariants (METRICS_SPEC.md section 7, sanity checks 1-4).

    Top and lowest score equal the week's max and min points; every Heartbreaker lost and no
    loser scored more; every Robbery winner won and no winner scored less; Blowout equals the
    largest winning margin; Bench blunder equals that team's points left on the bench.
    """
    problems = []
    key = ["season", "week", "roster_id"]
    merged = awards.merge(team_weeks[key + ["points", "result", "margin"]], on=key, how="left")
    merged = merged.merge(lineups[key + ["bench_points_lost"]], on=key, how="left")
    weekly = team_weeks.groupby(["season", "week"])
    max_points, min_points = weekly["points"].max(), weekly["points"].min()
    loser_max = team_weeks[team_weeks["result"] == "L"].groupby(["season", "week"])["points"].max()
    winner_min = team_weeks[team_weeks["result"] == "W"].groupby(["season", "week"])["points"].min()
    margin_max = team_weeks[team_weeks["result"] == "W"].groupby(["season", "week"])["margin"].max()

    def off(a, b):
        return pd.isna(b) or abs(a - b) > TOLERANCE

    for r in merged.itertuples():
        wk, where = (r.season, r.week), f"week {r.week}, {r.award}, roster {r.roster_id}"
        if r.award in ("top_score", "lowest_score", "heartbreaker", "robbery") and off(r.value, r.points):
            problems.append(f"{where}: value {r.value} is not this team's score {r.points}")
        if r.award in ("blowout", "nail_biter") and off(r.value, r.margin):
            problems.append(f"{where}: value {r.value} is not this team's margin {r.margin}")
        if r.award == "top_score" and off(r.value, max_points.get(wk)):
            problems.append(f"{where}: {r.value} is not the week's top score")
        elif r.award == "lowest_score" and off(r.value, min_points.get(wk)):
            problems.append(f"{where}: {r.value} is not the week's lowest score")
        elif r.award == "heartbreaker" and (r.result != "L" or off(r.value, loser_max.get(wk))):
            problems.append(f"{where}: not the highest-scoring loser")
        elif r.award == "robbery" and (r.result != "W" or off(r.value, winner_min.get(wk))):
            problems.append(f"{where}: not the lowest-scoring winner")
        elif r.award == "blowout" and (r.result != "W" or off(r.value, margin_max.get(wk))):
            problems.append(f"{where}: not the largest winning margin")
        elif r.award == "bench_blunder" and off(r.value, r.bench_points_lost):
            problems.append(f"{where}: value {r.value} vs points left on the bench {r.bench_points_lost}")
    missing_caption = awards[awards["caption"].isna() | (awards["caption"].astype(str).str.strip() == "")]
    problems += [f"week {r.week}, {r.award}: empty caption" for r in missing_caption.itertuples()]
    return _result("Weekly awards are consistent", problems,
                   f"{len(awards)} awards over {awards['week'].nunique()} weeks match their source tables")


def check_optimal_lineups(lineups, chosen, team_weeks):
    """Optimal lineups are complete and consistent (METRICS_SPEC.md section 3, sanity checks 1 and 4).

    Every team-week has one, actual points equal the team score, optimal points are at
    least actual points and equal the sum of the chosen players, and no player is used twice.
    """
    key = ["season", "week", "roster_id"]
    merged = team_weeks[key + ["points"]].merge(lineups, on=key, how="outer", indicator="source")
    problems = [f"week {r.week}, roster {r.roster_id}: missing from {'lineups_optimal' if r.source == 'left_only' else 'team_weeks'}"
                for r in merged[merged["source"] != "both"].itertuples()]
    both = merged[merged["source"] == "both"]
    chosen_sum = chosen.groupby(key)["points"].sum().rename("chosen_points").reset_index()
    both = both.merge(chosen_sum, on=key, how="left")
    for r in both.itertuples():
        where = f"week {r.week}, roster {r.roster_id}"
        if abs(r.actual_points - r.points) > TOLERANCE:
            problems.append(f"{where}: actual {r.actual_points:.2f} vs team score {r.points:.2f}")
        if r.optimal_points < r.actual_points - TOLERANCE:
            problems.append(f"{where}: optimal {r.optimal_points:.2f} below actual {r.actual_points:.2f}")
        if pd.isna(r.chosen_points) or abs(r.optimal_points - r.chosen_points) > TOLERANCE:
            problems.append(f"{where}: optimal {r.optimal_points:.2f} vs chosen players' total {r.chosen_points}")
    filled = chosen[~chosen["is_empty_slot"].astype(bool)]
    reused = filled[filled.duplicated(key + ["player_id"])]
    problems += [f"week {r.week}, roster {r.roster_id}: player {r.player_id} used twice" for r in reused.itertuples()]
    return _result("Optimal lineups are consistent", problems, f"{len(both)} team-weeks; optimal >= actual")


def check_season_efficiency(season, lineups):
    """Season-to-date lineup efficiency (METRICS_SPEC.md section 3).

    For every team and through_week: efficiency = Σ actual ÷ Σ optimal over weeks 1…through_week
    (to the stored 4 dp), between 0 and 1, and null only when Σ optimal <= 0; points left on the
    bench = Σ (optimal − actual), within 0.01 and never negative. Every team-week of
    lineups_optimal needs a metrics_season row and vice versa.
    """
    problems = []
    frames = []
    for through_week in sorted(lineups["week"].unique()):
        totals = lineups[lineups["week"] <= through_week].groupby(["season", "roster_id"])[["actual_points", "optimal_points"]].sum()
        frames.append(totals.reset_index().assign(through_week=through_week))
    expected = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["season", "roster_id", "through_week"])
    key = ["season", "through_week", "roster_id"]
    merged = season[key + ["efficiency", "bench_points_lost"]].merge(expected, on=key, how="outer", indicator="source")
    where = lambda r: f"through week {r.through_week}, roster {r.roster_id}"
    problems += [f"{where(r)}: missing from {'metrics_season' if r.source == 'right_only' else 'lineups_optimal'}"
                 for r in merged[merged["source"] != "both"].itertuples()]
    for r in merged[merged["source"] == "both"].itertuples():
        if r.optimal_points <= 0:
            if pd.notna(r.efficiency):
                problems.append(f"{where(r)}: efficiency {r.efficiency} with no optimal points")
            continue
        ratio = r.actual_points / r.optimal_points
        if pd.isna(r.efficiency) or abs(r.efficiency - ratio) > 0.00005 + 1e-9:
            problems.append(f"{where(r)}: efficiency {r.efficiency} vs total actual / total optimal {ratio:.4f}")
        elif not 0 <= r.efficiency <= 1:
            problems.append(f"{where(r)}: efficiency {r.efficiency} outside 0–1")
        bench = r.optimal_points - r.actual_points
        if abs(r.bench_points_lost - bench) > TOLERANCE or r.bench_points_lost < 0:
            problems.append(f"{where(r)}: points left on the bench {r.bench_points_lost} vs {bench:.2f}")
    return _result("Season lineup efficiency is consistent", problems,
                   f"{(merged['source'] == 'both').sum()} team-season rows = total actual / total optimal")


def check_allplay_and_luck(weekly, season, team_weeks, rosters):
    """All-play and luck invariants (METRICS_SPEC.md sections 1 and 2).

    Per team-week, all-play W + L + T = teams that week − 1. Per week, the league's
    W + ½T = n(n − 1)/2. In regular-season weeks where every team played, expected wins sum
    to actual wins, so luck sums to 0. Median cross-check: median_result is W exactly when
    all-play wins >= n/2. Season totals for the last week equal the sum of the weekly rows,
    and the season record (head-to-head + median) equals Sleeper's roster wins/losses/ties.
    """
    problems = []
    week_key = ["season", "week"]
    n = weekly.groupby(week_key)["roster_id"].transform("size")
    games = weekly["allplay_wins"] + weekly["allplay_losses"] + weekly["allplay_ties"]
    for r in weekly[games != n - 1].itertuples():
        problems.append(f"week {r.week}, roster {r.roster_id}: all-play W+L+T is not {int(n[r.Index]) - 1}")

    by_week = weekly.assign(credit=weekly["allplay_wins"] + 0.5 * weekly["allplay_ties"], n=n).groupby(week_key)
    for (season_id, week), g in by_week:
        teams = int(g["n"].iloc[0])
        if abs(g["credit"].sum() - teams * (teams - 1) / 2) > LUCK_TOLERANCE:
            problems.append(f"week {week}: league all-play wins {g['credit'].sum()} != {teams * (teams - 1) / 2}")
        if g["actual_wins"].notna().all():
            if abs(g["expected_wins"].sum() - g["actual_wins"].sum()) > LUCK_TOLERANCE or abs(g["luck"].sum()) > LUCK_TOLERANCE:
                problems.append(f"week {week}: expected wins {g['expected_wins'].sum():.6f} vs actual {g['actual_wins'].sum()}; "
                                f"luck sums to {g['luck'].sum():.2e}")

    if "median_result" in team_weeks:
        merged = weekly.assign(n=n).merge(team_weeks[week_key + ["roster_id", "median_result"]], on=week_key + ["roster_id"])
        played = merged[merged["median_result"].notna()]
        mismatch = played[(played["median_result"] == "W") != (played["allplay_wins"] >= played["n"] / 2)]
        problems += [f"week {r.week}, roster {r.roster_id}: median_result {r.median_result} but all-play wins {r.allplay_wins}"
                     for r in mismatch.itertuples()]

    last = season[season["through_week"] == season["through_week"].max()].set_index("roster_id")
    sums = weekly.groupby("roster_id")[["allplay_wins", "actual_wins", "expected_wins", "luck"]].sum()
    for column in sums:
        diff = (last[column] - sums[column]).abs()
        problems += [f"roster {rid}: season {column} differs from the weekly total" for rid in diff[diff > LUCK_TOLERANCE].index]

    # The displayed record (head-to-head + median, regular season) must be Sleeper's official record.
    # In playoff weeks Sleeper may count playoff games too (see check_records): then the displayed
    # record must equal the regular-season record from the games, and Sleeper's must fit a standard.
    standards = _record_standards(team_weeks)
    official = {rid: (s["W"], s["L"], s["T"]) for rid, s in _sleeper_totals(rosters).items()}
    sleeper_fits = _matching_standard(standards, official, lambda ours, theirs: ours == theirs) is not None
    for roster_id, sleeper in sorted(official.items()):
        if roster_id not in last.index:
            problems.append(f"roster {roster_id}: missing from metrics_season")
            continue
        ours = tuple(int(last.at[roster_id, c]) for c in ("wins", "losses", "ties"))
        expected = standards[REGULAR_SEASON].get(roster_id)
        if not sleeper_fits and ours != sleeper:
            problems.append(f"roster {roster_id}: record {'–'.join(map(str, ours))} vs Sleeper {'–'.join(map(str, sleeper))}")
        elif ours != expected:
            problems.append(f"roster {roster_id}: record {'–'.join(map(str, ours))} vs "
                            f"{'–'.join(map(str, expected or ()))} from the regular-season games (Sleeper {'–'.join(map(str, sleeper))})")
    return _result("All-play and luck are consistent", problems,
                   f"{len(weekly)} team-weeks; luck sums to 0 each week; median cross-check agrees; records match Sleeper")


def _bracket_expectation(seeds):
    """{bye team: the two teams whose first-round winner it meets}, from roster_ids in seed order (verified format)."""
    return {seeds[0]: frozenset(seeds[3:5]), seeds[1]: frozenset((seeds[2], seeds[5]))}


def check_seeding_matches_sleeper(bracket, team_weeks, league):
    """Our seeding (wins, then points for) gives Sleeper's byes and first-round pairings (METRICS_SPEC.md section 8, check 8).

    During the regular season Sleeper's bracket is provisional, built from the current standings; from the
    playoffs on it is the real one, so it is compared with the final regular-season standings.
    """
    from sleeper_dash.metrics.playoff_odds import league_format, seeding, standings_through

    name = "Seeding matches Sleeper's bracket"
    regular = team_weeks.loc[~team_weeks["is_playoff"].astype(bool), "week"]
    if regular.empty or bracket.empty:
        return CheckResult(name, True, "Sleeper has no bracket yet; nothing to compare")
    try:
        fmt = league_format(league)
    except ValueError as error:
        return CheckResult(name, False, str(error))
    week = min(int(regular.max()), fmt["regular_weeks"])
    expected = _bracket_expectation(seeding(standings_through(team_weeks, week)))

    first_round = {int(g.matchup_id): frozenset((int(g.t1_roster_id), int(g.t2_roster_id)))
                   for g in bracket[bracket["round"] == 1].itertuples()
                   if pd.notna(g.t1_roster_id) and pd.notna(g.t2_roster_id)}
    sleeper = {}
    for g in bracket[bracket["round"] == 2].itertuples():
        for team, source, other in ((g.t1_roster_id, g.t1_from, g.t2_from), (g.t2_roster_id, g.t2_from, g.t1_from)):
            if pd.notna(team) and pd.isna(source) and isinstance(other, str) and other.startswith("W"):
                sleeper[int(team)] = first_round.get(int(other[1:]))
    if len(first_round) != 2 or len(sleeper) != 2 or None in sleeper.values():
        return CheckResult(name, True, "Sleeper's bracket isn't filled in yet; nothing to compare")

    def describe(pairings):
        return "; ".join(f"bye {bye} meets the {'/'.join(str(t) for t in sorted(pair))} winner"
                         for bye, pair in sorted(pairings.items()))

    problems = [] if sleeper == expected else [f"through week {week} our seeding gives {describe(expected)}, "
                                               f"but Sleeper's bracket has {describe(sleeper)}"]
    return _result(name, problems, f"through week {week}: byes and first-round pairings agree ({describe(expected)})")


def check_playoff_odds(odds, team_weeks, league):
    """Playoff odds invariants (METRICS_SPEC.md section 8, sanity checks 1-5, plus the seed probabilities).

    Every probability in 0-1; title and bye odds at most playoff odds; each week the playoff odds sum
    to 6, bye odds to 2, title odds to 1, and each seed's odds to 1; a team's seed odds sum to its
    playoff odds; average final wins add up to the season's total wins; Clinched teams have playoff
    odds 1 and Out teams 0; after the last regular-season week everything matches the final standings.
    """
    from sleeper_dash.metrics.playoff_odds import BYES, SEEDS, VERIFIED_FORMAT, league_format, seeding, standings_through

    name = "Playoff odds add up"
    if odds.empty:
        return CheckResult(name, True, "no playoff odds yet")
    fmt = league_format(league)
    tol = LUCK_TOLERANCE * fmt["n_teams"]
    seed_cols = [f"p_seed_{s}" for s in SEEDS]
    prob_cols = ["p_playoffs", "p_bye", "p_title"] + seed_cols
    problems = []
    out_of_range = odds[((odds[prob_cols] < 0) | (odds[prob_cols] > 1)).any(axis=1)]
    problems += [f"week {r.week}, roster {r.roster_id}: a probability outside 0-1" for r in out_of_range.itertuples()]
    above = odds[(odds["p_title"] > odds["p_playoffs"] + LUCK_TOLERANCE) | (odds["p_bye"] > odds["p_playoffs"] + LUCK_TOLERANCE)]
    problems += [f"week {r.week}, roster {r.roster_id}: title or bye odds above playoff odds" for r in above.itertuples()]
    seed_total = odds[seed_cols].sum(axis=1)
    problems += [f"week {odds.at[i, 'week']}, roster {odds.at[i, 'roster_id']}: seed odds sum to {seed_total[i]:.6f}, "
                 f"playoff odds {odds.at[i, 'p_playoffs']:.6f}"
                 for i in odds.index[(seed_total - odds["p_playoffs"]).abs() > LUCK_TOLERANCE]]
    byes = odds[seed_cols[:BYES]].sum(axis=1)
    problems += [f"week {odds.at[i, 'week']}, roster {odds.at[i, 'roster_id']}: bye odds aren't the seed 1 and 2 odds"
                 for i in odds.index[(byes - odds["p_bye"]).abs() > LUCK_TOLERANCE]]
    is_clinched, is_out = odds["clinched"].astype(bool), odds["out"].astype(bool)
    problems += [f"week {r.week}, roster {r.roster_id}: both clinched and out" for r in odds[is_clinched & is_out].itertuples()]
    problems += [f"week {r.week}, roster {r.roster_id}: clinched but playoff odds {r.p_playoffs}"
                 for r in odds[is_clinched & (odds["p_playoffs"] != 1)].itertuples()]
    problems += [f"week {r.week}, roster {r.roster_id}: out but odds above 0"
                 for r in odds[is_out & (odds[["p_playoffs", "p_bye", "p_title"]] != 0).any(axis=1)].itertuples()]

    wins_per_week = fmt["n_teams"] if fmt["median"] else fmt["n_teams"] // 2  # head-to-head winners plus median winners
    targets = {"p_playoffs": VERIFIED_FORMAT["playoff_teams"], "p_bye": BYES, "p_title": 1, **{c: 1 for c in seed_cols}}
    for (season, week), g in odds.groupby(["season", "week"]):
        if len(g) != fmt["n_teams"]:
            problems.append(f"week {week}: {len(g)} teams, expected {fmt['n_teams']}")
        for column, target in targets.items():
            if abs(g[column].sum() - target) > tol:
                problems.append(f"week {week}: {column} sums to {g[column].sum():.6f}, not {target}")
        season_weeks = team_weeks[team_weeks["season"] == season]
        so_far = season_weeks[(season_weeks["week"] <= week) & ~season_weeks["is_playoff"].astype(bool)]
        total_wins = fmt["regular_weeks"] * wins_per_week - int((so_far["result"] == "T").sum()) // 2
        if abs(g["avg_wins"].sum() - total_wins) > 0.001:  # each average is stored to 4 decimal places
            problems.append(f"week {week}: average final wins sum to {g['avg_wins'].sum():.4f}, not {total_wins}")
        if week == fmt["regular_weeks"]:
            seeds = seeding(standings_through(season_weeks, week))
            for r in g.itertuples():
                seed = seeds.index(r.roster_id) + 1
                wanted = {f"p_seed_{s}": float(s == seed) for s in SEEDS}
                if any(getattr(r, c) != v for c, v in wanted.items()) or r.p_playoffs != float(seed <= len(SEEDS)):
                    problems.append(f"week {week}, roster {r.roster_id}: odds don't match the final standings (seed {seed})")
    return _result(name, problems, f"{odds['week'].nunique()} weeks; each week 6 playoff spots, 2 byes, 1 title, "
                                   "every seed once; Clinched and Out consistent")


def check_managers(managers, teams):
    """Managers are matched across seasons by Sleeper owner ID (seasons.build_managers).

    Every team in every season has an owner listed in managers, no owner has two teams in one season,
    and each manager's seasons, first and last season, and name (from their latest season) agree with teams.
    """
    from sleeper_dash.seasons import build_managers

    problems = []
    if teams["owner_id"].isna().any():
        rows = teams[teams["owner_id"].isna()]
        problems += [f"{r.season} roster {r.roster_id}: no owner" for r in rows.itertuples()]
    doubled = teams.dropna(subset=["owner_id"]).groupby(["season", "owner_id"]).size()
    problems += [f"{season}: owner {owner} has {n} teams" for (season, owner), n in doubled[doubled > 1].items()]
    if managers["owner_id"].duplicated().any():
        problems.append("an owner appears twice in managers")
    expected = build_managers(teams).set_index("owner_id")
    actual = managers.astype({"owner_id": str}).set_index("owner_id")
    missing, extra = sorted(set(expected.index) - set(actual.index)), sorted(set(actual.index) - set(expected.index))
    problems += [f"owner {o} owns a team but isn't in managers" for o in missing]
    problems += [f"owner {o} is in managers but owns no team" for o in extra]
    both = expected.index.intersection(actual.index)
    for column in ["display_name", "first_season", "last_season", "seasons"]:
        wrong = [o for o in both if expected.at[o, column] != actual.at[o, column]]
        problems += [f"owner {o}: {column} is {actual.at[o, column]}, expected {expected.at[o, column]}" for o in wrong]
    seasons = teams["season"].nunique()
    every = int((actual["seasons"] == seasons).sum()) if len(actual) else 0
    return _result("Managers match across seasons by owner ID", problems,
                   f"{len(actual)} managers over {seasons} season(s); {every} played every season")


def check_unique_keys(tables, label=None):
    """No table has two rows with the same key."""
    problems = []
    for name, table in tables.items():
        dupes = int(table.duplicated(KEYS[name]).sum())
        if dupes:
            problems.append(f"{name}: {dupes} duplicate key(s) on ({', '.join(KEYS[name])})")
    return _result("No duplicate keys" + (f" ({label})" if label else ""), problems, f"{len(tables)} tables checked")


def run_data_checks(tables, league, rosters):
    """Checks on the tidy tables built by transform (BASE_TABLES): reconciliation with Sleeper and integrity."""
    team_weeks = tables["team_weeks"]
    results = [
        check_team_rows_per_week(team_weeks, league),
        check_matchup_pairs(team_weeks),
        check_starter_points(tables["player_weeks"], team_weeks),
        check_records(team_weeks, rosters, league),
        check_points_for_against(team_weeks, rosters),
    ]
    if "schedule" in tables:
        results.append(check_schedule(tables["schedule"], team_weeks, league))
    if "winners_bracket" in tables:
        results.append(check_seeding_matches_sleeper(tables["winners_bracket"], team_weeks, league))
    results.append(check_unique_keys({n: t for n, t in tables.items() if n not in METRIC_TABLES}, "data tables"))
    return results


def run_metric_checks(tables, league, rosters):
    """Invariant checks on the lineup and metric tables (METRICS_SPEC.md sanity checks). Uses the data tables as reference."""
    team_weeks = tables["team_weeks"]
    results = []
    if "lineups_optimal" in tables:
        results.append(check_optimal_lineups(tables["lineups_optimal"], tables["lineups_optimal_players"], team_weeks))
    if "metrics_team_weeks" in tables:
        results.append(check_allplay_and_luck(tables["metrics_team_weeks"], tables["metrics_season"], team_weeks, rosters))
        if "is_boom" in tables["metrics_team_weeks"]:
            results.append(check_consistency_and_sos(tables["metrics_team_weeks"], tables["metrics_season"], league))
        if "efficiency" in tables["metrics_season"] and "lineups_optimal" in tables:
            results.append(check_season_efficiency(tables["metrics_season"], tables["lineups_optimal"]))
    if "power_rankings" in tables:
        results.append(check_power_rankings(tables["power_rankings"], team_weeks))
    if "awards" in tables:
        results.append(check_awards(tables["awards"], team_weeks, tables["lineups_optimal"]))
    if "playoff_odds" in tables:
        results.append(check_playoff_odds(tables["playoff_odds"], team_weeks, league))
    metric_tables = {n: t for n, t in tables.items() if n in METRIC_TABLES}
    if metric_tables:
        results.append(check_unique_keys(metric_tables, "metric tables"))
    return results


def run_checks(tables, league, rosters):
    """Every check that applies to the tables given: data checks, then metric checks."""
    return run_data_checks(tables, league, rosters) + run_metric_checks(tables, league, rosters)


def combine_season_results(per_season):
    """One result per check from {season: [results]}: passed only if it passed in every season.

    A failure names each season it failed in; a pass shows the latest season's detail and how many
    earlier seasons also passed. With one season the results are unchanged.
    """
    if len(per_season) == 1:
        return next(iter(per_season.values()))
    latest = max(per_season)
    combined = []
    for result in per_season[latest]:
        rows = {season: r for season, results in per_season.items() for r in results if r.name == result.name}
        failed = {season: r for season, r in rows.items() if not r.passed}
        if failed:
            detail = "; ".join(f"{season}: {r.detail}" for season, r in sorted(failed.items(), reverse=True))
        else:
            earlier = len(rows) - 1
            detail = f"{latest}: {result.detail}" + (f"; passed in {earlier} earlier season(s) too" if earlier else "")
        combined.append(CheckResult(result.name, not failed, detail))
    return combined


def validate_seasons(by_season, checks=None, stage="Validation", extra=()):
    """validate() for several seasons: by_season = {season: (tables, league, rosters)}, each season checked
    against its own league settings and Sleeper standings. `extra` adds results already worked out across
    seasons (e.g. check_managers). Raises ValidationError listing every failure; returns the results."""
    per_season = {season: (checks or run_checks)(tables, league, rosters) for season, (tables, league, rosters) in by_season.items()}
    results = combine_season_results(per_season) + list(extra)
    failed = [r for r in results if not r.passed]
    if failed:
        raise ValidationError(
            f"{stage}: {len(failed)} check(s) failed; nothing was saved or published.\n\n" + format_results(results)
        )
    return results


def format_results(results):
    width = max(len(r.name) for r in results)
    lines = [f"{'Check':<{width}}  Result  Detail"]
    lines += [f"{r.name:<{width}}  {'PASS' if r.passed else 'FAIL':<6}  {r.detail}" for r in results]
    return "\n".join(lines)


def validate(tables, league, rosters, checks=None, stage="Validation"):
    """Run a group of checks (default: all); raise ValidationError listing all failures. Returns the results when all pass."""
    results = (checks or run_checks)(tables, league, rosters)
    failed = [r for r in results if not r.passed]
    if failed:
        raise ValidationError(
            f"{stage}: {len(failed)} check(s) failed; nothing was saved or published.\n\n" + format_results(results)
        )
    return results


def load_tables(processed_dir=None, names=None):
    """Read the saved tables back with IDs kept as text. names defaults to every table in KEYS."""
    from sleeper_dash.transform import PROCESSED_DIR

    processed_dir = processed_dir or PROCESSED_DIR
    tables = {}
    for name in names or KEYS:
        path = processed_dir / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing. Run `python -m sleeper_dash.pipeline` first.")
        tables[name] = pd.read_csv(
            path, dtype={"owner_id": str, "player_id": str, "transaction_id": str}, encoding="utf-8-sig"
        )
    return tables


def main():
    from sleeper_dash.config import load_config
    from sleeper_dash.seasons import league_files, season_slice

    tables = load_tables()
    files = league_files(sorted(int(s) for s in tables["teams"]["season"].unique()), load_config().sleeper_points_gaps)
    by_season = {season: (season_slice(tables, season), *files[season]) for season in files}
    data = combine_season_results({s: run_data_checks(*v) for s, v in by_season.items()})
    data.append(check_managers(tables["managers"], tables["teams"]))
    metric = combine_season_results({s: run_metric_checks(*v) for s, v in by_season.items()})
    print(f"Seasons: {', '.join(str(s) for s in files)}\n")
    print("DATA CHECKS\n" + format_results(data) + "\n\nMETRIC CHECKS\n" + format_results(metric))
    results = data + metric
    failed = sum(not r.passed for r in results)
    print(f"\n{len(results) - failed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
