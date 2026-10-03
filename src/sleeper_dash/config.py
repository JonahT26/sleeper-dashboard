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
    season_start_date: str  # 'YYYY-MM-DD'; splits out preseason transactions (checked against Sleeper in-season)
    metrics: dict = field(default_factory=dict)  # metric parameters; defined in docs/METRICS_SPEC.md


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Read config.yaml and return a Config, raising ValueError on bad values."""
    with open(path, encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f) or {}
        except ValueError as error:  # e.g. an impossible unquoted date such as 2026-13-01
            raise ValueError(f"{path} has a value that can't be read ({error}). Write dates as YYYY-MM-DD.") from None

    missing = [key for key in ("league_id", "season", "season_start_date") if key not in raw]
    if missing:
        raise ValueError(f"{path} is missing required setting(s): {', '.join(missing)}")

    league_id = raw["league_id"]
    if not isinstance(league_id, str):
        raise ValueError(
            f"league_id in {path} must be a quoted string, e.g. league_id: \"123\". "
            "Without quotes YAML reads it as a number."
        )

    season = raw["season"]
    if not isinstance(season, int) or isinstance(season, bool):
        raise ValueError(f"season in {path} must be a whole number, e.g. season: 2026")

    season_start_date = _season_start_date(raw["season_start_date"], season, path)

    metrics = raw.get("metrics") or {}
    if not isinstance(metrics, dict):
        raise ValueError(f"metrics in {path} must be a section of named settings")

    return Config(league_id=league_id, season=season, season_start_date=season_start_date, metrics=metrics)


def _season_start_date(value, season, path):
    """The NFL season's start date as 'YYYY-MM-DD'. YAML reads an unquoted date as a date, a quoted one as text."""
    if isinstance(value, datetime.datetime) or not isinstance(value, (datetime.date, str)):
        raise ValueError(f"season_start_date in {path} must be a date, e.g. season_start_date: {season}-09-09")
    try:
        start = value if isinstance(value, datetime.date) else datetime.date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"season_start_date in {path} must be a date written YYYY-MM-DD, not {value!r}") from None
    if start.year != season:
        raise ValueError(
            f"season_start_date in {path} is {start.isoformat()}, which isn't in season {season}. "
            "Update both together when the season changes."
        )
    return start.isoformat()
