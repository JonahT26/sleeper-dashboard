"""Several seasons at once (Phase 5, past seasons): split tables by season, stack them, and match managers.

Each season is built and checked on its own, with its own league settings (lineup slots, playoff
start, playoff format), because those can differ between seasons. The saved tables then hold every
season, one after another, told apart by their `season` column. Managers are matched across seasons
by Sleeper owner ID, never by team name, which changes from season to season.
"""

import pandas as pd

MANAGERS_COLUMNS = ["owner_id", "display_name", "first_season", "last_season", "seasons"]


def season_slice(tables, season):
    """{name: rows for one season} for every table with a season column (tables without one are left out)."""
    return {name: table[table["season"] == season].reset_index(drop=True)
            for name, table in tables.items() if "season" in table.columns}


def stack(by_season):
    """One table per name, every season's rows in season order. by_season: {season: {name: table}}."""
    names = list(dict.fromkeys(name for season in sorted(by_season) for name in by_season[season]))
    stacked = {}
    for name in names:
        parts = [by_season[season][name] for season in sorted(by_season) if name in by_season[season]]
        # Seasons with no rows (e.g. no playoff odds yet) are skipped, so they can't change a column's type.
        non_empty = [p for p in parts if not p.empty]
        stacked[name] = pd.concat(non_empty or parts[:1], ignore_index=True)
    return stacked


def build_managers(teams):
    """One row per manager (Sleeper owner ID) across every season in `teams`. Key: owner_id.

    display_name is the manager's name in the latest season they played; first_season, last_season,
    and seasons (how many) come from the seasons they owned a team.
    """
    owned = teams.dropna(subset=["owner_id"]).sort_values(["season", "roster_id"])
    latest = owned.groupby("owner_id").tail(1).set_index("owner_id")
    by_owner = owned.groupby("owner_id")["season"]
    managers = pd.DataFrame({
        "display_name": latest["display_name"],
        "first_season": by_owner.min(), "last_season": by_owner.max(), "seasons": by_owner.nunique(),
    }).rename_axis("owner_id").reset_index()
    return managers[MANAGERS_COLUMNS].astype({"owner_id": str, "first_season": "int64", "last_season": "int64",
                                              "seasons": "int64"}).sort_values(["first_season", "owner_id"]).reset_index(drop=True)


def with_known_gaps(rosters, gaps):
    """A copy of rosters.json with the known gaps in Sleeper's stored season totals added back.

    gaps: config.yaml sleeper_points_gaps for this season (weekly-score sum minus Sleeper's stored total).
    After this, "Points for/against match Sleeper" compares the weekly sums with what Sleeper's totals
    would be if it had carried its own stat corrections through. A listed gap that isn't really there
    makes the check fail too, so the list stays true. Each adjusted team is marked so the check can say so.
    """
    import copy

    adjusted = copy.deepcopy(rosters)
    by_roster = {r["roster_id"]: r for r in adjusted}
    for gap in gaps:
        settings = by_roster[gap["roster_id"]]["settings"]
        for key, amount in (("fpts", gap["points_for"]), ("fpts_against", gap["points_against"])):
            cents = settings.get(key, 0) * 100 + settings.get(f"{key}_decimal", 0) + round(amount * 100)
            settings[key], settings[f"{key}_decimal"] = int(cents // 100), int(cents % 100)
        settings["known_points_gap"] = True
    return adjusted


def league_files(seasons, gaps=None):
    """{season: (league.json, rosters.json)} from data/raw/, for checks that compare with Sleeper.

    gaps: config.yaml sleeper_points_gaps; each season's known gaps are applied to its rosters (with_known_gaps).
    """
    from sleeper_dash.transform import read_raw

    gaps = gaps or {}
    return {season: (read_raw(season, "league.json"), with_known_gaps(read_raw(season, "rosters.json"), gaps.get(season, [])))
            for season in seasons}
