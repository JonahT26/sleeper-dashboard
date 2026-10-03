"""Pull the season's raw Sleeper data into data/raw/{season}/ as untouched JSON.

Run with:  python -m sleeper_dash.extract

Full refresh: every run re-downloads everything into a staging folder and only
replaces data/raw/{season}/ once all calls have succeeded, so a failed run never
leaves a half-updated season behind.
"""

import json
import shutil
import time

from sleeper_dash import api
from sleeper_dash.config import PROJECT_ROOT, load_config

RAW_DIR = PROJECT_ROOT / "data" / "raw"
SWAP_ATTEMPTS = 5
SWAP_WAIT_SECONDS = 0.2  # waits 0.2, 0.4, 0.6, 0.8 s between tries: 2 s at most


class ExtractError(Exception):
    """The extract could not produce a complete, trustworthy raw snapshot."""


def latest_completed_week(state, league):
    """Return the last fantasy week that is fully finished, or 0 if none is.

    Two independent signals must agree, and the smaller one wins:
      1. Sleeper's league scoring: settings.last_scored_leg is the last week
         Sleeper has finished scoring for this league. It does not move while
         a week's games are still being played.
      2. The NFL calendar: while this league's NFL regular season is under way,
         /state/nfl week is the week in progress, so only weeks before it can be done.
    """
    last_scored = league.get("settings", {}).get("last_scored_leg")
    if last_scored is None:
        raise ExtractError(
            "League settings have no last_scored_leg, so the latest completed week "
            "cannot be determined safely."
        )

    completed = last_scored
    if state["season"] == league["season"] and state["season_type"] == "regular":
        completed = min(completed, state["week"] - 1)
    return max(completed, 0)


def future_schedule_weeks(league, last_completed_week):
    """Regular-season weeks after the latest completed week, whose pairings Sleeper already publishes.

    Their matchups (0 points so far) give the remaining schedule for strength of schedule.
    """
    return list(range(last_completed_week + 1, league["settings"]["playoff_week_start"]))


def _swap_in(staging_dir, season_dir):
    """Replace data/raw/{season}/ with the finished staging folder.

    On Windows a folder that was just deleted can stay locked for a moment (antivirus or
    search indexing still has it open), so the rename is refused. Retry briefly before giving up.
    """
    for attempt in range(1, SWAP_ATTEMPTS + 1):
        try:
            if season_dir.exists():
                shutil.rmtree(season_dir)
            staging_dir.rename(season_dir)
            return
        except PermissionError as error:
            if attempt == SWAP_ATTEMPTS:
                raise ExtractError(
                    f"Couldn't replace {season_dir} with the new download after {SWAP_ATTEMPTS} tries ({error}). "
                    "Close anything using that folder and run again."
                ) from error
            time.sleep(SWAP_WAIT_SECONDS * attempt)


def _record_count(data):
    return len(data) if isinstance(data, list) else 1


def extract(config):
    """Download the season into data/raw/{season}/. Returns a run summary dict."""
    season_dir = RAW_DIR / str(config.season)
    staging_dir = RAW_DIR / f"{config.season}.partial"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    files = []
    calls = 0

    def fetch(path, filename):
        nonlocal calls
        data = api.get(path)
        calls += 1
        if data is None:
            raise ExtractError(f"Sleeper returned an empty response (null) for {path}.")
        target = staging_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        files.append({"file": filename, "records": _record_count(data)})
        return data

    league_path = f"/league/{config.league_id}"
    state = fetch("/state/nfl", "state.json")
    league = fetch(league_path, "league.json")
    if str(league["season"]) != str(config.season):
        raise ExtractError(
            f"League {config.league_id} is for season {league['season']}, "
            f"but config.yaml says season {config.season}."
        )

    fetch(f"{league_path}/users", "users.json")
    fetch(f"{league_path}/rosters", "rosters.json")
    drafts = fetch(f"{league_path}/drafts", "drafts.json")
    for draft in drafts:
        draft_id = draft["draft_id"]
        fetch(f"/draft/{draft_id}/picks", f"picks/draft_{draft_id}.json")

    # The players list is cached separately (data/cache/) and re-downloaded at most once a day.
    cache_path = api.PLAYERS_CACHE_PATH
    mtime_before = cache_path.stat().st_mtime if cache_path.exists() else None
    players = api.get_players()
    players_refreshed = cache_path.stat().st_mtime != mtime_before
    calls += players_refreshed

    last_week = latest_completed_week(state, league)
    for week in range(1, last_week + 1):
        fetch(f"{league_path}/matchups/{week}", f"matchups/week_{week:02d}.json")
        fetch(f"{league_path}/transactions/{week}", f"transactions/week_{week:02d}.json")
    for week in future_schedule_weeks(league, last_week):
        fetch(f"{league_path}/matchups/{week}", f"schedule/week_{week:02d}.json")

    _swap_in(staging_dir, season_dir)

    return {
        "season_dir": season_dir,
        "files": files,
        "calls": calls,
        "latest_completed_week": last_week,
        "nfl_week": state["week"],
        "nfl_season_type": state["season_type"],
        "last_scored_leg": league["settings"]["last_scored_leg"],
        "players_cached": len(players),
        "players_refreshed": players_refreshed,
    }


def main():
    summary = extract(load_config())

    print("LATEST COMPLETED WEEK")
    print(f"  NFL state:               week {summary['nfl_week']} ({summary['nfl_season_type']})")
    print(f"  League last_scored_leg:  {summary['last_scored_leg']}")
    print(f"  Latest completed week:   {summary['latest_completed_week']}")
    print()
    print(f"FILES WRITTEN to {summary['season_dir'].relative_to(PROJECT_ROOT).as_posix()}/")
    width = max(len(f["file"]) for f in summary["files"])
    print(f"  {'File':<{width}}  Records")
    for f in summary["files"]:
        print(f"  {f['file']:<{width}}  {f['records']:>7}")
    print()
    status = "downloaded fresh" if summary["players_refreshed"] else "reused (less than 24 hours old)"
    print(f"  Players cache: {summary['players_cached']} players, {status}")
    print(f"  {len(summary['files'])} files, {summary['calls']} API calls")


if __name__ == "__main__":
    main()
