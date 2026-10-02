"""Build tidy tables in data/processed/ from the raw JSON in data/raw/{season}/.

Run with:  python -m sleeper_dash.transform

Reads raw files only; never calls the Sleeper API.
"""

import json

import pandas as pd

from sleeper_dash.config import PROJECT_ROOT, load_config

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

TEAMS_COLUMNS = ["season", "roster_id", "owner_id", "co_owners", "display_name", "team_name"]


def read_raw(season, filename, raw_dir=RAW_DIR):
    path = raw_dir / str(season) / filename
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run `python -m sleeper_dash.extract` first.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
    path = save_table(teams, "teams")

    with pd.option_context("display.width", 200, "display.max_columns", None):
        print(teams.to_string(index=False))
    print()
    print(f"Saved {len(teams)} rows to {path.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"  Unique roster_id:            {teams['roster_id'].nunique()}")
    print(f"  Missing owner_id:            {teams['owner_id'].isna().sum()}")
    print(f"  Teams with co-owners:        {(teams['co_owners'].map(len) > 0).sum()}")
    fallback = (teams["team_name"] == teams["display_name"]).sum()
    print(f"  team_name = display_name:    {fallback} (no custom team name)")


if __name__ == "__main__":
    main()
