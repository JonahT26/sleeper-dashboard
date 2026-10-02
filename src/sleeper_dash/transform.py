"""Build tidy tables in data/processed/ from the raw JSON in data/raw/{season}/.

Run with:  python -m sleeper_dash.transform

Reads raw files only; never calls the Sleeper API.
"""

import json
import statistics
from collections import defaultdict

import pandas as pd

from sleeper_dash.config import PROJECT_ROOT, load_config

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

TEAMS_COLUMNS = ["season", "roster_id", "owner_id", "co_owners", "display_name", "team_name"]
TEAM_WEEKS_COLUMNS = [
    "season", "week", "roster_id", "matchup_id", "points", "opponent_roster_id",
    "opponent_points", "margin", "result", "median_result", "is_playoff",
]


def read_raw(season, filename, raw_dir=RAW_DIR):
    path = raw_dir / str(season) / filename
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run `python -m sleeper_dash.extract` first.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_matchups(season, raw_dir=RAW_DIR):
    """Return {week: matchups} for every week extract saved, which is completed weeks only."""
    folder = raw_dir / str(season) / "matchups"
    if not folder.exists():
        raise FileNotFoundError(f"{folder} is missing. Run `python -m sleeper_dash.extract` first.")
    weeks = {}
    for path in sorted(folder.glob("week_*.json")):
        with open(path, encoding="utf-8") as f:
            weeks[int(path.stem.removeprefix("week_"))] = json.load(f)
    return weeks


