"""Build the static dashboard page, site/index.html, from the saved tables (docs/UI_GUIDE.md).

Run with:  python -m sleeper_dash.dashboard   (after python -m sleeper_dash.pipeline)

Python does all the formatting: build_view turns the tables into plain values and strings
for every completed week, and one Jinja2 template draws them. The latest week is drawn
straight into the page, so it shows without JavaScript; every other week is drawn into a
<template> block that the week selector swaps in, so switching weeks needs no network call.
Each week shows rankings, records, and metrics as of that week. A section with no data for
a week is left out entirely (owner decision, no placeholder).
"""

import gzip
import json
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml
from jinja2 import Environment, PackageLoader

from sleeper_dash.config import PROJECT_ROOT
from sleeper_dash.dashboard import bracket, charts, explainer, history, theme

SITE_DIR = PROJECT_ROOT / "site"
TABLES = ["teams", "team_weeks", "power_rankings", "metrics_season", "lineups_optimal", "awards", "playoff_odds",
          "managers", "winners_bracket"]
EASTERN = ZoneInfo("America/New_York")
# The weekly workflow's schedule is the one source for "next update due" (UI_GUIDE.md "Status bar").
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "weekly.yml"
UPCOMING_DAYS = 120  # scheduled updates listed in the page, counted from the run; the viewer's browser picks the next one

# Ladder breakdown rows, in display order (METRICS_SPEC.md section 6; labels from UI_GUIDE.md Ladder row).
COMPONENTS = ["season_scoring", "recent_form", "roster_strength", "results"]
COMPONENT_LABELS = {"season_scoring": "Season scoring", "recent_form": "Recent form",
                    "roster_strength": "Roster strength", "results": "Head-to-head wins"}
# Round axis ends for the bars, so one fixed scale serves every week of the season.
POWER_AXIS_STEPS = [5, 10, 15, 20, 25, 30, 40, 50]
PART_AXIS_STEPS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20]
SEEDS = [1, 2, 3, 4, 5, 6]  # playoff_odds seed columns (METRICS_SPEC.md section 8: the verified 6-team format)
BYES = 2
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


def chance(p, certain=False):
    """A probability as a whole percentage. Unless it is certain, a value that rounds to 0% or 100% says "<1%" or ">99%"
    (METRICS_SPEC.md section 8, Display): a simulation that never saw something doesn't prove it can't happen."""
    if certain:
        return f"{round(p * 100)}%"
    whole = round(p * 100)
    if whole == 0:
        return "<1%"
    if whole == 100:
        return ">99%"
    return f"{whole}%"


def updated_text(finished_at):
    """'Tue Oct 6, 9:00 AM ET' from the pipeline's ISO timestamp."""
    when = datetime.fromisoformat(finished_at).astimezone(EASTERN)
    return f"{when:%a %b} {when.day}, {when.hour % 12 or 12}:{when:%M} {'AM' if when.hour < 12 else 'PM'} ET"


# --- Freshness: when the next update is due -------------------------------------------------

def workflow_schedule(path=None):
    """[(minute, hour, cron weekdays, time zone)] for each scheduled run in the weekly workflow.

    Reads the cron lines GitHub runs, so the page can't name a different time. Only the plain
    "minute hour * * weekdays" form is understood; anything else stops the build with a clear message.
    """
    path = Path(path or WORKFLOW_PATH)
    workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    triggers = workflow.get("on", workflow.get(True)) or {}  # YAML 1.1 reads a bare `on:` key as true
    schedule = []
    for entry in triggers.get("schedule") or []:
        fields = str(entry.get("cron", "")).split()
        days = fields[4].split(",") if len(fields) == 5 else []
        if len(fields) != 5 or fields[2:4] != ["*", "*"] or not all(f.isdigit() for f in fields[:2] + days):
            raise DashboardError(f"Can't read the schedule {entry.get('cron')!r} in {path.name}: the page understands "
                                 "only 'minute hour * * weekdays', e.g. '17 12 * * 2'.")
        schedule.append((int(fields[0]), int(fields[1]), {int(d) % 7 for d in days}, ZoneInfo(entry.get("timezone", "UTC"))))
    if not schedule:
        raise DashboardError(f"{path.name} has no schedule, so the page can't say when the next update is due.")
    return schedule


def upcoming_updates(schedule, after, days=UPCOMING_DAYS):
    """Every scheduled run in the `days` after `after` (an aware datetime), oldest first.

    Each is {"at": UTC ISO time for the browser to compare, "text": "Tue Oct 6, 12:17 PM ET"}.
    Times are wall-clock in the schedule's time zone, so they follow daylight saving as GitHub does.
    """
    runs = set()
    for minute, hour, weekdays, zone in schedule:
        first = after.astimezone(zone).date()
        for offset in range(days + 1):
            day = first + timedelta(days=offset)
            when = datetime.combine(day, time(hour, minute), tzinfo=zone)
            if day.isoweekday() % 7 in weekdays and after < when <= after + timedelta(days=days):
                runs.add(when.astimezone(timezone.utc))
    return [{"at": when.isoformat(timespec="seconds"), "text": updated_text(when.isoformat())} for when in sorted(runs)]


def freshness(run, stale_after_days, schedule):
    """What the page needs to warn about stale data: the threshold and the scheduled updates after this run."""
    return {"stale_after_days": stale_after_days,
            "next_updates": upcoming_updates(schedule, datetime.fromisoformat(run["finished_at"]))}


# --- View model -----------------------------------------------------------------------------

