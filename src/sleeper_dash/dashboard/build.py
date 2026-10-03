"""Build the static dashboard page, site/index.html, from the saved tables (docs/UI_GUIDE.md).

Run with:  python -m sleeper_dash.dashboard   (after python -m sleeper_dash.pipeline)

Python does all the formatting: build_view turns the tables into plain values and strings
for every completed week, and one Jinja2 template draws them. The latest week is drawn
straight into the page, so it shows without JavaScript; every other week is drawn into a
<template> block that the week selector swaps in, so switching weeks needs no network call.
Each week shows rankings, records, and metrics as of that week. A section with no data for
a week is left out entirely (owner decision, no placeholder).
"""

import json
import math
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from jinja2 import Environment, PackageLoader

from sleeper_dash.config import PROJECT_ROOT
from sleeper_dash.dashboard import charts, theme

SITE_DIR = PROJECT_ROOT / "site"
TABLES = ["teams", "team_weeks", "power_rankings", "metrics_season", "lineups_optimal", "awards"]
EASTERN = ZoneInfo("America/New_York")

# Ladder breakdown rows, in display order (METRICS_SPEC.md section 6; labels from UI_GUIDE.md Ladder row).
COMPONENTS = ["season_scoring", "recent_form", "roster_strength", "results"]
COMPONENT_LABELS = {"season_scoring": "Season scoring", "recent_form": "Recent form",
                    "roster_strength": "Roster strength", "results": "Head-to-head wins"}
# Round axis ends for the bars, so one fixed scale serves every week of the season.
POWER_AXIS_STEPS = [5, 10, 15, 20, 25, 30, 40, 50]
PART_AXIS_STEPS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20]
# How each award's value is shown on its tile (points to 1 dp unless listed).
AWARD_FORMATS = {"perfect_lineup": "percent", "asleep_at_the_wheel": "count"}

EN_DASH, MINUS = "–", "−"


class DashboardError(Exception):
    """The page can't be built from what's on disk; the message says what to run."""


# --- Formatting (docs/UI_GUIDE.md "Numbers and copy") ------------------------------------------

def one_dp(value):
    """Points and scores: 1 decimal place."""
    return f"{value:.1f}"


def signed(value):
    """A gap from average: +2.6, −0.7, or 0.0 when it rounds to zero."""
    text = f"{abs(value):.1f}"
    if text == "0.0":
        return text
    return ("+" if value > 0 else MINUS) + text


def record(wins, losses, ties, show_ties):
    """8–2, or 8–1–1 once the league has had a tie."""
    return EN_DASH.join(str(int(n)) for n in ((wins, losses, ties) if show_ties else (wins, losses)))


def nice_axis(largest, steps):
    """The smallest round number in steps that covers the largest gap (the last step if none does)."""
    return next((step for step in steps if step >= largest - 1e-9), steps[-1])


def bar(gap, axis):
    """Geometry of a bar running right (gap > 0) or left (gap < 0) from a centre line, in % of its track."""
    width = min(abs(gap) / axis, 1) * 50
    left = 50 if gap >= 0 else 50 - width
    return {"left": f"{left:.2f}", "width": f"{width:.2f}", "side": "pos" if gap >= 0 else "neg"}


def movement(change):
    """Rank movement: arrow plus number, with words for screen readers."""
    if change is None or pd.isna(change) or change == 0:
        return {"kind": "same", "text": EN_DASH, "spoken": "first week" if change is None or pd.isna(change) else "no change"}
    change = int(change)
    if change > 0:
        return {"kind": "up", "text": f"▲{change}", "spoken": f"up {change}"}
    return {"kind": "down", "text": f"▼{-change}", "spoken": f"down {-change}"}


def award_value(award, value):
    kind = AWARD_FORMATS.get(award, "points")
    if kind == "percent":
        return f"{round(value * 100)}%"
    if kind == "count":
        return str(int(value))
    return one_dp(value)


