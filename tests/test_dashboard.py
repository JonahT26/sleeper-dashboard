"""Tests for the dashboard page builder: what each week shows, hidden sections, formatting, and page limits.

Tables are synthetic, so nothing depends on this season's data; nothing touches the network.
"""

import json
import re

import pandas as pd
import pytest

from sleeper_dash.dashboard import build
from sleeper_dash.dashboard.build import (
    DashboardError, award_value, bar, build_site, build_view, movement, nice_axis, record, render, signed, updated_text,
)

WEIGHTS = {"season_scoring": 0.35, "recent_form": 0.25, "roster_strength": 0.20, "results": 0.20}
POWER = {"weights": WEIGHTS, "recent_weeks": 3}
RUN = {"finished_at": "2026-10-06T13:00:00+00:00", "league_name": "Test League", "season": 2026, "weeks": [1, 2, 3]}


def make_tables(weeks=3, n=12, award_weeks=None, team_names=None):
    """A season where team i is ranked i every week. Team 1 wins every game; the rest go 1–1 each week.

    Contributions are exact (w × (50 + gap)), so they sum to the power score.
    """
    award_weeks = range(1, weeks + 1) if award_weeks is None else award_weeks
    teams = pd.DataFrame({"season": 2026, "roster_id": range(1, n + 1),
                          "team_name": team_names or [f"Team {i}" for i in range(1, n + 1)],
                          "display_name": [f"user{i}" for i in range(1, n + 1)]})
    power, season, awards, team_weeks, lineups = [], [], [], [], []
    for week in range(1, weeks + 1):
        for i in range(1, n + 1):
            team_weeks.append({"season": 2026, "week": week, "roster_id": i, "is_playoff": week >= 15})
            actual = 140.0 - 3 * i
            lineups.append({"season": 2026, "week": week, "roster_id": i, "actual_points": actual,
                            "optimal_points": actual + i, "bench_points_lost": float(i), "efficiency": actual / (actual + i)})
            gap = ((n + 1) / 2 - i) * 2.0
            row = {"season": 2026, "week": week, "roster_id": i, "rank": i,
                   "rank_change": float("nan") if week == 1 else 0.0, "power_score": 50 + gap,
                   "season_scoring": 130.0 + gap, "recent_form": 131.0 + gap, "roster_strength": 150.0 + gap, "results": 0.5}
            row.update({f"contrib_{c}": w * (50 + gap) for c, w in WEIGHTS.items()})
            power.append(row)
            wins = 2 * week if i == 1 else week
            regular = min(week, 14)
            actual_wins = 2 * regular if i == 1 else regular
            expected = actual_wins - 0.5 + i / 12
            season.append({"season": 2026, "through_week": week, "roster_id": i,
                           "wins": wins, "losses": 2 * week - wins, "ties": 0,
                           "actual_wins": float(actual_wins), "expected_wins": expected, "luck": actual_wins - expected,
                           "efficiency": round((140.0 - 3 * i) / (140.0 - 2 * i), 4),
                           "allplay_wins": (n - i) * week, "allplay_losses": (i - 1) * week, "allplay_ties": 0,
                           "h2h_wins": week if i == 1 else 0, "h2h_losses": 0 if i == 1 else week, "h2h_ties": 0})
        if week in award_weeks:
            awards += [
                {"season": 2026, "week": week, "award": "top_score", "award_name": "Top score", "roster_id": 1,
                 "value": 150.0 + week, "caption": f"Put up {150 + week:.1f}, the best of the week.", "player_id": None},
                {"season": 2026, "week": week, "award": "blowout", "award_name": "Blowout", "roster_id": 2,
                 "value": 40.0, "caption": "Beat Team 7 by 40.0.", "player_id": None},
                {"season": 2026, "week": week, "award": "blowout", "award_name": "Blowout", "roster_id": 3,
                 "value": 40.0, "caption": "Beat Team 8 by 40.0.", "player_id": None},
            ]
    return {"teams": teams, "team_weeks": pd.DataFrame(team_weeks), "lineups_optimal": pd.DataFrame(lineups),
            "power_rankings": pd.DataFrame(power), "metrics_season": pd.DataFrame(season),
            "awards": pd.DataFrame(awards, columns=["season", "week", "award", "award_name", "roster_id", "value", "caption", "player_id"])}


