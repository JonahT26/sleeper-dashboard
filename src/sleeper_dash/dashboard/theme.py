"""The one shared Plotly theme (docs/UI_GUIDE.md "Charts"). Never style a chart anywhere else.

Colours are written as design-token names such as "@pylon" or "@bar". The page's JavaScript
replaces each one with the value of the matching CSS custom property (--pylon, --bar, ...) when
it draws a chart, so charts follow light and dark mode and UI_GUIDE.md's colour table stays the
only place colours are defined. resolve_tokens does the same in Python, for tests.

Rules carried here: highlight one team in pylon and draw everyone else in the default bar grey;
direct labels instead of legends; horizontal gridlines only, thin, in hash; no chart borders or
background fills; tooltips with the team name and formatted value only; no mode bar; no zooming
or dragging (so a phone can scroll past a chart); responsive; Plotly loaded from its CDN.
"""

import copy
import json

PLOTLY_JS_VERSION = "4.1.1"  # the plotly.js that matches the installed Python plotly (plotly.offline.get_plotlyjs_version())
PLOTLY_CDN = f"https://cdn.plot.ly/plotly-basic-{PLOTLY_JS_VERSION}.min.js"

HIGHLIGHT = "@pylon"
OTHERS = "@bar"
TOKENS = ["page", "ink", "muted", "hash", "bar", "pylon"]  # every token a chart may use; each is a CSS custom property

BODY_FONT = "Barlow, system-ui, -apple-system, 'Segoe UI', sans-serif"
LABEL_SIZE = 12

CONFIG = {"displayModeBar": False, "responsive": True, "scrollZoom": False, "doubleClick": False, "showTips": False}


def axis(gridlines):
    """Axis style for every chart axis (a second panel's axis uses it too)."""
    return {
        "showgrid": gridlines, "gridcolor": "@hash", "gridwidth": 1, "zeroline": False, "showline": False,
        "ticks": "", "tickfont": {"color": "@muted", "size": 13}, "title": {"font": {"color": "@muted", "size": 13}, "standoff": 8},
        "fixedrange": True, "automargin": True,
    }


def base_layout():
    """Layout every chart starts from. Charts add their own axes ranges, titles, and shapes on top."""
    return {
        "font": {"family": BODY_FONT, "size": 13, "color": "@ink"},
        "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
        "margin": {"l": 8, "r": 8, "t": 8, "b": 8, "pad": 0},
        "showlegend": False, "dragmode": False, "hovermode": "closest",
        "hoverlabel": {"bgcolor": "@page", "bordercolor": "@hash", "font": {"family": BODY_FONT, "size": 13, "color": "@ink"}},
        "xaxis": axis(gridlines=False),
        "yaxis": axis(gridlines=True),
    }


def team_colour(roster_id, highlight):
    return HIGHLIGHT if roster_id == highlight else OTHERS


def merge(base, extra):
    """Deep-merge extra into a copy of base (dicts only), the way the page combines theme and chart layouts."""
    out = copy.deepcopy(base)
    for key, value in extra.items():
        out[key] = merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else copy.deepcopy(value)
    return out


def resolve_tokens(obj, palette):
    """Replace every '@token' string with its colour from palette (a dict of token -> colour)."""
    if isinstance(obj, dict):
        return {k: resolve_tokens(v, palette) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_tokens(v, palette) for v in obj]
    if isinstance(obj, str) and obj.startswith("@"):
        return palette[obj[1:]]
    return obj


def to_script_json(obj):
    """JSON safe to place inside <script type="application/json">: every < is written \\u003c, so nothing in the
    data (a team name, say) can end the script or open a tag. JSON.parse turns it back into <."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