def updated_text(finished_at):
    """'Tue Oct 6, 9:00 AM ET' from the pipeline's ISO timestamp."""
    when = datetime.fromisoformat(finished_at).astimezone(EASTERN)
    return f"{when:%a %b} {when.day}, {when.hour % 12 or 12}:{when:%M} {'AM' if when.hour < 12 else 'PM'} ET"


# --- View model -----------------------------------------------------------------------------

def build_view(tables, run, power_params):
    """Everything the template needs, as plain values and formatted strings. Pure: no file access.

    tables: teams, team_weeks, power_rankings, metrics_season, lineups_optimal, awards. run: the pipeline's run record.
    power_params: config.yaml metrics.power (weights and recent_weeks).
    """
    teams = tables["teams"].set_index("roster_id")
    power, season, awards = tables["power_rankings"], tables["metrics_season"], tables["awards"]
    lineups, team_weeks = tables["lineups_optimal"], tables["team_weeks"]
    names = teams["team_name"].to_dict()
    regular_weeks = sorted(int(w) for w in team_weeks.loc[~team_weeks["is_playoff"].astype(bool), "week"].unique())
    weights, recent_weeks = power_params["weights"], power_params["recent_weeks"]
    weeks = sorted(int(w) for w in power["week"].unique())
    if not weeks:
        raise DashboardError("No power rankings to show. Run `python -m sleeper_dash.pipeline` first.")

    gaps = power[[f"contrib_{c}" for c in COMPONENTS]] - [50 * weights[c] for c in COMPONENTS]
    power_axis = nice_axis((power["power_score"] - 50).abs().max(), POWER_AXIS_STEPS)
    part_axis = nice_axis(gaps.abs().max().max(), PART_AXIS_STEPS)
    so_far = season[season["through_week"] == weeks[-1]]
    show_ties, show_allplay_ties = bool((so_far["ties"] > 0).any()), bool((so_far["allplay_ties"] > 0).any())

    views = []
    for week in weeks:
        standings = season[season["through_week"] == week].set_index("roster_id")
        ladder = []
        for r in power[power["week"] == week].sort_values("rank").itertuples():
            s = standings.loc[r.roster_id]
            parts = []
            for c in COMPONENTS:
                contribution = getattr(r, f"contrib_{c}")
                gap = contribution - 50 * weights[c]
                parts.append({"label": COMPONENT_LABELS[c], "weight": f"{round(weights[c] * 100)}%",
                              "detail": _component_detail(c, getattr(r, c), s, min(recent_weeks, week)),
                              "score": one_dp(contribution), "gap": signed(gap), "bar": bar(gap, part_axis)})
            ladder.append({
                "rank": int(r.rank), "roster_id": int(r.roster_id),
                "team": teams.at[r.roster_id, "team_name"], "user": teams.at[r.roster_id, "display_name"],
                "move": movement(r.rank_change),
                "record": f"{record(s.wins, s.losses, s.ties, show_ties)}, "
                          f"all-play {record(s.allplay_wins, s.allplay_losses, s.allplay_ties, show_allplay_ties)}",
                "score": one_dp(r.power_score), "gap": signed(r.power_score - 50), "bar": bar(r.power_score - 50, power_axis),
                "parts": parts,
            })
        highlight = ladder[0]["roster_id"]  # the #1 team, matching the pylon #1 on the ladder, until the viewer taps another
        sections = []
        luck_rows = standings.reset_index()
        played = [w for w in regular_weeks if w <= week]
        if played and luck_rows["expected_wins"].notna().all():
            sections.append(charts.luck_chart(luck_rows, names, highlight, week, played[-1]))
        so_far = lineups[lineups["week"] <= week]
        if not so_far.empty:
            sections.append(charts.efficiency_chart(so_far, standings["efficiency"], names, highlight, week))
        scores = team_weeks.loc[team_weeks["week"] <= week, ["roster_id", "week", "points"]]
        later = [charts.consistency_chart(scores, standings, names, highlight, week),
                 charts.schedule_chart(standings, names, highlight, week),
                 charts.rank_history_chart(power.loc[power["week"] <= week, ["week", "roster_id", "rank"]], names, highlight, week)]
        sections += [section for section in later if section]  # a chart without data yet is left out
        for section in sections:
            section["figure_json"] = theme.to_script_json(section["figure"])
        views.append({"week": week, "title": f"Week {week} power rankings", "ladder": ladder,
                      "awards": _award_tiles(awards[awards["week"] == week], teams), "charts": sections})

    chart_theme = theme.to_script_json({"layout": theme.base_layout(), "config": theme.CONFIG, "tokens": theme.TOKENS})
    return {"league_name": run["league_name"], "updated": updated_text(run["finished_at"]),
            "latest": views[-1], "earlier": views[:-1], "weeks": weeks,
            "plotly_cdn": theme.PLOTLY_CDN, "chart_theme": chart_theme}