def page(**kwargs):
    return render(build_view(make_tables(**kwargs), RUN, POWER))


def split(html):
    """(the part of the page shown on load, {week: that week's <template> HTML})."""
    templates = dict(re.findall(r'<template id="week-(\d+)"[^>]*>(.*?)</template>', html, re.S))
    shown = re.sub(r"<template.*?</template>", "", html, flags=re.S)
    return shown, {int(k): v for k, v in templates.items()}


# --- What the page shows -------------------------------------------------------------------

def test_page_opens_on_the_latest_week_drawn_into_the_html():
    shown, _ = split(page())
    assert '<h1 class="title display" id="title">Week 3 power rankings</h1>' in shown
    assert shown.count('<li class="team" data-roster=') == 12
    assert "Test League" in shown and "Updated Tue Oct 6, 9:00 AM ET" in shown
    assert re.search(r'<option value="3" selected>Week 3</option>', shown)


def test_every_earlier_week_waits_in_a_template_for_the_selector():
    html = page()
    _, templates = split(html)
    assert sorted(templates) == [1, 2]
    assert 'data-title="Week 1 power rankings"' in html
    assert all(t.count('<li class="team" data-roster=') == 12 for t in templates.values())


def test_each_week_shows_records_and_details_as_of_that_week():
    shown, templates = split(page())
    assert "2–0, all-play 11–0" in templates[1] and "4–0, all-play 22–0" in templates[2] and "6–0, all-play 33–0" in shown
    assert "points a week, this week" in templates[1] and "last 2 weeks" in templates[2] and "last 3 weeks" in shown
    assert "Won 1 of 1" in templates[1] and "Won 3 of 3" in shown
    assert "151.0" in templates[1] and "153.0" in shown  # that week's top score


def test_a_week_without_awards_has_no_awards_section():
    shown, templates = split(page(award_weeks=[1, 3]))
    assert "Weekly awards" in templates[1] and "Weekly awards" in shown
    assert "Weekly awards" not in templates[2] and "tile" not in templates[2]


def test_co_winners_share_one_tile():
    shown, _ = split(page())
    assert shown.count('<li class="tile">') == 2
    blowout = shown[shown.index(">Blowout<"):]
    assert "Beat Team 7 by 40.0." in blowout and "Beat Team 8 by 40.0." in blowout


def test_breakdown_scores_add_up_to_the_power_score_and_gaps_to_the_gap():
    view = build_view(make_tables(), RUN, POWER)
    for team in view["latest"]["ladder"]:
        assert sum(float(p["score"]) for p in team["parts"]) == pytest.approx(float(team["score"]), abs=0.2)
        assert [p["label"] for p in team["parts"]] == ["Season scoring", "Recent form", "Roster strength", "Head-to-head wins"]
        gaps = sum(float(p["gap"].replace("−", "-")) for p in team["parts"])
        assert gaps == pytest.approx(float(team["gap"].replace("−", "-")), abs=0.2)
    top = view["latest"]["ladder"][0]
    assert top["score"] == "61.0" and top["gap"] == "+11.0" and top["parts"][2]["gap"] == "+2.2"


def test_only_the_top_team_is_listed_first_and_movement_reads_for_screen_readers():
    view = build_view(make_tables(), RUN, POWER)
    assert [t["rank"] for t in view["latest"]["ladder"]] == list(range(1, 13))
    assert view["earlier"][0]["ladder"][0]["move"]["spoken"] == "first week"
    assert view["latest"]["ladder"][0]["move"]["spoken"] == "no change"


def test_ties_appear_only_once_the_league_has_had_one():
    tables = make_tables()
    assert "–0–" not in render(build_view(tables, RUN, POWER))
    tables["metrics_season"].loc[tables["metrics_season"]["roster_id"] == 2, "allplay_ties"] = 1
    shown, _ = split(render(build_view(tables, RUN, POWER)))
    assert "all-play 30–3–1" in shown and "6–0," in shown  # all-play ties shown; the record has none, so stays 2-part


