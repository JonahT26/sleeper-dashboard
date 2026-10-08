"""Load and validate project settings from config.yaml."""

import datetime
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@dataclass(frozen=True)
class Config:
    league_id: str
    season: int
    # {season: 'YYYY-MM-DD'}: the first day of each NFL season, which splits out preseason
    # transactions. Stored here because Sleeper's /state/nfl only describes the current season.
    season_start_dates: dict
    metrics: dict = field(default_factory=dict)  # metric parameters; defined in docs/METRICS_SPEC.md
    dashboard: dict = field(default_factory=dict)  # page settings, e.g. stale_after_days (docs/UI_GUIDE.md)
    # First season to include. Earlier seasons are reached through each league's previous_league_id;
    # None means the configured season only.
    history_from: int | None = None
    # {season: [{roster_id, points_for, points_against}]}: known gaps between the sum of Sleeper's weekly
    # scores and its stored season totals (weekly sum minus stored), from stat corrections Sleeper never
    # carried into the totals. The points check allows exactly these and nothing else.
    sleeper_points_gaps: dict = field(default_factory=dict)
    # {season: {"winner_roster_id": int, "loser_roster_id": int}}: league rulings on a season's final that
    # differ from Sleeper's bracket (seasons.with_champion_override); the run stops if Sleeper no longer shows
    # the result being overridden.
    champion_overrides: dict = field(default_factory=dict)
    # The weekly league-chat post (chat.py): mode (off, dry-run, on), award preferences, the page's address.
    # The GroupMe bot ID is a GitHub Actions secret, never in config (CLAUDE.md rule 7).
    chat: dict = field(default_factory=lambda: {"mode": "off"})

    def start_date(self, season):
        """The season's start date, 'YYYY-MM-DD'. Raises ValueError if config.yaml doesn't have it."""
        if season not in self.season_start_dates:
            raise ValueError(
                f"config.yaml season_start_dates has no date for season {season}. Add a line such as "
                f"{season}: {season}-09-09 (Sleeper's /state/nfl season_start_date for that season)."
            )
        return self.season_start_dates[season]

    @property
    def season_start_date(self):
        """This season's start date."""
        return self.start_date(self.season)

    @property
    def seasons(self):
        """Every season the pipeline builds, oldest first: history_from up to the configured season."""
        return list(range(self.history_from or self.season, self.season + 1))


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Read config.yaml and return a Config, raising ValueError on bad values."""
    with open(path, encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f) or {}
        except ValueError as error:  # e.g. an impossible unquoted date such as 2026-13-01
            raise ValueError(f"{path} has a value that can't be read ({error}). Write dates as YYYY-MM-DD.") from None

    missing = [key for key in ("league_id", "season", "season_start_dates") if key not in raw]
    if missing:
        raise ValueError(f"{path} is missing required setting(s): {', '.join(missing)}")

    league_id = raw["league_id"]
    if not isinstance(league_id, str):
        raise ValueError(
            f"league_id in {path} must be a quoted string, e.g. league_id: \"123\". "
            "Without quotes YAML reads it as a number."
        )

    season = raw["season"]
    if not _is_whole_number(season):
        raise ValueError(f"season in {path} must be a whole number, e.g. season: 2026")

    start_dates = _season_start_dates(raw["season_start_dates"], path)
    if season not in start_dates:
        raise ValueError(f"season_start_dates in {path} has no date for season {season}; add one with the new season.")

    metrics = raw.get("metrics") or {}
    if not isinstance(metrics, dict):
        raise ValueError(f"metrics in {path} must be a section of named settings")

    dashboard = raw.get("dashboard") or {}
    stale = dashboard.get("stale_after_days", 8) if isinstance(dashboard, dict) else None
    if not isinstance(stale, (int, float)) or isinstance(stale, bool) or stale <= 0:
        raise ValueError(f"dashboard.stale_after_days in {path} must be a number of days above 0, e.g. stale_after_days: 8")

    history_from = raw.get("history_from")
    if history_from is not None:
        if not _is_whole_number(history_from) or history_from > season:
            raise ValueError(f"history_from in {path} must be a season year no later than season ({season}), e.g. history_from: 2020")
        missing = [s for s in range(history_from, season) if s not in start_dates]
        if missing:
            raise ValueError(f"season_start_dates in {path} has no date for season(s) {missing}, which history_from "
                             f"{history_from} includes. Add one line per season.")

    chat = raw.get("chat") or {"mode": "off"}
    if not isinstance(chat, dict):
        raise ValueError(f'chat in {path} must be a section of named settings, e.g. chat: {{mode: "dry-run"}}')
    if chat.get("mode") not in ("off", "dry-run", "on"):  # YAML reads a bare off/on as false/true: quote them
        raise ValueError(f'chat.mode in {path} must be "off", "dry-run", or "on", in quotes (got {chat.get("mode")!r})')

    page_url = dashboard.get("page_url") if isinstance(dashboard, dict) else None
    if page_url is not None and not (isinstance(page_url, str) and page_url.startswith("https://") and page_url.endswith("/")):
        raise ValueError(f"dashboard.page_url in {path} must be the page's https:// address ending in /, "
                         "e.g. https://jonaht26.github.io/sleeper-dashboard/")

    return Config(league_id=league_id, season=season, season_start_dates=start_dates, metrics=metrics,
                  dashboard={**dashboard, "stale_after_days": stale}, history_from=history_from,
                  sleeper_points_gaps=_points_gaps(raw.get("sleeper_points_gaps") or {}, path),
                  champion_overrides=_champion_overrides(raw.get("champion_overrides") or {}, path), chat=chat)


def _champion_overrides(value, path):
    """{season: {"winner_roster_id": int, "loser_roster_id": int}}: the final's winner by league ruling."""
    example = "champion_overrides:\n  2022: {winner_roster_id: 9, loser_roster_id: 4}"
    if not isinstance(value, dict):
        raise ValueError(f"champion_overrides in {path} must list one final per season, e.g.\n{example}")
    overrides = {}
    for season, entry in value.items():
        keys = {"winner_roster_id", "loser_roster_id"}
        if (not _is_whole_number(season) or not isinstance(entry, dict) or set(entry) != keys
                or not all(_is_whole_number(entry[k]) for k in keys) or entry["winner_roster_id"] == entry["loser_roster_id"]):
            raise ValueError(f"champion_overrides in {path}: {season!r} needs a season year with two different roster IDs, "
                             f"winner_roster_id and loser_roster_id, e.g.\n{example}")
        overrides[season] = {k: entry[k] for k in ("winner_roster_id", "loser_roster_id")}
    return overrides