def _component_detail(component, raw, standings, recent):
    if component == "season_scoring":
        return f"{one_dp(raw)} points a week"
    if component == "recent_form":
        return f"{one_dp(raw)} points a week, " + ("this week" if recent == 1 else f"last {recent} weeks")
    if component == "roster_strength":
        return f"{one_dp(raw)} points a week with the best lineup"
    games = int(standings.h2h_wins + standings.h2h_losses + standings.h2h_ties)
    text = f"Won {int(standings.h2h_wins)} of {games}"
    return text + (f", tied {int(standings.h2h_ties)}" if standings.h2h_ties else "")


def _award_tiles(week_awards, teams):
    """One tile per award, in the table's (config) order; co-winners share a tile."""
    tiles = []
    for award, rows in week_awards.groupby("award", sort=False):
        tiles.append({"name": rows["award_name"].iloc[0], "value": award_value(award, rows["value"].iloc[0]),
                      "winners": [{"team": teams.at[r.roster_id, "team_name"], "caption": r.caption} for r in rows.itertuples()]})
    return tiles


# --- Rendering and files --------------------------------------------------------------------

def render(view):
    env = Environment(loader=PackageLoader("sleeper_dash.dashboard", "templates"), autoescape=True,
                      trim_blocks=True, lstrip_blocks=True)
    html = env.get_template("index.html.j2").render(**view)
    return re.sub(r"\n[ \t]+", "\n", html)  # drop template indentation: about 15% of the page, invisible in HTML


def read_run_record(path=None):
    from sleeper_dash.pipeline import RUN_RECORD_PATH

    path = Path(path or RUN_RECORD_PATH)
    if not path.exists():
        raise DashboardError(f"{path} is missing, so the page can't say when it was updated. "
                             "Run `python -m sleeper_dash.pipeline` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def build_site(out_dir=None, processed_dir=None, run_path=None):
    """Read the saved tables and run record, write site/index.html, and return (path, view)."""
    from sleeper_dash.config import load_config
    from sleeper_dash.validate import load_tables

    view = build_view(load_tables(processed_dir, names=TABLES), read_run_record(run_path), load_config().metrics["power"])
    out_dir = Path(out_dir or SITE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(render(view), encoding="utf-8")
    return path, view


def main():
    try:
        path, view = build_site()
    except (DashboardError, FileNotFoundError) as error:
        raise SystemExit(f"DASHBOARD NOT BUILT: {error}")
    size = path.stat().st_size
    weeks = view["weeks"]
    print(f"Dashboard built: {path.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"  Weeks:    {weeks[0]}–{weeks[-1]} (opens on week {weeks[-1]}; the others are in the page for the week selector)")
    every = [view["latest"], *view["earlier"]]
    print(f"  Sections: power rankings; weekly awards in {sum(bool(v['awards']) for v in every)} of {len(weeks)} weeks; "
          f"charts in the latest week: {', '.join(c['key'] for c in view['latest']['charts']) or 'none'}")
    print(f"  Updated:  {view['updated']}")
    print(f"  Size:     {size / 1024:.0f} KB of the 1 MB budget ({math.ceil(size / len(weeks) / 1024)} KB a week)")
