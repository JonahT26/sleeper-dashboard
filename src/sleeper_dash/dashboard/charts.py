"""The dashboard's charts as plain Plotly figure dicts, built from theme.py (docs/UI_GUIDE.md "Charts").

Each function returns a chart section for one week: title, subtitle, a one-sentence text summary
(read by screen readers, and shown if Plotly can't load), and the figure. Colours are theme
tokens; the page fills them in. Teams carry their roster_id in `meta` so the page can move the
highlight to whichever team the viewer taps. Pure functions: tables in, dicts out.
"""

import html
import math

from sleeper_dash.dashboard import theme

MINUS = "−"


def _signed(value):
    text = f"{abs(value):.1f}"
    return text if text == "0.0" else ("+" if value > 0 else MINUS) + text


def _wins(value):
    """3 wins, 1 win, 2.5 wins (a tie is half a win)."""
    number = f"{value:g}"
    return f"{number} win" if value == 1 else f"{number} wins"


def _plotly_text(names):
    """Team names escaped for Plotly hover text and annotations, which read a little HTML (<b>, <br>)."""
    return {roster: html.escape(name, quote=False) for roster, name in names.items()}


def _team_label(text, roster, **position):
    """A team-name annotation the viewer can tap to highlight that team (charts.js reads `name`)."""
    return {"text": text, "name": str(roster), "captureevents": True, "showarrow": False, "bgcolor": "@page",  # lines pass behind
            "font": {"size": theme.LABEL_SIZE, "color": "@ink"}, **position}


def _row_labels(name, value, row, roster):
    """For one-row-per-team charts: the team name above the row's left end, a value above its right end."""
    return [_team_label(name, roster, x=0, xref="paper", xanchor="left", y=row, yanchor="bottom", yshift=5),
            {"text": value, "x": 1, "xref": "paper", "xanchor": "right", "y": row, "yanchor": "bottom", "yshift": 5,
             "showarrow": False, "font": {"size": theme.LABEL_SIZE, "color": "@muted"}}]


def _rows(order):
    """Row positions for a one-row-per-team chart: the first team in `order` at the top."""
    n = len(order)
    return [n - 1 - i for i in range(n)]


def _nice(value, steps=(1, 2, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50)):
    return next((s for s in steps if s >= value - 1e-9), steps[-1])


def luck_chart(standings, names, highlight, week, last_regular_week):
    """Scatter of expected wins (x) vs actual wins (y), with the line where they're equal (METRICS_SPEC.md section 2).

    standings: metrics_season rows for this week (actual_wins, expected_wins, luck; regular season only).
    last_regular_week: the last regular-season week up to this one (luck is frozen after it).
    """
    rows = standings.sort_values("roster_id")
    top = max(rows["actual_wins"].max(), rows["expected_wins"].max(), 1)
    end = math.ceil(top) + 0.5
    ticks = 1 if end <= 12 else 2

    shown = _plotly_text(names)
    hover = [f"{shown[r.roster_id]}<br>{_wins(r.actual_wins)}, {r.expected_wins:.1f} expected, luck {_signed(r.luck)}"
             for r in rows.itertuples()]
    rosters = rows["roster_id"].tolist()
    data = [
        {"type": "scatter", "mode": "lines", "x": [0, end], "y": [0, end], "hoverinfo": "skip",
         "line": {"color": "@muted", "width": 1, "dash": "dot"}},
        {"type": "scatter", "mode": "markers", "x": rows["expected_wins"].round(3).tolist(), "y": rows["actual_wins"].tolist(),
         "marker": {"size": 10, "color": [theme.team_colour(r, highlight) for r in rosters], "line": {"width": 1.5, "color": "@page"}},
         "customdata": rosters, "hovertext": hover, "hovertemplate": "%{hovertext}<extra></extra>",
         "meta": {"rosters": rosters, "paint": ["marker.color"]}},
    ]
    axis = {"range": [-0.3, end], "dtick": ticks, "tick0": 0}
    # Equal scales keep the line at 45°; constraining both axes shrinks the plot to a square instead of
    # widening the range (which would show impossible negative wins on a wide screen).
    layout = {"xaxis": {**axis, "title": {"text": "Expected wins"}, "constrain": "domain", "constraintoward": "left"},
              "yaxis": {**axis, "title": {"text": "Actual wins"}, "scaleanchor": "x", "constrain": "domain"}}
    labels = [{"x": round(r.expected_wins, 3), "y": r.actual_wins, "text": names[r.roster_id], "roster": r.roster_id}
              for r in rows.itertuples()]

    luckiest, unluckiest = rows.loc[rows["luck"].idxmax()], rows.loc[rows["luck"].idxmin()]
    when = f"through week {week}" if last_regular_week == week else f"regular season, through week {last_regular_week}"
    summary = (f"Luck {when}. Luckiest: {names[luckiest.roster_id]}, {_wins(luckiest.actual_wins)} from "
               f"{luckiest.expected_wins:.1f} expected ({_signed(luckiest.luck)}). Unluckiest: {names[unluckiest.roster_id]}, "
               f"{_wins(unluckiest.actual_wins)} from {unluckiest.expected_wins:.1f} expected ({_signed(unluckiest.luck)}).")
    return {
        "key": "luck", "id": f"luck-{week}",
        "title": "Luck: actual wins vs expected wins",
        "subtitle": f"Above the line: more wins than your scores earned. Below it: fewer. {when[0].upper() + when[1:]}.",
        "summary": summary,
        "figure": {"data": data, "layout": layout, "labels": labels, "highlight": highlight, "height": {"phone": 340, "desktop": 380}},
    }