def test_team_names_are_escaped():
    names = ["<script>alert(1)</script>"] + [f"Team {i}" for i in range(2, 13)]
    html = page(team_names=names)
    assert "<script>alert(1)" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# --- Page limits (docs/UI_GUIDE.md "Quality floor") -----------------------------------------

def test_only_google_fonts_and_plotly_are_loaded_from_outside_the_page():
    urls = re.findall(r'(?:src|href)="(https?://[^"]+)"', page())
    assert urls and all(u.startswith(("https://fonts.googleapis.com", "https://fonts.gstatic.com", "https://cdn.plot.ly/")) for u in urls)
    assert '<script src="https://cdn.plot.ly/plotly-basic-' in page() and " defer>" in page()


def test_a_full_17_week_season_stays_under_1_mb():
    html = page(weeks=17)
    assert len(html.encode("utf-8")) < 1_000_000
    assert len(split(html)[1]) == 16


# --- Formatting -----------------------------------------------------------------------------

@pytest.mark.parametrize("value, text", [(2.56, "+2.6"), (-0.7, "−0.7"), (-0.04, "0.0"), (0.0, "0.0"), (11.0, "+11.0")])
def test_signed(value, text):
    assert signed(value) == text


def test_record_and_axis_and_bar_geometry():
    assert record(8, 2, 0, False) == "8–2" and record(8, 1, 1, True) == "8–1–1"
    assert nice_axis(12.9, [5, 10, 15]) == 15 and nice_axis(15, [5, 10, 15]) == 15 and nice_axis(99, [5, 10]) == 10
    assert bar(7.5, 15) == {"left": "50.00", "width": "25.00", "side": "pos"}
    assert bar(-7.5, 15) == {"left": "25.00", "width": "25.00", "side": "neg"}
    assert bar(-30, 15)["width"] == "50.00"  # never past the end of the track


def test_movement_and_award_values():
    assert movement(2) == {"kind": "up", "text": "▲2", "spoken": "up 2"}
    assert movement(-1.0)["text"] == "▼1" and movement(0)["spoken"] == "no change" and movement(float("nan"))["spoken"] == "first week"
    assert award_value("top_score", 147.04) == "147.0" and award_value("perfect_lineup", 0.874) == "87%"
    assert award_value("asleep_at_the_wheel", 2.0) == "2"


def test_updated_time_is_shown_in_eastern_time_across_daylight_saving():
    assert updated_text("2026-10-03T02:23:58+00:00") == "Fri Oct 2, 10:23 PM ET"   # EDT, UTC−4
    assert updated_text("2026-12-08T14:00:00+00:00") == "Tue Dec 8, 9:00 AM ET"    # EST, UTC−5


# --- Files -----------------------------------------------------------------------------------

def test_build_site_writes_the_page_from_saved_csvs(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    for name, table in make_tables().items():
        table.to_csv(processed / f"{name}.csv", index=False, encoding="utf-8-sig")
    run_path = tmp_path / "pipeline_run.json"
    run_path.write_text(json.dumps(RUN), encoding="utf-8")
    path, view = build_site(out_dir=tmp_path / "site", processed_dir=processed, run_path=run_path)
    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert view["weeks"] == [1, 2, 3]


def test_missing_run_record_stops_with_a_clear_message(tmp_path, monkeypatch, capsys):
    with pytest.raises(DashboardError, match="pipeline"):
        build.read_run_record(tmp_path / "nope.json")
    monkeypatch.setattr(build, "build_site", lambda: (_ for _ in ()).throw(DashboardError("Run the pipeline first.")))
    with pytest.raises(SystemExit, match="DASHBOARD NOT BUILT"):
        build.main()


def test_no_power_rankings_stops_with_a_clear_message():
    tables = make_tables()
    tables["power_rankings"] = tables["power_rankings"].iloc[0:0]
    with pytest.raises(DashboardError, match="pipeline"):
        build_view(tables, RUN, POWER)
