"""Tests for the shared chart theme and the Luck and Lineup efficiency charts."""

import re

import plotly.graph_objects as go
import plotly.offline
import pytest

from sleeper_dash.dashboard import charts, theme
from sleeper_dash.dashboard.build import build_view, render
from sleeper_dash.dashboard.theme import PLOTLY_JS_VERSION, base_layout, merge, resolve_tokens, to_script_json
from test_dashboard import METRICS, RUN, make_tables, split

LIGHT = {"page": "#F6F8F4", "ink": "#15201A", "muted": "#5B6B61", "hash": "#D5DDD7", "bar": "#9AA79F", "pylon": "#E8590C"}


def view(**kwargs):
    return build_view(make_tables(**kwargs), RUN, METRICS)


def chart(v, key):
    return next(c for c in v["charts"] if c["key"] == key)


# --- The theme -------------------------------------------------------------------------------

def test_cdn_plotly_matches_the_installed_python_plotly():
    assert PLOTLY_JS_VERSION == plotly.offline.get_plotlyjs_version()


def test_theme_follows_the_guide():
    layout = base_layout()
    assert theme.CONFIG["displayModeBar"] is False and theme.CONFIG["responsive"] is True
    assert layout["xaxis"]["showgrid"] is False and layout["yaxis"]["showgrid"] is True   # horizontal gridlines only
    assert layout["yaxis"]["gridcolor"] == "@hash" and layout["showlegend"] is False      # direct labels, no legends
    assert layout["paper_bgcolor"] == layout["plot_bgcolor"] == "rgba(0,0,0,0)"           # no background fills
    assert layout["dragmode"] is False and layout["xaxis"]["fixedrange"] and layout["yaxis"]["fixedrange"]


def test_every_colour_token_is_a_css_custom_property_in_both_modes():
    from importlib.resources import files

    css = files("sleeper_dash.dashboard").joinpath("templates/styles.css").read_text(encoding="utf-8")
    light, dark = css.split("@media (prefers-color-scheme: dark)")[:2]
    for token in theme.TOKENS:
        assert f"--{token}:" in light and f"--{token}:" in dark.split("}")[0] + dark, token


def test_only_known_tokens_are_used():
    text = render(view())
    used = set(re.findall(r'"@(\w+)"', text))
    assert used and used <= set(theme.TOKENS)


def test_script_json_cannot_end_its_script_early():
    import json

    text = to_script_json({"text": "</script><b>"})
    assert "<" not in text and json.loads(text) == {"text": "</script><b>"}


def test_team_names_are_escaped_in_chart_text():
    tables = make_tables(team_names=["<b>Bold</b> & co"] + [f"Team {i}" for i in range(2, 13)])
    v = build_view(tables, RUN, METRICS)
    eff = chart(v["latest"], "efficiency")["figure"]
    assert "&lt;b&gt;Bold&lt;/b&gt; &amp; co" in [a["text"] for a in eff["layout"]["annotations"]]
    assert chart(v["latest"], "luck")["figure"]["data"][1]["hovertext"][0].startswith("&lt;b&gt;Bold")


# --- Both charts -----------------------------------------------------------------------------

def test_every_figure_is_valid_plotly_once_colours_are_filled_in():
    v = view()
    for week_view in [v["latest"], *v["earlier"]]:
        for c in week_view["charts"]:
            figure = resolve_tokens(c["figure"], LIGHT)
            go.Figure(data=figure["data"], layout=merge(resolve_tokens(base_layout(), LIGHT), figure["layout"]))  # raises if invalid


def test_charts_follow_the_week_selector():
    shown, templates = split(render(view()))
    assert 'id="fig-luck-3"' in shown and 'id="fig-efficiency-3"' in shown
    assert 'id="fig-luck-1"' in templates[1] and 'id="fig-efficiency-2"' in templates[2]
    assert "through week 1." in templates[1] and "Through week 3." in shown


def test_the_weeks_top_team_is_highlighted_and_everyone_else_is_grey():
    luck = chart(view()["latest"], "luck")["figure"]
    points = luck["data"][1]
    assert luck["highlight"] == 1
    assert [c for r, c in zip(points["meta"]["rosters"], points["marker"]["color"]) if r == 1] == ["@pylon"]
    assert points["marker"]["color"].count("@bar") == 11


