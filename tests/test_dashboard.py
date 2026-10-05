"""Tests for the dashboard page builder: what each week shows, hidden sections, formatting, and page limits.

Tables are synthetic, so nothing depends on this season's data; nothing touches the network.
"""

import html as html_lib
import json
import re
from datetime import datetime

import pandas as pd
import pytest

from sleeper_dash.dashboard import build
from sleeper_dash.dashboard.build import (
    DashboardError, award_value, bar, build_site, build_view, movement, nice_axis, record, render, signed, updated_text,
)

WEIGHTS = {"season_scoring": 0.35, "recent_form": 0.25, "roster_strength": 0.20, "results": 0.20}
METRICS = {"power": {"weights": WEIGHTS, "recent_weeks": 3, "scale": 15, "shrink_weeks": 3},
           "consistency": {"min_weeks": 3, "floor_pct": 0.10, "ceiling_pct": 0.90, "boom_margin": 20, "bust_margin": 20},
           "schedule": {"min_weeks": 3},
           "playoff_odds": {"simulations": 10000, "seed": 2026, "shrink_weeks": 6, "min_weeks": 3}}
RUN = {"finished_at": "2026-10-06T13:00:00+00:00", "league_name": "Test League", "season": 2026, "weeks": [1, 2, 3],
       "league": {"teams": 12, "median_game": True, "playoff_week_start": 15, "playoff_teams": 6}}
# Synthetic playoff odds for teams 1-12 (each column sums like the real table: 6 playoff spots, 2 byes, 1 title).
ODDS_PLAYOFFS = [1.0, 0.999, 0.97, 0.85, 0.7, 0.55, 0.45, 0.3, 0.12, 0.05, 0.011, 0.0]
ODDS_BYE = [0.9, 0.6, 0.3, 0.12, 0.05, 0.02, 0.008, 0.002, 0.0, 0.0, 0.0, 0.0]
ODDS_TITLE = [0.4, 0.2, 0.15, 0.1, 0.06, 0.04, 0.025, 0.015, 0.007, 0.003, 0.0, 0.0]
ODDS_PROVEN_FROM = 10  # team 1 is Clinched and team 12 Out from this week (before it: ">99%" and "<1%")


def make_tables(weeks=3, n=12, award_weeks=None, team_names=None, flat_remaining=False):
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
            team_weeks.append({"season": 2026, "week": week, "roster_id": i, "is_playoff": week >= 15,
                               "points": 140.0 - 3 * i + (week % 3) * (i % 4)})
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
                           # consistency and strength of schedule appear from week 3 (min_weeks); remaining ends after week 14
                           "volatility": 10.0 + i if week >= 3 else None, "floor": 120.0 - i if week >= 3 else None,
                           "ceiling": 140.0 + i if week >= 3 else None, "sos_played": (i - 6.5) * 2 if week >= 3 else None,
                           "sos_remaining": (0.0 if flat_remaining else 6.5 - i) if 3 <= week < 14 else None,
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
            "awards": pd.DataFrame(awards, columns=["season", "week", "award", "award_name", "roster_id", "value", "caption", "player_id"]),
            "playoff_odds": make_odds(range(3, min(weeks, 14) + 1), n)}


def make_odds(weeks, n=12):
    """playoff_odds rows for the given weeks (METRICS_SPEC.md section 8 columns), from the ODDS_ vectors."""
    rows = []
    for week in weeks:
        for i in range(1, n + 1):
            p, bye, title = ODDS_PLAYOFFS[i - 1], ODDS_BYE[i - 1], ODDS_TITLE[i - 1]
            rest = (p - bye) / 4
            rows.append({"season": 2026, "week": week, "roster_id": i, "strength": 10.0 - i, "strength_sd": 7.0, "score_sd": 21.0,
                         "p_playoffs": p, "p_bye": bye, "p_seed_1": bye * 0.6, "p_seed_2": bye * 0.4,
                         **{f"p_seed_{s}": rest for s in range(3, 7)}, "p_title": title,
                         "avg_wins": 26.0 - 2 * i + 0.25, "avg_losses": 2.0 + 2 * i - 0.25,
                         "clinched": i == 1 and week >= ODDS_PROVEN_FROM, "out": i == n and week >= ODDS_PROVEN_FROM})
    return pd.DataFrame(rows)


