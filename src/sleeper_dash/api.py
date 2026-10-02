"""Sleeper HTTP client: timeouts, retries with backoff, pacing, and a daily players cache."""

import json
import logging
import time

import requests

from sleeper_dash.config import PROJECT_ROOT

BASE_URL = "https://api.sleeper.app/v1"
TIMEOUT_SECONDS = 10
MAX_RETRIES = 3
BACKOFF_SECONDS = 1  # first retry waits 1s, then 2s, then 4s
MIN_SECONDS_BETWEEN_CALLS = 0.25  # caps us at 240 calls/minute, far below Sleeper's 1,000

PLAYERS_CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "players_nfl.json"
PLAYERS_MAX_AGE_HOURS = 24

log = logging.getLogger(__name__)

_last_call = float("-inf")  # time.monotonic() of the most recent request


class SleeperAPIError(Exception):
    """A Sleeper request failed and retrying will not (or did not) help."""


class SleeperNotFoundError(SleeperAPIError):
    """Sleeper returned 404 for a path."""


def _wait_for_turn():
    """Sleep just long enough to keep calls at least MIN_SECONDS_BETWEEN_CALLS apart."""
    global _last_call
    elapsed = time.monotonic() - _last_call
    if elapsed < MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
    _last_call = time.monotonic()


def get(path):
    """GET BASE_URL + path and return the parsed JSON.

    Retries network errors, 429s, and 5xx responses up to MAX_RETRIES times with
    doubling waits. Note that Sleeper answers some bad IDs with 200 and a JSON
    `null` body rather than a 404, so callers should check for None.
    """
    url = f"{BASE_URL}{path}"
    for attempt in range(MAX_RETRIES + 1):
        _wait_for_turn()
        try:
            response = requests.get(url, timeout=TIMEOUT_SECONDS)
        except (requests.ConnectionError, requests.Timeout) as exc:
            problem = f"network error ({type(exc).__name__})"
        else:
            status = response.status_code
            if status == 404:
                raise SleeperNotFoundError(
                    f"Sleeper returned 404 Not Found for {path}. "
                    "Check the league ID in config.yaml and any week number in the path."
                )
            if status == 429 or status >= 500:
                problem = f"HTTP {status}"
            elif status >= 400:
                raise SleeperAPIError(f"Sleeper returned HTTP {status} for {path}; not retrying.")
            else:
                return response.json()

        if attempt == MAX_RETRIES:
            raise SleeperAPIError(
                f"Gave up on {path} after {MAX_RETRIES + 1} attempts. Last problem: {problem}."
            )
        wait = BACKOFF_SECONDS * 2**attempt
        log.warning("%s on %s; retry %d of %d in %ss", problem, path, attempt + 1, MAX_RETRIES, wait)
        time.sleep(wait)


def get_players(cache_path=PLAYERS_CACHE_PATH, max_age_hours=PLAYERS_MAX_AGE_HOURS):
    """Return every NFL player from /players/nfl as a dict keyed by player_id.

    The response is large and Sleeper asks that it be fetched at most once a day,
    so it is cached to disk and only re-downloaded once the cache is older than
    max_age_hours.
    """
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)

    players = get("/players/nfl")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temporary file first so an interrupted save never leaves a half-written cache.
    temp_path = cache_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(players, f)
    temp_path.replace(cache_path)
    return players