def test_each_chart_has_a_title_a_how_to_read_subtitle_and_a_text_summary():
    for c in view()["latest"]["charts"]:
        assert c["title"] and c["subtitle"] and c["summary"]
    shown, _ = split(render(view()))
    assert 'role="img" aria-label="Luck through week 3.' in shown and 'class="chart-fallback"' in shown


# --- Luck ------------------------------------------------------------------------------------

def test_luck_plots_expected_against_actual_with_a_45_degree_line_and_every_team_labelled():
    luck = chart(view()["latest"], "luck")["figure"]
    line, points = luck["data"]
    assert line["x"] == line["y"] and line["x"][0] == 0
    assert len(points["x"]) == 12 and points["y"][0] == 6.0           # team 1: 6 wins through week 3
    assert sorted(label["text"] for label in luck["labels"]) == sorted(f"Team {i}" for i in range(1, 13))
    assert luck["layout"]["xaxis"]["range"] == luck["layout"]["yaxis"]["range"]
    assert luck["layout"]["yaxis"]["scaleanchor"] == "x"


def test_luck_names_the_luckiest_and_unluckiest():
    summary = chart(view()["latest"], "luck")["summary"]
    assert "Luckiest: Team 1, 6 wins from 5.6 expected (+0.4)" in summary
    assert "Unluckiest: Team 12, 3 wins from 3.5 expected (−0.5)" in summary


def test_luck_says_regular_season_once_the_playoffs_start():
    v = view(weeks=16)
    assert chart(v["latest"], "luck")["subtitle"].endswith("Regular season, through week 14.")
    assert chart(v["earlier"][13], "luck")["subtitle"].endswith("Through week 14.")


# --- Lineup efficiency -----------------------------------------------------------------------

def test_efficiency_rows_are_sorted_by_season_efficiency_with_points_per_week():
    eff = chart(view()["latest"], "efficiency")["figure"]
    names = [a["text"] for a in eff["layout"]["annotations"] if a["xanchor"] == "left"]
    rows = [a["y"] for a in eff["layout"]["annotations"] if a["xanchor"] == "left"]
    assert names[0] == "Team 1" and names[-1] == "Team 12" and rows == sorted(rows, reverse=True)  # most efficient on top
    actual, optimal = eff["data"][-2], eff["data"][-1]
    assert actual["x"][0] == 137.0 and optimal["x"][0] == 138.0     # team 1: 137 scored, 138 possible, per week
    assert optimal["marker"]["color"] == "@page"                      # open dot
    percents = [a["text"] for a in eff["layout"]["annotations"] if a["xanchor"] == "right"]
    assert percents[0] == "99%" and len(percents) == 12


def test_a_week_without_lineups_has_no_efficiency_chart():
    tables = make_tables()
    tables["lineups_optimal"] = tables["lineups_optimal"][tables["lineups_optimal"]["week"] > 1]
    v = build_view(tables, RUN, METRICS)
    assert [c["key"] for c in v["earlier"][0]["charts"]] == ["luck"]
    assert [c["key"] for c in v["latest"]["charts"]][:2] == ["luck", "efficiency"]


@pytest.mark.parametrize("value, text", [(3.0, "3 wins"), (1.0, "1 win"), (2.5, "2.5 wins")])
def test_win_counts_read_naturally(value, text):
    assert charts._wins(value) == text


# --- Which charts each week shows ------------------------------------------------------------

def test_charts_appear_once_their_data_exists_in_guide_order():
    v = view()
    keys = {w["week"]: [c["key"] for c in w["charts"]] for w in [*v["earlier"], v["latest"]]}
    assert keys[1] == ["luck", "efficiency"]                                  # no rank history from one week
    assert keys[2] == ["luck", "efficiency", "rank_history"]                  # consistency and schedule need 3 weeks
    assert keys[3] == ["luck", "efficiency", "consistency", "schedule", "rank_history"]
    shown, templates = split(render(v))
    assert "Consistency:" in shown and "Consistency:" not in templates[2]     # hidden entirely, no placeholder


# --- Consistency -----------------------------------------------------------------------------

