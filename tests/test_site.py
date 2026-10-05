"""The files a weekly run publishes, read back from site/: the link-preview tags and image name the latest week.

The weekly workflow runs this right after building the page (step "Page tests (this run's tables)", with
CHECK_BUILT_SITE=1), so a run whose preview is missing or stale publishes nothing. Elsewhere it's skipped, because
site/ is a build output (locally it can be older than the tables): to run it yourself, build the page first with
`python -m sleeper_dash.dashboard`, then set CHECK_BUILT_SITE=1.
"""

import os
import re

import pytest

from sleeper_dash.config import load_config
from sleeper_dash.dashboard import preview
from sleeper_dash.dashboard.build import SITE_DIR
from sleeper_dash.transform import PROCESSED_DIR
from sleeper_dash.validate import load_tables

pytestmark = pytest.mark.skipif(os.environ.get("CHECK_BUILT_SITE") != "1",
                                reason="checks a freshly built site/; the weekly workflow sets CHECK_BUILT_SITE=1")


def latest_week():
    config = load_config()
    power = load_tables(PROCESSED_DIR, names=["power_rankings"])["power_rankings"]
    return config.season, int(power.loc[power["season"] == config.season, "week"].max())


def test_the_published_tags_and_image_are_this_weeks():
    season, week = latest_week()
    html = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    found = dict(re.findall(r'<meta (?:property|name)="((?:og|twitter):[\w:]+)" content="([^"]*)">', html))
    page_url = load_config().dashboard["page_url"]
    assert found["og:title"] == found["twitter:title"] == f"Week {week} power rankings"
    assert f"after week {week}." in found["og:description"]
    assert found["og:image"] == found["twitter:image"] == f"{page_url}{preview.FILENAME}?v={season}-{week}"
    image = SITE_DIR / preview.FILENAME
    assert image.exists(), "the page points to a preview image the build didn't write"
    assert preview.read_week(image) == (season, week)
    assert image.stat().st_size < 100_000