def build_view(tables, run, params, fresh=None):
    """Everything the template needs, as plain values and formatted strings. Pure: no file access.

    tables: teams, team_weeks, power_rankings, metrics_season, lineups_optimal, awards, playoff_odds, managers,
    winners_bracket. run: the pipeline's run record.
    params: config.yaml metrics (power weights and windows for the ladder; every weight and threshold for "How this works").
    fresh: freshness() for the stale-data line; build_site always passes it. Without it the page has no stale-data line.
    The saved tables hold every season (Phase 5); the page shows the run's season only, except the History
    section, which summarises every finished season.
    """
    past = history.history_view(tables, run["season"])
    tables = {name: table[table["season"] == run["season"]].reset_index(drop=True) if "season" in table.columns else table
              for name, table in tables.items()}
    teams = tables["teams"].set_index("roster_id")
    power, season, awards = tables["power_rankings"], tables["metrics_season"], tables["awards"]
    lineups, team_weeks = tables["lineups_optimal"], tables["team_weeks"]
    names = teams["team_name"].to_dict()
    regular_weeks = sorted(int(w) for w in team_weeks.loc[~team_weeks["is_playoff"].astype(bool), "week"].unique())
    weights, recent_weeks = params["power"]["weights"], params["power"]["recent_weeks"]
    if not run.get("league"):
        raise DashboardError("The pipeline run record has no league settings. Run `python -m sleeper_dash.pipeline` again.")
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
        odds = tables.get("playoff_odds")
        odds_view = None
        if odds is not None and (odds["week"] == week).any():
            odds_view = _odds_section(odds[odds["week"] == week], names, params, run["league"])
        playoffs = bracket.bracket_view(tables.get("winners_bracket"), team_weeks, names, run["league"], week)
        views.append({"week": week, "title": f"Week {week} power rankings", "ladder": ladder, "odds": odds_view, "bracket": playoffs,
                      "awards": _award_tiles(awards[awards["week"] == week], teams), "charts": sections})

    chart_theme = theme.to_script_json({"layout": theme.base_layout(), "config": theme.CONFIG, "tokens": theme.TOKENS})
    stale = fresh and {"after_days": fresh["stale_after_days"], "next_updates_json": theme.to_script_json(fresh["next_updates"]),
                       "final": bool(run["league"].get("season_complete"))}  # season over: "Final rankings", no next update
    return {"league_name": run["league_name"], "season": run["season"], "updated": updated_text(run["finished_at"]), "updated_at": run["finished_at"],
            "stale": stale, "latest": views[-1], "earlier": views[:-1], "weeks": weeks, "history": past,
            "plotly_cdn": theme.PLOTLY_CDN, "chart_theme": chart_theme,
            "how_it_works": explainer.sections(params, run["league"])}  # owner-approved copy, numbers from config.yaml


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


def _odds_section(rows, names, params, league):
    """Playoff odds for one week: one row per team, most likely playoff team first (METRICS_SPEC.md section 8).

    "Clinched" and "Out" are shown only when proved. After the last regular-season week the standings are final,
    so playoff and bye odds are certain; title odds are always simulated, and certain only for a team that is out.
    """
    sims = params["playoff_odds"]["simulations"]
    final = int(rows["week"].iloc[0]) == league["playoff_week_start"] - 1
    places = league["playoff_teams"]
    ordered = rows.sort_values(["p_playoffs", "p_bye", "avg_wins", "roster_id"], ascending=[False, False, False, True])
    table = []
    for r in ordered.itertuples():
        playoffs = "Clinched" if r.clinched else "Out" if r.out else chance(r.p_playoffs)
        table.append({
            "roster_id": int(r.roster_id), "team": names[r.roster_id],
            "record": f"{r.avg_wins:.1f}{EN_DASH}{r.avg_losses:.1f}",
            "playoffs": playoffs, "bar": f"{r.p_playoffs * 100:.1f}",
            "bye": chance(r.p_bye, certain=final or r.out), "title": chance(r.p_title, certain=r.out),
            "seeds": [{"text": chance(getattr(r, f"p_seed_{s}"), certain=final or r.out),
                       "shade": f"{getattr(r, f'p_seed_{s}'):.2f}"} for s in SEEDS],
        })
    if final:
        subtitle = (f"The regular season is over and the top {places} are in; the top {BYES} have a first-round bye. "
                    f"Title odds come from {sims:,} simulations of the playoffs.")
    else:
        subtitle = (f"Chances from {sims:,} simulations of the rest of the season. The top {places} make the playoffs, "
                    f"and the top {BYES} get a first-round bye.")
    return {"subtitle": subtitle, "rows": table, "seeds": SEEDS}


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


def build_site(out_dir=None, processed_dir=None, run_path=None, workflow_path=None):
    """Read the saved tables, run record, config, and workflow schedule; write site/index.html; return (path, view)."""
    from sleeper_dash.config import load_config
    from sleeper_dash.validate import load_tables

    config, run = load_config(), read_run_record(run_path)
    fresh = freshness(run, config.dashboard["stale_after_days"], workflow_schedule(workflow_path))
    view = build_view(load_tables(processed_dir, names=TABLES), run, config.metrics, fresh)
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
    upcoming = json.loads(view["stale"]["next_updates_json"])
    print(f"  Stale:    the page warns if this is more than {view['stale']['after_days']} days old; "
          f"next scheduled update {upcoming[0]['text'] if upcoming else 'none listed'}")
    compressed = len(gzip.compress(path.read_bytes()))  # the budget counts what a visitor downloads (owner, 2026-10-02)
    print(f"  Size:     {compressed / 1024:.0f} KB compressed, of the 1 MB budget ({size / 1024:.0f} KB before compression)")