def efficiency_chart(lineups, efficiency, names, highlight, week):
    """Dot plot of points scored vs best possible points per week, one row per team, sorted by season efficiency.

    lineups: lineups_optimal rows for weeks 1…week. efficiency: metrics_season.efficiency by roster_id for this week
    (Σ actual ÷ Σ optimal, METRICS_SPEC.md section 3).
    """
    totals = lineups.groupby("roster_id").agg(actual=("actual_points", "sum"), optimal=("optimal_points", "sum"), weeks=("week", "nunique"))
    totals["actual_pw"] = totals["actual"] / totals["weeks"]
    totals["optimal_pw"] = totals["optimal"] / totals["weeks"]
    totals["efficiency"] = efficiency.reindex(totals.index)
    order = totals.reset_index().sort_values(["efficiency", "roster_id"], ascending=[False, True]).reset_index(drop=True)
    n = len(order)
    order["row"] = [n - 1 - i for i in range(n)]  # most efficient at the top

    shown = _plotly_text(names)
    data, annotations = [], []
    for r in order.itertuples():
        colour = theme.team_colour(r.roster_id, highlight)
        data.append({"type": "scatter", "mode": "lines", "x": [round(r.actual_pw, 2), round(r.optimal_pw, 2)], "y": [r.row, r.row],
                     "hoverinfo": "skip", "line": {"color": colour, "width": 2}, "meta": {"roster": r.roster_id, "paint": ["line.color"]}})
        annotations += _row_labels(shown[r.roster_id], f"{round(r.efficiency * 100)}%", r.row, r.roster_id)
    rosters = order["roster_id"].tolist()
    hover = [f"{shown[r.roster_id]}<br>{r.actual_pw:.1f} a week scored, {r.optimal_pw:.1f} best possible ({round(r.efficiency * 100)}%)"
             for r in order.itertuples()]
    colours = [theme.team_colour(rid, highlight) for rid in rosters]
    common = {"type": "scatter", "mode": "markers", "y": order["row"].tolist(), "customdata": rosters,
              "hovertext": hover, "hovertemplate": "%{hovertext}<extra></extra>"}
    data.append({**common, "x": order["actual_pw"].round(2).tolist(),
                 "marker": {"size": 10, "color": colours, "line": {"width": 0}},
                 "meta": {"rosters": rosters, "paint": ["marker.color"]}})
    data.append({**common, "x": order["optimal_pw"].round(2).tolist(),
                 "marker": {"size": 10, "color": "@page", "line": {"width": 2, "color": colours}},
                 "meta": {"rosters": rosters, "paint": ["marker.line.color"]}})

    low, high = order["actual_pw"].min(), order["optimal_pw"].max()
    layout = {
        "xaxis": {"title": {"text": "Points per week"}, "range": [math.floor(low / 5) * 5 - 5, math.ceil(high / 5) * 5 + 5]},
        "yaxis": {"range": [-0.6, n - 0.2], "dtick": 1, "tick0": 0, "showticklabels": False},
        "annotations": annotations, "margin": {"t": 4},
    }
    best, worst = order.iloc[0], order.iloc[-1]
    summary = (f"Lineup efficiency through week {week}. Most efficient: {names[best.roster_id]}, {round(best.efficiency * 100)}% "
               f"of best possible points. Least: {names[worst.roster_id]}, {round(worst.efficiency * 100)}%.")
    return {
        "key": "efficiency", "id": f"efficiency-{week}",
        "title": "Lineup efficiency: points scored vs best possible",
        "subtitle": "Solid dot: points scored a week. Open dot: the best lineup the roster allowed. "
                    f"Sorted by the share of best possible points scored, through week {week}.",
        "summary": summary,
        "figure": {"data": data, "layout": layout, "labels": [], "highlight": highlight, "height": {"phone": 30 * n + 70, "desktop": 30 * n + 70}},
    }