def page(**kwargs):
    return render(build_view(make_tables(**kwargs), RUN, METRICS))


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
    assert "Test League" in shown and 'Updated <time datetime="2026-10-06T13:00:00+00:00">Tue Oct 6, 9:00 AM ET</time>' in shown
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
    view = build_view(make_tables(), RUN, METRICS)
    for team in view["latest"]["ladder"]:
        assert sum(float(p["score"]) for p in team["parts"]) == pytest.approx(float(team["score"]), abs=0.2)
        assert [p["label"] for p in team["parts"]] == ["Season scoring", "Recent form", "Roster strength", "Head-to-head wins"]
        gaps = sum(float(p["gap"].replace("−", "-")) for p in team["parts"])
        assert gaps == pytest.approx(float(team["gap"].replace("−", "-")), abs=0.2)
    top = view["latest"]["ladder"][0]
    assert top["score"] == "61.0" and top["gap"] == "+11.0" and top["parts"][2]["gap"] == "+2.2"


def test_only_the_top_team_is_listed_first_and_movement_reads_for_screen_readers():
    view = build_view(make_tables(), RUN, METRICS)
    assert [t["rank"] for t in view["latest"]["ladder"]] == list(range(1, 13))
    assert view["earlier"][0]["ladder"][0]["move"]["spoken"] == "first week"
    assert view["latest"]["ladder"][0]["move"]["spoken"] == "no change"


def test_ties_appear_only_once_the_league_has_had_one():
    tables = make_tables()
    assert "–0–" not in render(build_view(tables, RUN, METRICS))
    tables["metrics_season"].loc[tables["metrics_season"]["roster_id"] == 2, "allplay_ties"] = 1
    shown, _ = split(render(build_view(tables, RUN, METRICS)))
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


def test_a_full_17_week_season_downloads_under_1_mb():
    """The page-weight budget counts compressed bytes, what a visitor downloads (owner decision 2026-10-02)."""
    import gzip

    html = page(weeks=17)
    assert len(split(html)[1]) == 16
    assert len(gzip.compress(html.encode("utf-8"))) < 1_000_000


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


# --- Freshness: the stale-data line ------------------------------------------------------------

def utc(text):
    return datetime.fromisoformat(text)


def test_the_schedule_is_read_from_the_weekly_workflow():
    """Tuesday and Thursday 12:17 PM Eastern (owner, 2026-10-03), straight from the cron lines GitHub runs."""
    schedule = build.workflow_schedule()
    assert [(minute, hour, days, str(zone)) for minute, hour, days, zone in schedule] == [
        (17, 12, {2}, "America/New_York"), (17, 12, {4}, "America/New_York")]


def test_next_updates_are_the_scheduled_runs_after_the_last_one_in_eastern_time():
    upcoming = build.upcoming_updates(build.workflow_schedule(), utc("2026-10-06T16:30:00+00:00"), days=10)
    assert [u["text"] for u in upcoming] == ["Thu Oct 8, 12:17 PM ET", "Tue Oct 13, 12:17 PM ET", "Thu Oct 15, 12:17 PM ET"]
    assert upcoming[0]["at"] == "2026-10-08T16:17:00+00:00"


def test_next_updates_follow_daylight_saving_like_github():
    # Clocks go back on Sun Nov 1, 2026: 12:17 PM Eastern is 16:17 UTC before and 17:17 UTC after.
    upcoming = build.upcoming_updates(build.workflow_schedule(), utc("2026-10-29T17:00:00+00:00"), days=6)
    assert [(u["at"], u["text"]) for u in upcoming] == [("2026-11-03T17:17:00+00:00", "Tue Nov 3, 12:17 PM ET")]


def test_a_run_just_before_its_slot_lists_that_slot():
    upcoming = build.upcoming_updates(build.workflow_schedule(), utc("2026-10-06T16:00:00+00:00"), days=3)
    assert [u["text"] for u in upcoming] == ["Tue Oct 6, 12:17 PM ET", "Thu Oct 8, 12:17 PM ET"]


def test_the_page_lists_four_months_of_scheduled_updates():
    fresh = build.freshness(RUN, 8, build.workflow_schedule())
    assert fresh["stale_after_days"] == 8
    assert len(fresh["next_updates"]) == 35  # Tuesdays and Thursdays in the 120 days after Tue Oct 6, 9 AM ET
    assert fresh["next_updates"][0]["text"] == "Tue Oct 6, 12:17 PM ET"   # the same day's run, still ahead
    assert fresh["next_updates"][-1]["text"] == "Tue Feb 2, 12:17 PM ET"