def test_consistency_shows_every_weekly_score_steadiest_first_with_the_league_median():
    c = chart(view()["latest"], "consistency")["figure"]
    band, dots = c["data"]
    assert len(dots["x"]) == 12 * 3 and dots["meta"]["rosters"].count(1) == 3
    names = [a["text"] for a in c["layout"]["annotations"] if a.get("name")]
    assert names[0] == "Team 1" and names[-1] == "Team 12"                    # volatility 11 … 22: steadiest on top
    values = [a["text"] for a in c["layout"]["annotations"] if a.get("xanchor") == "right"]
    assert values[0] == "±11.0"
    median_line = c["layout"]["shapes"][0]
    assert median_line["x0"] == median_line["x1"] and any(a["text"].startswith("League median") for a in c["layout"]["annotations"])
    assert band["x"][:2] == [119.0, 141.0]                                    # team 1's floor to ceiling


# --- Strength of schedule --------------------------------------------------------------------

def test_schedule_has_played_and_remaining_panels_with_bars_from_the_average():
    c = chart(view()["latest"], "schedule")["figure"]
    played, remaining = c["data"]
    assert played["xaxis"] == "x" and remaining["xaxis"] == "x2" and played["orientation"] == "h"
    assert played["x"][0] == 11.0 and played["text"][0] == "+11.0"           # toughest schedule first (team 12)
    assert c["layout"]["xaxis"]["ticktext"] == ["−10", "0", "+10"]          # whole-number ticks
    assert c["layout"]["xaxis2"]["title"]["font"]["size"] == 13               # second panel styled by the theme too
    assert {s["xref"] for s in c["layout"]["shapes"]} == {"x", "x2"}          # a zero line in each panel


def test_schedule_with_every_remaining_schedule_average_says_so_instead_of_drawing_empty_bars():
    s = chart(build_view(make_tables(flat_remaining=True), RUN, METRICS)["latest"], "schedule")
    assert len(s["figure"]["data"]) == 1 and "xaxis2" not in s["figure"]["layout"]
    assert s["subtitle"].endswith("Still to come: every team's remaining opponents are exactly average (0.0).")


def test_schedule_after_the_regular_season_shows_played_only():
    s = chart(view(weeks=15)["latest"], "schedule")
    assert len(s["figure"]["data"]) == 1 and "Regular-season games, through week 15." in s["subtitle"]


# --- Rank history ----------------------------------------------------------------------------

def test_rank_history_draws_one_grey_line_per_team_with_the_top_team_highlighted():
    c = chart(view()["latest"], "rank_history")
    fig = c["figure"]
    assert len(fig["data"]) == 12 and c["wide"] is True
    colours = {t["meta"]["roster"]: t["line"]["color"] for t in fig["data"]}
    assert colours[1] == "@pylon" and set(colours.values()) == {"@pylon", "@bar"} and list(colours.values()).count("@pylon") == 1
    assert fig["layout"]["yaxis"]["range"] == [12.5, 0.5]                     # rank 1 at the top
    labels = [a for a in fig["layout"]["annotations"] if a.get("captureevents")]
    assert len(labels) == 12 and all(a["x"] == 3 for a in labels)             # names at the end of each line, tappable


def test_rank_history_gives_phones_shorter_names_and_more_room_for_the_lines():
    names = ["Burrow UrFace N My Butker", "Lawrence & Order: SNU", "Fourteen chars"] + [f"Team {i}" for i in range(4, 13)]
    fig = chart(build_view(make_tables(team_names=names), RUN, METRICS)["latest"], "rank_history")["figure"]
    labels = fig["phone"]["labels"]
    assert labels["1"] == "Burrow UrFace…" and labels["2"] == "Lawrence &amp; Or…"      # cut before escaping
    assert labels["3"] == "Fourteen chars" and labels["4"] == "Team 4"          # 14 characters or fewer: unchanged
    assert all(len(text.replace("&amp;", "&")) <= 14 for text in labels.values())
    assert fig["phone"]["margin"]["r"] < fig["layout"]["margin"]["r"]
    phone_layout = dict(fig["layout"], margin=dict(fig["layout"]["margin"], **fig["phone"]["margin"]),
                        annotations=[dict(a, text=labels[a["name"]], hovertext=a["text"]) for a in fig["layout"]["annotations"]])
    go.Figure(data=resolve_tokens(fig["data"], LIGHT), layout=resolve_tokens(phone_layout, LIGHT))  # what charts.js draws on a phone


def test_team_name_labels_can_be_tapped_to_highlight():
    v = view()
    for c in v["latest"]["charts"]:
        for a in c["figure"]["layout"].get("annotations", []):
            if a.get("name"):
                assert a["captureevents"] is True and a["name"].isdigit()