def consistency_chart(scores, standings, names, highlight, week):
    """Strip plot of each team's weekly scores, one row per team, steadiest on top (METRICS_SPEC.md section 4).

    scores: team_weeks rows for weeks 1…week (roster_id, week, points). standings: metrics_season rows for this
    week, indexed by roster_id (volatility, floor, ceiling). Returns None until volatility exists (min_weeks).
    """
    if standings["volatility"].isna().all():
        return None
    order = standings.reset_index().sort_values(["volatility", "roster_id"]).reset_index(drop=True)
    order["row"] = _rows(order)
    row_of = order.set_index("roster_id")["row"]
    shown = _plotly_text(names)

    band_x, band_y, annotations = [], [], []
    for r in order.itertuples():
        band_x += [r.floor, r.ceiling, None]
        band_y += [r.row, r.row, None]
        annotations += _row_labels(shown[r.roster_id], f"±{r.volatility:.1f}", r.row, r.roster_id)
    points = scores.sort_values(["roster_id", "week"])
    rosters = points["roster_id"].tolist()
    median = float(points["points"].median())
    data = [
        {"type": "scatter", "mode": "lines", "x": band_x, "y": band_y, "hoverinfo": "skip", "line": {"color": "@hash", "width": 8}},
        {"type": "scatter", "mode": "markers", "x": points["points"].round(2).tolist(), "y": points["roster_id"].map(row_of).tolist(),
         "marker": {"size": 8, "opacity": 0.9, "color": [theme.team_colour(r, highlight) for r in rosters], "line": {"width": 1, "color": "@page"}},
         "customdata": rosters, "hovertext": [f"{shown[r.roster_id]}<br>Week {r.week}: {r.points:.1f}" for r in points.itertuples()],
         "hovertemplate": "%{hovertext}<extra></extra>", "meta": {"rosters": rosters, "paint": ["marker.color"]}},
    ]
    n = len(order)
    low, high = points["points"].min(), points["points"].max()
    annotations.append({"text": f"League median {median:.1f}", "x": median, "y": 1, "yref": "paper", "yanchor": "bottom",
                        "showarrow": False, "font": {"size": theme.LABEL_SIZE, "color": "@muted"}})
    layout = {
        "xaxis": {"title": {"text": "Points in a week"}, "range": [math.floor(low / 10) * 10 - 5, math.ceil(high / 10) * 10 + 5]},
        "yaxis": {"range": [-0.6, n - 0.2], "dtick": 1, "tick0": 0, "showticklabels": False},
        "shapes": [{"type": "line", "x0": median, "x1": median, "y0": 0, "y1": 1, "yref": "paper",
                    "line": {"color": "@muted", "width": 1, "dash": "dot"}}],
        "annotations": annotations, "margin": {"t": 24},
    }
    steady, swingy = order.iloc[0], order.iloc[-1]
    return {
        "key": "consistency", "id": f"consistency-{week}",
        "title": "Consistency: weekly scores",
        "subtitle": "Each dot is one week's score; the shaded bar runs from a typical bad week to a typical good week. "
                    "Steadiest teams on top. The ± number is how much a team's score swings against the league each week.",
        "summary": f"Consistency through week {week}. Steadiest: {names[steady.roster_id]} (±{steady.volatility:.1f} points). "
                   f"Swingiest: {names[swingy.roster_id]} (±{swingy.volatility:.1f}). League median score {median:.1f}.",
        "figure": {"data": data, "layout": layout, "labels": [], "highlight": highlight, "height": {"phone": 30 * n + 90, "desktop": 30 * n + 90}},
    }