@pytest.mark.parametrize("cron", ["17 12 * * 1-5", "*/15 * * * *", "17 12 1 * *", "17 12 * * TUE"])
def test_a_schedule_the_page_cannot_read_stops_the_build(tmp_path, cron):
    workflow = tmp_path / "weekly.yml"
    workflow.write_text(f'on:\n  schedule:\n    - cron: "{cron}"\n', encoding="utf-8")
    with pytest.raises(DashboardError, match="only 'minute hour \\* \\* weekdays'"):
        build.workflow_schedule(workflow)


def test_a_workflow_without_a_schedule_stops_the_build(tmp_path):
    workflow = tmp_path / "weekly.yml"
    workflow.write_text("on:\n  workflow_dispatch:\n", encoding="utf-8")
    with pytest.raises(DashboardError, match="no schedule"):
        build.workflow_schedule(workflow)


def test_once_the_season_is_over_the_stale_line_says_final_rankings():
    """Owner, 2026-10-03: after the season, no "next update" promise; the line names the season instead."""
    done = {**RUN, "league": {**RUN["league"], "season_complete": True}}
    html = render(build_view(make_tables(), done, METRICS, build.freshness(done, 8, build.workflow_schedule())))
    assert '<p class="stale" id="stale" hidden>Final rankings for the 2026 season.</p>' in html
    assert 'id="next-updates"' not in html and "Next update due" not in html
    in_season = render(build_view(make_tables(), RUN, METRICS, build.freshness(RUN, 8, build.workflow_schedule())))
    assert "Final rankings for the" not in in_season and "The latest rankings are from week 3." in in_season


def test_without_freshness_the_page_has_no_stale_line_but_still_shows_the_update_time():
    html = page()
    assert 'id="stale"' not in html and "data-stale-after-days" not in html
    assert "Updated <time" in html


# --- Files -----------------------------------------------------------------------------------

def test_build_site_writes_the_page_from_saved_csvs(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    for name, table in make_tables().items():
        table.to_csv(processed / f"{name}.csv", index=False, encoding="utf-8-sig")
    run_path = tmp_path / "pipeline_run.json"
    run_path.write_text(json.dumps(RUN), encoding="utf-8")
    path, view = build_site(out_dir=tmp_path / "site", processed_dir=processed, run_path=run_path)
    html = path.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert view["weeks"] == [1, 2, 3]
    # The published page always carries the stale-data line, the configured threshold, and the schedule.
    assert 'id="stale" hidden' in html and 'data-stale-after-days="8"' in html
    assert '"text":"Thu Oct 8, 12:17 PM ET"' in html


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
        build_view(tables, RUN, METRICS)


# --- Playoff odds (METRICS_SPEC.md section 8; UI_GUIDE.md "Playoff odds") -----------------------

def odds_rows(html, week):
    shown, templates = split(html)
    part = shown if week == max([week, *templates]) and week not in templates else templates[week]
    section = re.search(r'<section class="odds-section".*?</section>', part, re.S)
    return section and html_lib.unescape(section.group(0))  # "&gt;99%" in the HTML is ">99%" on screen


def test_playoff_odds_sit_after_the_ladder_from_week_3_only():
    html = page(weeks=5)
    shown, templates = split(html)
    assert odds_rows(html, 1) is None and odds_rows(html, 2) is None  # min_weeks 3: hidden before
    for week in (3, 4, 5):
        part = shown if week == 5 else templates[week]
        assert part.index('class="ladder-section"') < part.index('class="odds-section"') < part.index('class="awards"')


def test_odds_extremes_say_less_than_1_percent_until_a_bound_proves_them():
    html = page(weeks=12)
    early, late = odds_rows(html, 9), odds_rows(html, 10)
    first, last = (re.findall(r'<tr data-roster="(\d+)">.*?<span class="po-val">(.+?)</span>', part, re.S) for part in (early, late))
    assert first[0] == ("1", ">99%") and first[-1] == ("12", "<1%")  # p = 1.0 and 0.0, not proved yet
    assert last[0] == ("1", "Clinched") and last[-1] == ("12", "Out")
    assert ("2", ">99%") in first  # 0.999 rounds to 100%, so it can't say 100%


def test_the_last_regular_season_week_says_the_field_is_set():
    html = page(weeks=15)
    assert "The regular season is over and the top 6 are in" in odds_rows(html, 14)
    assert "Chances from 10,000 simulations" in odds_rows(html, 13)
    assert odds_rows(html, 15) is None  # playoff weeks: the table ends at week 14
