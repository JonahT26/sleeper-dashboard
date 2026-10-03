"""docs/UI_GUIDE.md "Quality floor": the parts a test can check without a browser.

- Motion: with reduced motion requested, nothing on the page moves (UI_GUIDE.md "Motion").
- Keyboard focus: every interactive element shows a visible focus ring that stands out from its background.
- Colour: the CSS tokens are the guide's, the contrast ratios the guide states are true, and all text meets
  WCAG AA in light and dark mode (4.5:1; 3:1 for large text, which is where pylon may appear).

Not checked here (needs a real browser): no sideways scrolling from 360px up.
"""

import json
import re
from importlib.resources import files

import pytest

from sleeper_dash.config import PROJECT_ROOT
from sleeper_dash.dashboard import theme
from sleeper_dash.dashboard.build import build_view, render
from test_dashboard import METRICS, RUN, make_tables
from test_page import parse

TEMPLATES = files("sleeper_dash.dashboard").joinpath("templates")
CSS = TEMPLATES.joinpath("styles.css").read_text(encoding="utf-8")
SCRIPTS = TEMPLATES.joinpath("page.js").read_text(encoding="utf-8") + TEMPLATES.joinpath("charts.js").read_text(encoding="utf-8")
GUIDE = (PROJECT_ROOT / "docs" / "UI_GUIDE.md").read_text(encoding="utf-8")
REDUCED, DARK = "(prefers-reduced-motion: reduce)", "(prefers-color-scheme: dark)"


def css_rules(css, media=None):
    """[(media or container query, or None; [selectors]; {property: value})] for every rule, one level of @media or @container deep."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules, i = [], 0
    while (start := css.find("{", i)) >= 0:
        depth, end = 1, start + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[end], 0)
            end += 1
        head, body = css[i:start].strip(), css[start + 1:end - 1]
        if head.startswith("@media"):
            rules += css_rules(body, head.removeprefix("@media").strip())
        elif head.startswith("@container"):
            rules += css_rules(body, head)
        else:
            declarations = dict((p.strip(), v.strip()) for p, v in (d.split(":", 1) for d in body.split(";") if ":" in d))
            rules.append((media, [s.strip() for s in head.split(",")], declarations))
        i = end
    return rules


RULES = css_rules(CSS)


def root_tokens(media):
    return {p[2:]: v for m, selectors, d in RULES if m == media and ":root" in selectors for p, v in d.items() if p.startswith("--")}


PALETTES = {"light": root_tokens(None), "dark": {**root_tokens(None), **root_tokens(DARK)}}


def colour(value, mode):
    """A CSS colour value as #RRGGBB, following var(--token) through the mode's palette."""
    while (m := re.fullmatch(r"var\(--([\w-]+)\)", value.strip())):
        value = PALETTES[mode][m.group(1)]
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", value), value
    return value.upper()


def luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG 2 contrast ratio between two #RRGGBB colours."""
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def page():
    return render(build_view(make_tables(), RUN, METRICS))


# --- Motion ------------------------------------------------------------------------------------

def test_reduced_motion_turns_off_every_transition_and_animation():
    moving = {(prop, s) for m, selectors, d in RULES if m != REDUCED for s in selectors
              for prop in ("transition", "animation") if d.get(prop, "none") != "none"}
    stopped = {(prop, s) for m, selectors, d in RULES if m == REDUCED for s in selectors
               for prop in ("transition", "animation") if d.get(prop) == "none"}
    assert moving, "the ladder's grow-in and the breakdown's expand should be found"
    assert moving - stopped == set()


def test_reduced_motion_shows_the_ladder_bars_full_length_from_the_start():
    hidden = {s for m, selectors, d in RULES if m != REDUCED for s in selectors if ".preload" in s and "transform" in d}
    shown = {s for m, selectors, d in RULES if m == REDUCED for s in selectors if d.get("transform") == "none"}
    assert hidden == {".preload .l3 .fill"} and hidden <= shown


def test_nothing_else_moves_on_its_own():
    assert "@keyframes" not in CSS and "scroll-behavior" not in CSS
    assert not re.search(r"Plotly\.animate|scrollIntoView|behavior\s*:|\.animate\(", SCRIPTS)
    assert "transition" not in theme.base_layout()
    for figure in re.findall(r'<script type="application/json" id="fig-[^"]+">(.*?)</script>', page(), re.S):
        figure = json.loads(figure)
        assert "transition" not in figure["layout"] and "frames" not in figure  # Plotly animates only with these