def schedule_chart(standings, names, highlight, week):
    """Strength of schedule, played and remaining, as bars left or right of the league average (METRICS_SPEC.md section 5).

    standings: metrics_season rows for this week, indexed by roster_id. Returns None until SOS exists (min_weeks).
    The remaining panel is left out once the regular season is over.
    """
    if standings["sos_played"].isna().all():
        return None
    order = standings.reset_index().sort_values(["sos_played", "roster_id"], ascending=[False, True]).reset_index(drop=True)
    order["row"] = _rows(order)
    n, rows, rosters = len(order), order["row"].tolist(), order["roster_id"].tolist()
    shown = _plotly_text(names)
    remaining = order["sos_remaining"]
    has_remaining = bool(remaining.notna().any())
    all_average = has_remaining and bool((remaining.abs() < 0.05).all())
    two_panels = has_remaining and not all_average  # a panel of zero-length bars says nothing; a note says it better

    biggest = max(order["sos_played"].abs().max(), remaining.abs().max() if two_panels else 0, 1)
    tick = max([t for t in (2, 5, 10, 15, 20, 25, 30, 40, 50) if t <= biggest] or [2])
    reach = biggest * 1.45  # room past the longest bar for its value
    colours = [theme.team_colour(r, highlight) for r in rosters]

    def bars(values, axis_name, label):
        return {"type": "bar", "orientation": "h", "x": values.round(2).tolist(), "y": rows, "xaxis": axis_name, "yaxis": "y",
                "marker": {"color": list(colours)}, "width": 0.36, "text": [_signed(v) for v in values], "textposition": "outside",
                "cliponaxis": False, "textfont": {"size": theme.LABEL_SIZE, "color": "@ink"}, "customdata": rosters,
                "hovertext": [f"{shown[r]}<br>{label}: {_signed(v)} points a week vs average" for r, v in zip(rosters, values)],
                "hovertemplate": "%{hovertext}<extra></extra>", "meta": {"rosters": rosters, "paint": ["marker.color"]}}

    def zero_line(axis_name):
        return {"type": "line", "x0": 0, "x1": 0, "xref": axis_name, "y0": 0, "y1": 1, "yref": "paper", "line": {"color": "@muted", "width": 1}}

    played_domain = [0, 0.47] if two_panels else [0, 1]
    axis = {"range": [-reach, reach], "tickvals": [-tick, 0, tick], "ticktext": [f"{MINUS}{tick:g}", "0", f"+{tick:g}"],
            "title": {"text": "Points a week vs average"}}
    data, shapes = [bars(order["sos_played"], "x", "Played")], [zero_line("x")]
    layout = {"xaxis": {**axis, "domain": played_domain},
              "yaxis": {"range": [-0.6, n - 0.2], "dtick": 1, "tick0": 0, "showticklabels": False}, "margin": {"t": 26}}
    titles = [("Played", sum(played_domain) / 2)]
    if two_panels:
        layout["xaxis2"] = theme.merge(theme.axis(gridlines=False), {**axis, "domain": [0.53, 1], "anchor": "y"})
        titles.append(("Remaining", 0.765))
        data.append(bars(remaining, "x2", "Remaining"))
        shapes.append(zero_line("x2"))
    annotations = [{"text": f"<b>{text}</b>", "x": x, "xref": "paper", "y": 1, "yref": "paper", "yanchor": "bottom", "yshift": 4,
                    "showarrow": False, "font": {"size": 13, "color": "@ink"}} for text, x in titles]
    for r in order.itertuples():
        annotations.append(_team_label(shown[r.roster_id], r.roster_id, x=0, xref="paper", xanchor="left", y=r.row, yanchor="bottom", yshift=6))
    layout["annotations"], layout["shapes"] = annotations, shapes

    hardest, easiest = order.iloc[0], order.iloc[-1]
    summary = (f"Strength of schedule through week {week}. Toughest so far: {names[hardest.roster_id]} ({_signed(hardest.sos_played)} points "
               f"a week). Easiest: {names[easiest.roster_id]} ({_signed(easiest.sos_played)}).")
    if all_average:
        still_to_come = " Still to come: every team's remaining opponents are exactly average (0.0)."
        summary += still_to_come
    elif has_remaining:
        tough = order.loc[remaining.idxmax()]
        still_to_come = ""
        summary += f" Toughest still to come: {names[tough.roster_id]} ({_signed(tough.sos_remaining)})."
    else:
        still_to_come = ""
    scope = "Games played so far and still to come" if two_panels else ("Games played so far" if has_remaining else "Regular-season games")
    return {
        "key": "schedule", "id": f"schedule-{week}",
        "title": "Strength of schedule: how strong opponents are",
        "subtitle": "Opponents' average points a week compared with an average schedule. Right of the line: tougher; left: easier. "
                    f"{scope}, through week {week}.{still_to_come}",
        "summary": summary,
        "figure": {"data": data, "layout": layout, "labels": [], "highlight": highlight, "height": {"phone": 34 * n + 90, "desktop": 32 * n + 90}},
    }


