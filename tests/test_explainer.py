"""Tests for the "How this works" copy: every number comes from config.yaml and league settings, never from the text."""

from sleeper_dash.config import load_config
from sleeper_dash.dashboard.build import build_view, render
from sleeper_dash.dashboard.explainer import as_text, sections
from test_dashboard import METRICS, RUN, make_tables

LEAGUE = {"teams": 12, "median_game": True, "playoff_week_start": 15}
OTHER_PARAMS = {
    "power": {"weights": {"season_scoring": 0.40, "recent_form": 0.30, "roster_strength": 0.15, "results": 0.15},
              "recent_weeks": 4, "scale": 10, "shrink_weeks": 2},
    "consistency": {"min_weeks": 4, "floor_pct": 0.20, "ceiling_pct": 0.75, "boom_margin": 25, "bust_margin": 15},
    "schedule": {"min_weeks": 5},
}


def test_the_draft_uses_todays_config():
    text = as_text(sections(load_config().metrics, LEAGUE))
    for phrase in ["Season scoring (35%)", "Recent form (25%)", "Roster strength (20%)", "Head-to-head wins (20%)",
                   "last 3 weeks", "worth 15 points", "below 2.4 or above 97.6", "spread is 25%", "75% by week 9",
                   "10th percentile", "the 90th", "20 or more points above", "20 or more below",
                   "played 3 weeks", "once 3 weeks", "top 6 of 12", "goes 11–0", "weeks 1–14", "60% between them"]:
        assert phrase in text, phrase


def test_every_number_follows_the_config_and_league_settings():
    text = as_text(sections(OTHER_PARAMS, {"teams": 10, "median_game": False, "playoff_week_start": 14}))
    for phrase in ["Season scoring (40%)", "Recent form (30%)", "Roster strength (15%)", "Head-to-head wins (15%)",
                   "last 4 weeks", "worth 10 points", "below 21.5 or above 78.5", "spread is 33%", "75% by week 6",
                   "20th percentile", "the 75th", "about 20% of weeks falls below", "about 25% of weeks goes above",
                   "25 or more points above", "15 or more below", "played 4 weeks", "once 5 weeks",
                   "goes 9–0", "weeks 1–13", "other 9 teams"]:
        assert phrase in text, phrase
    # This league has no median game, so the copy doesn't mention one.
    assert "median game" not in text and "Records" not in [s["heading"] for s in sections(OTHER_PARAMS, {**LEAGUE, "median_game": False})]
    assert "35%" not in text and "{" not in text and "}" not in text


def test_the_approved_copy_is_the_last_section_of_the_page_with_numbers_from_config():
    """Owner approved the copy on 2026-10-02. It renders once, after every week's sections, with config values filled in."""
    html = render(build_view(make_tables(), RUN, METRICS))
    shown = html.split("<template")[0] + html.split("</template>")[-1]
    assert shown.count('id="how-title"') == 1 and "<template" not in html.split('id="how-title"')[1].split("</section>")[0]
    assert shown.index('id="how-title"') > shown.rindex('class="chart-section')  # after the shown week's charts
    for phrase in ["Season scoring (35%)", "worth 15 points", "75% by week 9", "goes 11–0", "Why past weeks can change"]:
        assert phrase in html


def test_the_page_copy_changes_when_the_config_changes():
    params = {**OTHER_PARAMS, "awards": {"enabled": ["top_score"]}}
    html = render(build_view(make_tables(), RUN, params))
    assert "Season scoring (40%)" in html and "Season scoring (35%)" not in html
