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
        annotations.append({"text": shown[r.roster_id], "x": 0, "xref": "paper", "xanchor": "left", "y": r.row, "yanchor": "bottom",
                            "yshift": 5, "showarrow": False, "font": {"size": theme.LABEL_SIZE, "color": "@ink"}})
        annotations.append({"text": f"{round(r.efficiency * 100)}%", "x": 1, "xref": "paper", "xanchor": "right", "y": r.row,
                            "yanchor": "bottom", "yshift": 5, "showarrow": False, "font": {"size": theme.LABEL_SIZE, "color": "@muted"}})
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
