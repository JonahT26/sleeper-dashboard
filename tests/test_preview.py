"""Link previews (owner, 2026-10-05): the Open Graph and Twitter card tags in the page's head, and the preview image
(dashboard/preview.py) that build_site draws next to index.html on every run. Synthetic tables; no network.

tests/test_site.py checks the same things on the files a weekly run actually publishes.
"""

import json
import re

import pytest
from PIL import Image, ImageDraw

from sleeper_dash.config import load_config
from sleeper_dash.dashboard import preview
from sleeper_dash.dashboard.build import build_site, build_view, render
from test_config import VALID, write
from test_dashboard import METRICS, RUN, make_tables
from test_quality_floor import colour

PAGE = "https://example.test/page/"


def tags(html):
    """{property or name: content} for the page's og: and twitter: meta tags."""
    return dict(re.findall(r'<meta (?:property|name)="((?:og|twitter):[\w:]+)" content="([^"]*)">', html))


def test_the_tags_name_the_latest_week_and_point_to_this_weeks_image():
    found = tags(render(build_view(make_tables(weeks=5), {**RUN, "weeks": list(range(1, 6))}, METRICS, page_url=PAGE)))
    assert found["og:title"] == found["twitter:title"] == "Week 5 power rankings"
    assert found["og:description"] == found["twitter:description"] == (
        "Team 1 is #1 after week 5. Power rankings, luck, and weekly awards for Test League.")
    assert found["og:image"] == found["twitter:image"] == f"{PAGE}preview.png?v=2026-5"  # a new URL every week
    assert found["og:url"] == PAGE and found["twitter:card"] == "summary_large_image"
    assert (found["og:image:width"], found["og:image:height"]) == ("1200", "630")
    assert found["og:image:alt"] == "Week 5 power rankings: the top five teams and their power scores."


def test_without_the_page_address_there_are_no_preview_tags():
    assert tags(render(build_view(make_tables(), RUN, METRICS))) == {}


def test_build_site_draws_a_small_image_of_the_latest_weeks_top_five(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    for name, table in make_tables(weeks=4).items():
        table.to_csv(processed / f"{name}.csv", index=False, encoding="utf-8-sig")
    run_path = tmp_path / "pipeline_run.json"
    run_path.write_text(json.dumps({**RUN, "weeks": [1, 2, 3, 4]}), encoding="utf-8")
    page, view = build_site(out_dir=tmp_path / "site", processed_dir=processed, run_path=run_path)
    image = tmp_path / "site" / preview.FILENAME
    assert preview.read_week(image) == (2026, 4) == (view["preview"]["season"], view["preview"]["week"])
    with Image.open(image) as png:
        assert png.size == (1200, 630) and png.format == "PNG" and png.text["Title"] == "Week 4 power rankings"
        used = {rgb for _, rgb in png.convert("RGB").getcolors(maxcolors=4096)}
    assert image.stat().st_size < 60_000                                        # small: about 25 KB
    assert {preview._rgb(preview.COLOURS[c]) for c in ("masthead", "chalk", "pylon")} <= used   # the #1 numeral is pylon
    found = tags(page.read_text(encoding="utf-8"))
    assert found["og:title"] == "Week 4 power rankings"
    assert found["og:image"] == f"{load_config().dashboard['page_url']}preview.png?v=2026-4"


def test_long_team_names_are_cut_to_fit():
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = preview._font("Barlow-SemiBold.ttf", 34)
    cut = preview._fit(draw, "An extremely long fantasy team name that goes on and on", font, 300)
    assert cut.endswith("…") and draw.textlength(cut, font=font) <= 300
    assert preview._fit(draw, "Short", font, 300) == "Short"


def test_the_image_uses_the_pages_colour_tokens():
    """UI_GUIDE.md "Color": the masthead band and its text, and the dark-mode pylon and bar made for dark backgrounds."""
    assert preview.COLOURS == {"masthead": colour("var(--masthead)", "light"), "chalk": colour("var(--chalk)", "light"),
                               "on-mast-muted": colour("var(--on-mast-muted)", "light"),
                               "pylon": colour("var(--pylon)", "dark"), "bar": colour("var(--bar)", "dark")}


@pytest.mark.parametrize("value", ["http://jonaht26.github.io/sleeper-dashboard/", "https://jonaht26.github.io/sleeper-dashboard"])
def test_the_page_address_must_be_https_and_end_in_a_slash(tmp_path, value):
    with pytest.raises(ValueError, match="dashboard.page_url"):
        load_config(write(tmp_path, VALID + f"dashboard:\n  page_url: {value}\n"))