def rank_history_chart(rankings, names, highlight, week):
    """Bump chart of power rank by week, weeks 1…week (METRICS_SPEC.md section 6). Returns None before week 2."""
    weeks = sorted(int(w) for w in rankings["week"].unique())
    if len(weeks) < 2:
        return None
    shown = _plotly_text(names)
    latest = rankings[rankings["week"] == week].set_index("roster_id")["rank"]
    n = len(latest)
    data, annotations = [], []
    for roster, g in rankings.sort_values("week").groupby("roster_id"):
        roster = int(roster)
        colour = theme.team_colour(roster, highlight)
        data.append({"type": "scatter", "mode": "lines+markers", "x": g["week"].tolist(), "y": g["rank"].tolist(),
                     "line": {"color": colour, "width": 2}, "marker": {"size": 6, "color": colour},
                     "customdata": [roster] * len(g), "hovertext": [f"{shown[roster]}<br>Week {w}: #{k}" for w, k in zip(g["week"], g["rank"])],
                     "hovertemplate": "%{hovertext}<extra></extra>", "meta": {"roster": roster, "paint": ["line.color", "marker.color"]}})
        annotations.append(_team_label(shown[roster], roster, x=week, y=int(latest[roster]), xanchor="left", xshift=8))
    longest = max(len(names[r]) for r in latest.index)
    layout = {
        "xaxis": {"title": {"text": "Week"}, "range": [weeks[0] - 0.2, week + 0.2], "dtick": 1},
        "yaxis": {"title": {"text": "Power rank"}, "range": [n + 0.5, 0.5], "dtick": 1},
        "annotations": annotations, "margin": {"r": min(170, 6 * longest + 16)},
    }
    first = rankings[rankings["week"] == weeks[0]].set_index("roster_id")["rank"]
    moved = (first - latest).sort_values(kind="stable")
    riser, faller = moved.index[-1], moved.index[0]
    summary = (f"Power rankings, weeks {weeks[0]} to {week}. Biggest riser: {names[riser]}, from #{first[riser]} to #{latest[riser]}. "
               f"Biggest faller: {names[faller]}, from #{first[faller]} to #{latest[faller]}.")
    return {
        "key": "rank_history", "id": f"rank-history-{week}",
        "title": "Rank history: power rankings week by week",
        "subtitle": "Each line is one team's power rank after each week. Tap a line or a name to follow that team.",
        "summary": summary, "wide": True,
        "figure": {"data": data, "layout": layout, "labels": [], "highlight": highlight, "height": {"phone": 26 * n + 90, "desktop": 30 * n + 90}},
    }