def _points_gaps(value, path):
    """{season: [{"roster_id": int, "points_for": float, "points_against": float}]}, missing amounts as 0."""
    example = "sleeper_points_gaps:\n  2023:\n    - {roster_id: 5, points_for: 1.00}"
    if not isinstance(value, dict):
        raise ValueError(f"sleeper_points_gaps in {path} must list gaps by season, e.g.\n{example}")
    gaps = {}
    for season, entries in value.items():
        if not _is_whole_number(season) or not isinstance(entries, list):
            raise ValueError(f"sleeper_points_gaps in {path}: {season!r} must be a season year with a list of gaps, e.g.\n{example}")
        gaps[season] = []
        for entry in entries:
            extra = set(entry) - {"roster_id", "points_for", "points_against"} if isinstance(entry, dict) else {"?"}
            if extra or not _is_whole_number(entry.get("roster_id")):
                raise ValueError(f"sleeper_points_gaps in {path}, season {season}: each gap needs roster_id and "
                                 f"points_for and/or points_against, e.g.\n{example}")
            gaps[season].append({"roster_id": entry["roster_id"], "points_for": float(entry.get("points_for", 0)),
                                 "points_against": float(entry.get("points_against", 0))})
    return gaps


def _is_whole_number(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _season_start_dates(value, path):
    """{season: 'YYYY-MM-DD'}. YAML reads an unquoted date as a date and a quoted one as text; both are accepted."""
    example = "season_start_dates:\n  2026: 2026-09-09"
    if not isinstance(value, dict) or not value:
        raise ValueError(f"season_start_dates in {path} must list one date per season, e.g.\n{example}")
    dates = {}
    for season, date in value.items():
        if not _is_whole_number(season):
            raise ValueError(f"season_start_dates in {path}: {season!r} isn't a season year, e.g.\n{example}")
        if isinstance(date, datetime.datetime) or not isinstance(date, (datetime.date, str)):
            raise ValueError(f"season_start_dates in {path}: season {season} needs a date written YYYY-MM-DD, not {date!r}")
        try:
            start = date if isinstance(date, datetime.date) else datetime.date.fromisoformat(date)
        except ValueError:
            raise ValueError(f"season_start_dates in {path}: season {season} needs a date written YYYY-MM-DD, not {date!r}") from None
        if start.year != season:
            raise ValueError(f"season_start_dates in {path}: season {season} starts {start.isoformat()}, which isn't in {season}.")
        dates[season] = start.isoformat()
    return dates
