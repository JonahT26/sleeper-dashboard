"""Load and validate project settings from config.yaml."""

from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@dataclass(frozen=True)
class Config:
    league_id: str
    season: int


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Read config.yaml and return a Config, raising ValueError on bad values."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    missing = [key for key in ("league_id", "season") if key not in raw]
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

    return Config(league_id=league_id, season=season)
