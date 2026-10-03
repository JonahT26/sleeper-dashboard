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

    return Config(league_id=league_id, season=season, season_start_dates=start_dates, metrics=metrics)


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