def _clean_text(value):
    """Strip stray whitespace and treat blank strings as missing."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def build_teams(league, rosters, users):
    """One row per fantasy team per season. Key: (season, roster_id).

    Rosters are left-joined to users on owner_id, so a team with no owner keeps
    its row with empty names. team_name is the user's metadata.team_name when
    set, otherwise their display_name.
    """
    roster_df = pd.DataFrame(
        {
            "roster_id": [r["roster_id"] for r in rosters],
            "owner_id": [r.get("owner_id") for r in rosters],
            "co_owners": [r.get("co_owners") or [] for r in rosters],
        }
    )
    user_df = pd.DataFrame(
        {
            "owner_id": [u["user_id"] for u in users],
            "display_name": [_clean_text(u.get("display_name")) for u in users],
            "user_team_name": [_clean_text((u.get("metadata") or {}).get("team_name")) for u in users],
        },
        columns=["owner_id", "display_name", "user_team_name"],
    )

    teams = roster_df.merge(user_df, on="owner_id", how="left", validate="many_to_one")
    teams["team_name"] = teams["user_team_name"].fillna(teams["display_name"])
    teams["season"] = int(league["season"])

    teams = teams[TEAMS_COLUMNS].sort_values("roster_id").reset_index(drop=True)
    teams = teams.astype(
        {
            "season": "int64",
            "roster_id": "int64",
            "owner_id": "string",
            "display_name": "string",
            "team_name": "string",
        }
    )
    if teams.duplicated(["season", "roster_id"]).any():
        raise ValueError("teams has duplicate (season, roster_id) rows; check rosters.json.")
    return teams


def _result(points, other):
    if points > other:
        return "W"
    if points < other:
        return "L"
    return "T"


def build_team_weeks(league, matchups_by_week):
    """One row per team per completed week. Key: (season, week, roster_id).

    Opponents are the two teams sharing a matchup_id in a week; a team with no
    matchup_id (e.g. a playoff bye) gets null opponent, margin, and result.
    result is head-to-head only. When the league plays a weekly median game,
    median_result is a separate column: W above that week's median of all team
    scores, L below. Median games are assumed to be regular season only. A score
    exactly equal to the median raises, because no tie rule has been decided.
    """
    settings = league["settings"]
    season = int(league["season"])
    playoff_start = settings["playoff_week_start"]
    plays_median = settings.get("league_average_match") == 1

    rows = []
    for week, matchups in sorted(matchups_by_week.items()):
        is_playoff = week >= playoff_start
        points = {m["roster_id"]: round(m["points"], 2) for m in matchups}
        if len(points) != len(matchups):
            raise ValueError(f"Week {week}: a roster_id appears more than once in matchups.")

        teams_in_matchup = defaultdict(list)
        for m in matchups:
            if m.get("matchup_id") is not None:
                teams_in_matchup[m["matchup_id"]].append(m["roster_id"])
        for matchup_id, roster_ids in teams_in_matchup.items():
            if len(roster_ids) != 2:
                raise ValueError(
                    f"Week {week}: matchup_id {matchup_id} has {len(roster_ids)} team(s); expected 2."
                )
        opponent = {}
        for a, b in teams_in_matchup.values():
            opponent[a], opponent[b] = b, a

        median = None
        if plays_median and not is_playoff:
            median = statistics.median(points.values())
            tied = sorted(rid for rid, p in points.items() if p == median)
            if tied:
                raise ValueError(
                    f"Week {week}: roster(s) {tied} scored exactly the weekly median ({median}). "
                    "Median ties are not handled yet; decide a rule before continuing."
                )

        for m in matchups:
            roster_id = m["roster_id"]
            opp = opponent.get(roster_id)
            own_points = points[roster_id]
            opp_points = points[opp] if opp is not None else None
            row = {
                "season": season,
                "week": week,
                "roster_id": roster_id,
                "matchup_id": m.get("matchup_id"),
                "points": own_points,
                "opponent_roster_id": opp,
                "opponent_points": opp_points,
                "margin": round(own_points - opp_points, 2) if opp is not None else None,
                "result": _result(own_points, opp_points) if opp is not None else None,
                "is_playoff": is_playoff,
            }
            if plays_median:
                row["median_result"] = None if median is None else ("W" if own_points > median else "L")
            rows.append(row)

    columns = [c for c in TEAM_WEEKS_COLUMNS if plays_median or c != "median_result"]
    team_weeks = pd.DataFrame(rows, columns=columns)
    dtypes = {
        "season": "int64", "week": "int64", "roster_id": "int64", "matchup_id": "Int64",
        "points": "float64", "opponent_roster_id": "Int64", "opponent_points": "float64",
        "margin": "float64", "result": "string", "median_result": "string", "is_playoff": "bool",
    }
    team_weeks = team_weeks.astype({c: t for c, t in dtypes.items() if c in columns})
    return team_weeks.sort_values(["week", "roster_id"]).reset_index(drop=True)


def _standings(team_weeks, teams):
    """Season-to-date records and points from team_weeks, for display and reconciliation."""
    by_team = team_weeks.groupby("roster_id")
    count = lambda col, value: by_team[col].apply(lambda s: int((s == value).sum()))
    table = pd.DataFrame(
        {
            "W": count("result", "W"),
            "L": count("result", "L"),
            "T": count("result", "T"),
            "PF": by_team["points"].sum().round(2),
            "PA": by_team["opponent_points"].sum().round(2),
        }
    )
    if "median_result" in team_weeks:
        table["med_W"] = count("median_result", "W")
        table["med_L"] = count("median_result", "L")
    names = teams.set_index("roster_id")["team_name"]
    table.insert(0, "team_name", names.reindex(table.index))
    return table.reset_index()


def save_table(df, name, processed_dir=PROCESSED_DIR):
    """Write a table to data/processed/{name}.csv. List columns are stored as JSON text.

    Saved with a byte-order mark (utf-8-sig) so Excel shows non-English characters correctly.
    """
    out = df.copy()
    for column in out.columns:
        if out[column].map(lambda v: isinstance(v, list)).any():
            out[column] = out[column].map(json.dumps)
    processed_dir.mkdir(parents=True, exist_ok=True)
    path = processed_dir / f"{name}.csv"
    out.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def main():
    season = load_config().season
    league = read_raw(season, "league.json")
    rosters = read_raw(season, "rosters.json")
    users = read_raw(season, "users.json")

    teams = build_teams(league, rosters, users)
    team_weeks = build_team_weeks(league, read_matchups(season))
    for name, table in [("teams", teams), ("team_weeks", team_weeks)]:
        path = save_table(table, name)
        print(f"Saved {len(table)} rows to {path.relative_to(PROJECT_ROOT).as_posix()}")

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    weeks = sorted(int(w) for w in team_weeks["week"].unique())
    print(f"\nteam_weeks covers weeks {weeks}; playoff rows: {int(team_weeks['is_playoff'].sum())}")
    print("\nWEEK 1")
    print(team_weeks[team_weeks["week"] == 1].to_string(index=False))

    table = _standings(team_weeks, teams)
    sleeper = pd.DataFrame(
        {
            "roster_id": [r["roster_id"] for r in rosters],
            "sl_W": [r["settings"]["wins"] for r in rosters],
            "sl_L": [r["settings"]["losses"] for r in rosters],
            "sl_T": [r["settings"]["ties"] for r in rosters],
            "sl_PF": [r["settings"]["fpts"] + r["settings"]["fpts_decimal"] / 100 for r in rosters],
            "sl_PA": [r["settings"]["fpts_against"] + r["settings"]["fpts_against_decimal"] / 100 for r in rosters],
        }
    )
    table = table.merge(sleeper, on="roster_id")
    has_median = "med_W" in table
    table["record"] = table.W.astype(str) + "–" + table.L.astype(str) + "–" + table["T"].astype(str)
    total_W = table.W + (table.med_W if has_median else 0)
    total_L = table.L + (table.med_L if has_median else 0)
    table["matches_sleeper"] = (
        (total_W == table.sl_W) & (total_L == table.sl_L) & (table["T"] == table.sl_T)
        & ((table.PF - table.sl_PF).abs() < 0.005) & ((table.PA - table.sl_PA).abs() < 0.005)
    )
    columns = ["team_name", "record", "PF", "PA"]
    if has_median:
        table["median"] = table.med_W.astype(str) + "–" + table.med_L.astype(str)
        table["overall"] = total_W.astype(str) + "–" + total_L.astype(str)
        columns += ["median", "overall"]
    table = table.assign(total_W=total_W).sort_values(["total_W", "PF"], ascending=False)
    print("\nSTANDINGS (head-to-head record; sorted by overall wins, then points for)")
    print(table[columns + ["matches_sleeper"]].to_string(index=False))
    print(f"\nAll teams match Sleeper's own season totals: {bool(table['matches_sleeper'].all())}")


if __name__ == "__main__":
    main()