# --- Layout ------------------------------------------------------------------------------------

def test_the_one_line_ladder_leaves_room_for_team_names():
    """The ladder goes to one line a team only when the ladder itself is wide enough (beside the awards on a 1024px
    screen it is ~580px, and a screen-width rule once squeezed the name column to nothing there)."""
    [(query, row)] = [(m, d) for m, selectors, d in RULES if selectors == [".row"] and "grid-template-columns" in d and m]
    assert query.startswith("@container ladder")
    width = int(re.search(r"min-width:\s*(\d+)px", query).group(1))
    fixed = sum(float(n) * (16 if unit == "em" else 1)
                for n, unit in re.findall(r"(?<![\w(,])(\d+(?:\.\d+)?)(px|em)", row["grid-template-columns"]))
    gaps = 4 * 12 + 2 * 8  # column gaps and the row's side padding
    assert width - fixed - gaps >= 180   # the longest team name so far needs 191px at 16px; room left for the name column


# --- Keyboard focus ----------------------------------------------------------------------------

def outline_is_visible(declarations):
    outline = declarations.get("outline", "")
    width = re.search(r"(\d+(?:\.\d+)?)px", outline)
    return width and float(width.group(1)) >= 2 and "solid" in outline and "transparent" not in outline


def test_every_element_gets_a_visible_focus_ring():
    global_rings = [d for m, selectors, d in RULES if m is None and ":focus-visible" in selectors]
    assert len(global_rings) == 1 and outline_is_visible(global_rings[0])
    for m, selectors, d in RULES:
        if any(":focus" in s for s in selectors):
            assert outline_is_visible(d), selectors              # a narrower focus rule keeps the ring
        assert not re.fullmatch(r"(none|0(px)?)\b.*", d.get("outline", "x")), selectors   # nothing switches it off
        assert d.get("outline-style") != "none" and d.get("outline-width") not in ("0", "0px"), selectors


def test_every_interactive_element_can_be_reached_with_the_keyboard():
    doc = parse(page())
    interactive = [n for n in doc.walk() if n.tag in ("a", "button", "input", "select", "textarea", "summary") or "tabindex" in n.attrs]
    assert {n.tag for n in interactive} == {"select", "summary"}   # the week selector and the ladder rows
    assert all(n.attrs.get("tabindex") in (None, "0") for n in interactive)
    for summary in [n for n in interactive if n.tag == "summary"]:
        siblings = [c for c in summary.parent.children if not isinstance(c, str)]
        assert summary.parent.tag == "details" and siblings[0] is summary  # only then is a summary focusable and toggles
    week = doc.one("select", id="week")
    assert doc.one("label", **{"for": "week"}).text() == "Week" and week.all("option")


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("background", ["page", "masthead"])
def test_the_focus_ring_stands_out_from_every_background_it_is_drawn_on(mode, background):
    """WCAG 1.4.11: a focus indicator needs 3:1 against what it sits on (ladder rows on the page; the week selector on the masthead)."""
    ring = next(d for m, selectors, d in RULES if m is None and ":focus-visible" in selectors)
    ring_colour = colour(re.search(r"var\(--[\w-]+\)|#[0-9A-Fa-f]{6}", ring["outline"]).group(0), mode)
    assert contrast(ring_colour, colour(f"var(--{background})", mode)) >= 3


# --- Colour ------------------------------------------------------------------------------------

def guide_tokens():
    rows = re.findall(r"^\| `--([\w-]+)` \| `(#[0-9A-Fa-f]{6})` \| `(#[0-9A-Fa-f]{6})` \|", GUIDE, re.M)
    assert len(rows) == 10
    return rows


@pytest.mark.parametrize("token, light, dark", guide_tokens())
def test_css_tokens_are_the_guides_colours(token, light, dark):
    assert (colour(f"var(--{token})", "light"), colour(f"var(--{token})", "dark")) == (light.upper(), dark.upper())


# Ratios stated in UI_GUIDE.md "Color" (the token table and the contrast notes under it), to the precision stated.
STATED = [
    ("ink on chalk", "#15201A", "#F6F8F4", 15.7),
    ("chalk on turf", "#F6F8F4", "#18392B", 11.8),  # the guide said 11.9 until 2026-10-02; corrected (owner)
    ("muted on chalk", "#5B6B61", "#F6F8F4", 5.3),
    ("up on chalk", "#1D6FB8", "#F6F8F4", 4.9),
    ("down on chalk", "#B42318", "#F6F8F4", 6.2),
    ("light-mode pylon on chalk", "#E8590C", "#F6F8F4", 3.4),
    ("dark-mode masthead on the dark page", "#18392B", "#0F1F17", 1.35),
    ("dark-mode chalk text on the masthead", "#E8EDE9", "#18392B", 10.7),
    ("dark-mode muted text on the masthead", "#9DADA3", "#18392B", 5.4),
]


@pytest.mark.parametrize("pair, foreground, background, stated", STATED, ids=[s[0] for s in STATED])
def test_the_contrast_ratios_stated_in_the_guide_are_true(pair, foreground, background, stated):
    places = len(str(stated).split(".")[1])
    assert contrast(foreground, background) == pytest.approx(stated, abs=0.5 * 10 ** -places + 1e-9)


# Text on the masthead band; everything else sits on the page background.
MASTHEAD_TEXT = {".mast", ".status", ".updated", ".stale", ".week-pick select"}  # the status bar is masthead-coloured
LITERAL_BACKGROUNDS = {".week-pick select option": "#F6F8F4"}  # the open dropdown list draws its own background
LARGE_TEXT = {".team:first-child .rank"}                       # the #1 rank numeral, 48px bold: 3:1 is enough


def text_colours():
    for m, selectors, d in RULES:
        if m != REDUCED and "color" in d and d["color"] not in ("inherit", "currentColor", "transparent"):
            for s in selectors:
                yield m, s, d["color"], d.get("background")


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_all_text_meets_wcag_aa(mode):
    checked = []
    for media, selector, value, background in text_colours():
        if media == DARK and mode == "light":
            continue
        if selector in LITERAL_BACKGROUNDS:
            back = colour(background or LITERAL_BACKGROUNDS[selector], mode)
        else:
            back = colour("var(--masthead)" if selector in MASTHEAD_TEXT else "var(--page)", mode)
        ratio = contrast(colour(value, mode), back)
        checked.append(selector)
        assert ratio >= (3 if selector in LARGE_TEXT else 4.5), f"{selector}: {ratio:.2f}:1 in {mode} mode"
    assert {"body", ".updated", ".stale", ".key", ".move.up", ".move.down", ".team:first-child .rank"} <= set(checked)


def test_the_status_bar_stays_on_screen_with_the_masthead_colour():
    status = next(d for m, selectors, d in RULES if m is None and selectors == [".status"])
    assert status["position"] == "sticky" and status["top"] == "0" and status["background"] == "var(--masthead)"


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_chart_text_meets_wcag_aa(mode):
    """Charts have transparent backgrounds, so their text sits on the page; hover labels draw a page-coloured box."""
    text = page()
    used = set(re.findall(r'"\w*font":\{[^{}]*"color":"@(\w+)"', text))  # font, textfont, tickfont, title font
    used |= {theme.base_layout()["font"]["color"][1:], theme.base_layout()["hoverlabel"]["font"]["color"][1:]}
    assert used == {"ink", "muted"}
    for token in used:
        assert contrast(colour(f"var(--{token})", mode), colour("var(--page)", mode)) >= 4.5, token


def test_pylon_is_used_for_large_text_only():
    """Light-mode pylon is 3.4:1: fine for 24px+ bold and fills, never small text (UI_GUIDE.md "Color")."""
    pylon_text = {s for m, selectors, d in RULES if d.get("color") == "var(--pylon)" for s in selectors}
    assert pylon_text == LARGE_TEXT
    rank = next(d for m, selectors, d in RULES if m is None and selectors == [".rank"])
    assert rank["font-size"] == "48px" and rank["font-weight"] == "700"
    text = page()
    assert not re.search(r'"\w*font":\{[^{}]*"color":"@pylon"', text)    # chart labels: never pylon
    paints = {p for m in re.findall(r'"paint":\[([^\]]*)\]', text) for p in json.loads(f"[{m}]")}
    assert paints <= {"marker.color", "marker.line.color", "line.color"}             # the highlight colours marks, not text
