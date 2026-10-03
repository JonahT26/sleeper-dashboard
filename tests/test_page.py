"""The built page, read back the way a browser sees it (Phase 3 plan step 5; docs/UI_GUIDE.md "Layout" and "Quality floor").

Two pages are built in memory:
- this season's page, from the saved tables in data/processed/ (committed, so these tests run anywhere), and
- a synthetic 17-week season (test_dashboard.make_tables), which reaches the playoffs.

For every week in each page: the sections the guide lists are there, in order, and a section
whose data doesn't exist yet is left out entirely; nothing is loaded from outside except Google
Fonts and the Plotly CDN; the page stays under the 1 MB budget; and every number on the ladder,
the award tiles, and in the charts is exactly the value in power_rankings.csv, metrics_season.csv,
or awards.csv, rounded the way the guide says. The pipeline's run record (gitignored) is replaced
by a fixed one, so nothing here depends on when the pipeline last ran. No network.
"""

import gzip
import json
import re
from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import urlsplit

import pandas as pd
import pytest

from sleeper_dash.config import load_config
from sleeper_dash.dashboard import build, theme
from sleeper_dash.dashboard.build import build_view, render
from sleeper_dash.transform import PROCESSED_DIR
from sleeper_dash.validate import load_tables
from test_dashboard import METRICS, RUN, make_tables

MINUS, EN_DASH = "−", "–"
# The guide's section order (UI_GUIDE.md "Layout"); "How this works" follows, once for the whole page.
SECTION_ORDER = ["ladder", "awards", "luck", "efficiency", "consistency", "schedule", "rank-history"]
# Bar axes, rounded up to these (UI_GUIDE.md "Ladder row").
POWER_AXIS_STEPS = [5, 10, 15, 20, 25, 30, 40, 50]
PART_AXIS_STEPS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20]
COMPONENTS = [("season_scoring", "Season scoring"), ("recent_form", "Recent form"),
              ("roster_strength", "Roster strength"), ("results", "Head-to-head wins")]
ALLOWED_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com", "cdn.plot.ly"}
BUDGET = 1_000_000  # bytes, compressed (owner decision 2026-10-02)


# --- Reading the page -------------------------------------------------------------------------

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    @property
    def classes(self):
        return (self.attrs.get("class") or "").split()

    def text(self):
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def walk(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.walk()

    def all(self, tag=None, cls=None, **attrs):
        return [n for n in self.walk() if (tag is None or n.tag == tag) and (cls is None or cls in n.classes)
                and all(n.attrs.get(k) == v for k, v in attrs.items())]

    def one(self, tag=None, cls=None, **attrs):
        found = self.all(tag, cls, **attrs)
        assert len(found) == 1, f"expected one <{tag or '*'} class={cls} {attrs}>, found {len(found)}"
        return found[0]


class _Tree(HTMLParser):
    """A small DOM. Strict: every tag must be closed in order, so badly formed HTML fails the tests."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node("#document")

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, attrs, self.current))

    def handle_endtag(self, tag):
        assert self.current.tag == tag, f"</{tag}> closes <{self.current.tag}>"
        self.current = self.current.parent

    def handle_data(self, data):
        self.current.children.append(data)


def parse(html):
    tree = _Tree()
    tree.feed(html)
    tree.close()
    assert tree.current is tree.root, f"<{tree.current.tag}> is never closed"
    return tree.root


def week_nodes(doc):
    """{week: the element holding that week's sections}: the latest in #week-view, each earlier one in a <template>."""
    view = doc.one(id="week-view")
    weeks = {int(view.attrs["data-week"]): view}
    for template in doc.all("template"):
        weeks[int(template.attrs["id"].removeprefix("week-"))] = template
    return dict(sorted(weeks.items()))


def section_keys(node):
    """The week's sections in page order, named as in SECTION_ORDER."""
    keys = []
    for section in node.all("section"):
        if "ladder-section" in section.classes:
            keys.append("ladder")
        elif "awards" in section.classes:
            keys.append("awards")
        elif "chart-section" in section.classes:
            keys.append(section.one("script").attrs["id"].removeprefix("fig-").rsplit("-", 1)[0])
    return keys


def figure(node, key, week):
    return json.loads(node.one("script", id=f"fig-{key}-{week}").text())


def summary(node, key, week):
    """A chart's one-sentence text summary: read by screen readers, and shown if Plotly can't load."""
    chart = node.one("div", "chart", **{"data-figure": f"{key}-{week}"})
    assert chart.one("p", "chart-fallback").text() == chart.attrs["aria-label"]
    return chart.attrs["aria-label"]


# --- What the numbers should look like (UI_GUIDE.md "Numbers and copy") ----------------------

def one_dp(value):
    return f"{value:.1f}"


def signed(value):
    text = f"{abs(value):.1f}"
    return text if text == "0.0" else ("+" if value > 0 else MINUS) + text


def wins(value):
    return f"{value:g} win" if value == 1 else f"{value:g} wins"


def axis(largest, steps):
    return next((s for s in steps if s >= largest - 1e-9), steps[-1])


def bar_geometry(span):
    fill = span.one("span", "fill")
    style = dict(part.split(":") for part in fill.attrs["style"].rstrip(";").split(";"))
    side = "pos" if "pos" in fill.classes else "neg"
    return side, float(style["left"].rstrip("%")), float(style["width"].rstrip("%"))


def assert_bar(span, gap, axis_end):
    side, left, width = bar_geometry(span)
    expected = min(abs(gap) / axis_end, 1) * 50
    assert side == ("pos" if gap >= 0 else "neg")
    assert width == pytest.approx(expected, abs=0.006)
    assert left == pytest.approx(50 if gap >= 0 else 50 - expected, abs=0.006)


# --- The two pages ----------------------------------------------------------------------------

def built(tables, params):
    weeks = sorted(int(w) for w in tables["power_rankings"]["week"].unique())
    html = render(build_view(tables, {**RUN, "weeks": weeks}, params, build.freshness(RUN, 8, build.workflow_schedule())))
    return SimpleNamespace(tables=tables, params=params, html=html, doc=parse(html))


def this_season():
    return load_tables(PROCESSED_DIR, names=build.TABLES), load_config().metrics


@pytest.fixture(scope="module", params=["this season", "synthetic 17 weeks"])
def season(request):
    tables, params = this_season() if request.param == "this season" else (make_tables(weeks=17), METRICS)
    return built(tables, params)


def standings(tables, week):
    s = tables["metrics_season"]
    return s[s["through_week"] == week].set_index("roster_id").sort_index()


def expected_sections(tables, week):
    """Which sections a week should show, worked out from the tables alone."""
    s = standings(tables, week)
    lineups = tables["lineups_optimal"]
    has = {
        "ladder": True,
        "awards": bool((tables["awards"]["week"] == week).any()),
        "luck": not s.empty and bool(s["expected_wins"].notna().all()),
        "efficiency": bool((lineups["week"] <= week).any()),
        "consistency": bool(s["volatility"].notna().any()),
        "schedule": bool(s["sos_played"].notna().any()),
        "rank-history": tables["power_rankings"].loc[tables["power_rankings"]["week"] <= week, "week"].nunique() >= 2,
    }
    return [key for key in SECTION_ORDER if has[key]]


# --- Sections ---------------------------------------------------------------------------------

def test_every_week_is_in_the_page_and_the_selector_opens_on_the_latest(season):
    weeks = sorted(int(w) for w in season.tables["power_rankings"]["week"].unique())
    nodes = week_nodes(season.doc)
    assert list(nodes) == weeks
    assert set(season.tables["awards"]["week"]) <= set(weeks)
    options = season.doc.one("select", id="week").all("option")
    assert [int(o.attrs["value"]) for o in options] == weeks
    assert [o.attrs["value"] for o in options if "selected" in o.attrs] == [str(weeks[-1])]
    assert season.doc.one("h1", id="title").text() == f"Week {weeks[-1]} power rankings"
    for week in weeks[:-1]:
        assert nodes[week].attrs["data-title"] == f"Week {week} power rankings"


def test_masthead_shows_the_league_and_the_status_bar_when_it_was_updated(season):
    mast = season.doc.one("header", "mast")
    assert mast.one("p", "league").text() == RUN["league_name"]
    status = season.doc.one("div", "status", id="status")
    assert status.attrs["data-updated"] == RUN["finished_at"]
    assert status.one("p", "updated").text() == "Updated Tue Oct 6, 9:00 AM ET"
    assert status.one("time").attrs["datetime"] == RUN["finished_at"]


def test_the_stale_data_line_names_the_latest_week_and_waits_for_the_browser(season):
    """Hidden in the page; page.js shows it when the update is more than stale_after_days old on the viewer's clock."""
    weeks = sorted(int(w) for w in season.tables["power_rankings"]["week"].unique())
    status = season.doc.one("div", "status", id="status")
    assert status.attrs["data-stale-after-days"] == "8"
    line = status.one("p", "stale", id="stale")
    assert "hidden" in line.attrs and "hidden" in line.one("span", id="next-update").attrs
    assert line.text() == f"The latest rankings are from week {weeks[-1]}. Next update due ."   # the browser fills in the time
    upcoming = json.loads(status.one("script", id="next-updates").text())
    assert upcoming[0] == {"at": "2026-10-06T16:17:00+00:00", "text": "Tue Oct 6, 12:17 PM ET"}  # the run is Tue Oct 6, 9 AM ET


def test_every_week_shows_exactly_the_sections_its_data_supports_in_guide_order(season):
    for week, node in week_nodes(season.doc).items():
        assert section_keys(node) == expected_sections(season.tables, week), f"week {week}"


def test_hidden_sections_leave_nothing_behind(season):
    for week, node in week_nodes(season.doc).items():
        keys = section_keys(node)
        assert bool(node.all("div", "charts")) == any(k not in ("ladder", "awards") for k in keys), f"week {week}"
        for section in node.all("section"):
            assert section.text().strip(), f"an empty section in week {week}"
        assert not node.all("ul", "tiles") or node.one("ul", "tiles").all("li", "tile")
        text = node.text().lower()
        assert not any(word in text for word in ("no data", "not available", "coming soon", "check back")), f"week {week}"


def test_this_seasons_early_weeks_hide_the_charts_that_need_more_weeks():
    tables, params = this_season()
    page = built(tables, params)
    nodes = week_nodes(page.doc)
    min_weeks = params["consistency"]["min_weeks"], params["schedule"]["min_weeks"]
    for week, node in nodes.items():
        keys = section_keys(node)
        assert ("consistency" in keys) == (week >= min_weeks[0]) and ("schedule" in keys) == (week >= min_weeks[1])
        assert ("rank-history" in keys) == (week >= 2)


def test_a_week_whose_data_is_missing_loses_those_sections_and_nothing_else():
    tables, params = this_season()
    first, second = sorted(tables["power_rankings"]["week"].unique())[:2]
    tables["awards"] = tables["awards"][tables["awards"]["week"] != second]
    tables["lineups_optimal"] = tables["lineups_optimal"][tables["lineups_optimal"]["week"] != first]
    tables["metrics_season"] = tables["metrics_season"].copy()
    tables["metrics_season"].loc[tables["metrics_season"]["through_week"] == first, "expected_wins"] = float("nan")
    nodes = week_nodes(built(tables, params).doc)
    assert section_keys(nodes[first]) == ["ladder", "awards"] and not nodes[first].all("div", "charts")
    assert "awards" not in section_keys(nodes[second]) and "Weekly awards" not in nodes[second].text()
    assert section_keys(nodes[second])[0] == "ladder" and "luck" in section_keys(nodes[second])


def test_how_this_works_appears_once_after_the_weeks(season):
    how = season.doc.one("section", "how")
    assert how.one("h2").text() == "How this works" and len(how.all("p")) > 5
    assert all(not t.all("section", "how") for t in season.doc.all("template"))
    order = [n for n in season.doc.walk() if n.attrs.get("id") in ("week-view", "how-title")]
    assert [n.attrs["id"] for n in order] == ["week-view", "how-title"]


# --- Outside requests -------------------------------------------------------------------------

FETCHING_ATTRS = {"src", "href", "srcset", "imagesrcset", "poster", "data", "action", "formaction", "ping", "manifest", "background"}
FETCHING_TAGS = {"img", "picture", "iframe", "frame", "object", "embed", "video", "audio", "source", "track", "form", "base", "svg"}
NETWORK_JS = re.compile(r"fetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|import\s*\(|new\s+Image\b"
                        r"|createElement\(\s*[\"'](?:script|img|link|iframe|audio|video|source|object|embed)[\"']|https?:")


def test_the_only_outside_requests_are_google_fonts_and_the_plotly_cdn(season):
    doc = season.doc
    for node in doc.walk():
        for attr, value in node.attrs.items():
            if attr in FETCHING_ATTRS and not value.startswith("#"):
                url = urlsplit(value)
                assert url.scheme == "https" and url.netloc in ALLOWED_HOSTS, f'<{node.tag} {attr}="{value}">'
    assert not [n.tag for n in doc.walk() if n.tag in FETCHING_TAGS]
    assert not [n for n in doc.walk() if "http-equiv" in n.attrs]
    assert [n.attrs["src"] for n in doc.all("script") if "src" in n.attrs] == [theme.PLOTLY_CDN]
    sheets = [n.attrs["href"] for n in doc.all("link") if n.attrs.get("rel") == "stylesheet"]
    assert len(sheets) == 1 and sheets[0].startswith("https://fonts.googleapis.com/css2?")


def test_inline_styles_and_scripts_fetch_nothing(season):
    doc = season.doc
    css = [n.text() for n in doc.all("style")] + [n.attrs["style"] for n in doc.walk() if n.attrs.get("style")]
    for text in css:
        assert "url(" not in text and "@import" not in text and "image-set(" not in text
    code = [n.text() for n in doc.all("script") if "src" not in n.attrs and n.attrs.get("type") != "application/json"]
    assert len(code) == 3  # the preload flag, the week selector, the chart drawing
    for text in code:
        assert not NETWORK_JS.search(text), NETWORK_JS.search(text).group(0)


def test_chart_figures_use_nothing_plotly_would_download(season):
    for week, node in week_nodes(season.doc).items():
        for script in node.all("script", type="application/json"):
            fig = json.loads(script.text())
            assert {t["type"] for t in fig["data"]} <= {"scatter", "bar"}  # no maps (which fetch map data)
            assert "images" not in fig["layout"]                          # no layout images (which fetch a URL)


# --- Page weight ------------------------------------------------------------------------------

def full_season(tables, last_week=17):
    """This season's tables stretched to a full season by repeating the latest week (real names, captions, nine awards)."""
    latest = int(tables["power_rankings"]["week"].max())
    out = dict(tables)
    for name, column in [("team_weeks", "week"), ("lineups_optimal", "week"), ("power_rankings", "week"),
                         ("awards", "week"), ("metrics_season", "through_week")]:
        table = tables[name]
        last = table[table[column] == latest]
        out[name] = pd.concat([table, *(last.assign(**{column: w}) for w in range(latest + 1, last_week + 1))], ignore_index=True)
    out["team_weeks"]["is_playoff"] = out["team_weeks"]["week"] >= 15
    return out


def compressed(html):
    return len(gzip.compress(html.encode("utf-8")))


def test_this_seasons_page_is_under_the_budget(season):
    assert compressed(season.html) < BUDGET


def test_a_full_season_of_this_leagues_data_is_under_the_budget():
    tables, params = this_season()
    page = built(full_season(tables), params)
    assert len(week_nodes(page.doc)) == 17
    assert compressed(page.html) < BUDGET


def test_plotly_and_the_fonts_are_not_inlined(season):
    """The budget excludes the Plotly script because it is loaded from the CDN, not copied into the page."""
    assert "plotly.js (basic)" not in season.html and "@font-face" not in season.html and "base64," not in season.html
    assert max(len(n.text()) for n in season.doc.all("script")) < 100_000  # Plotly's basic bundle is ~1 MB


# --- The ladder matches power_rankings.csv and metrics_season.csv ------------------------------

def test_ladder_numbers_match_the_tables_for_every_week(season):
    tables, params = season.tables, season.params
    power, teams = tables["power_rankings"], tables["teams"].set_index("roster_id")
    weights, recent = params["power"]["weights"], params["power"]["recent_weeks"]
    latest = standings(tables, int(power["week"].max()))
    show_ties, show_allplay_ties = bool((latest["ties"] > 0).any()), bool((latest["allplay_ties"] > 0).any())
    power_axis = axis((power["power_score"] - 50).abs().max(), POWER_AXIS_STEPS)
    part_axis = axis(max((power[f"contrib_{c}"] - 50 * weights[c]).abs().max() for c, _ in COMPONENTS), PART_AXIS_STEPS)

    def rec(w, l, t, ties):
        return EN_DASH.join(str(int(n)) for n in ((w, l, t) if ties else (w, l)))

    for week, node in week_nodes(season.doc).items():
        ranked = power[power["week"] == week].sort_values("rank")
        s = standings(tables, week)
        rows = node.all("li", "team")
        assert [int(r.attrs["data-roster"]) for r in rows] == ranked["roster_id"].tolist(), f"week {week} order"
        for li, p in zip(rows, ranked.itertuples()):
            team, where = s.loc[p.roster_id], f"week {week}, roster {p.roster_id}"
            assert li.one("span", "rank").text() == str(int(p.rank)), where
            assert li.one("span", "name").text() == teams.at[p.roster_id, "team_name"], where
            assert li.one("span", "user").text() == teams.at[p.roster_id, "display_name"], where
            assert li.one("span", "val").text() == f"power score {one_dp(p.power_score)}", where
            assert_bar(li.one("span", "l3"), p.power_score - 50, power_axis)
            assert li.one("span", "rec").text() == (f"{rec(team.wins, team.losses, team.ties, show_ties)}, all-play "
                                                    f"{rec(team.allplay_wins, team.allplay_losses, team.allplay_ties, show_allplay_ties)}"), where
            move = li.one("span", "move")
            change = p.rank_change
            if pd.isna(change):
                assert (move.one("span", "sr").text(), move.children[0].text()) == ("first week", EN_DASH), where
            elif change == 0:
                assert (move.one("span", "sr").text(), move.children[0].text()) == ("no change", EN_DASH), where
            else:
                n = abs(int(change))
                spoken, arrow = (f"up {n}", f"▲{n}") if change > 0 else (f"down {n}", f"▼{n}")
                assert (move.one("span", "sr").text(), move.children[0].text()) == (spoken, arrow), where

            parts = li.one("table", "parts").one("tbody").all("tr")
            assert len(parts) == 5, where
            k = min(recent, week)
            details = {"season_scoring": f"{one_dp(p.season_scoring)} points a week",
                       "recent_form": f"{one_dp(p.recent_form)} points a week, " + ("this week" if k == 1 else f"last {k} weeks"),
                       "roster_strength": f"{one_dp(p.roster_strength)} points a week with the best lineup",
                       "results": f"Won {int(team.h2h_wins)} of {int(team.h2h_wins + team.h2h_losses + team.h2h_ties)}"
                                  + (f", tied {int(team.h2h_ties)}" if team.h2h_ties else "")}
            for tr, (c, label) in zip(parts, COMPONENTS):
                contribution = getattr(p, f"contrib_{c}")
                gap = contribution - 50 * weights[c]
                assert tr.one("span", "comp").text() == f"{label} ({round(weights[c] * 100)}%)", where
                assert tr.one("span", "detail").text() == details[c], where
                assert tr.one("td", "sc").text() == one_dp(contribution), where
                assert tr.one("span", "vs-num").text() == signed(gap), where
                assert_bar(tr.one("td", "vs"), gap, part_axis)
            total = parts[4]
            assert [td.text() for td in total.all("td")] == [one_dp(p.power_score), signed(p.power_score - 50)], where


# --- Award tiles match awards.csv -------------------------------------------------------------

AWARD_FORMATS = {"perfect_lineup": lambda v: f"{round(v * 100)}%", "asleep_at_the_wheel": lambda v: str(int(v))}


def test_award_tiles_match_the_awards_table_for_every_week(season):
    awards, teams = season.tables["awards"], season.tables["teams"].set_index("roster_id")
    for week, node in week_nodes(season.doc).items():
        rows = awards[awards["week"] == week]
        if rows.empty:
            assert not node.all("section", "awards"), f"week {week}"
            continue
        tiles = node.one("section", "awards").all("li", "tile")
        groups = list(rows.groupby("award", sort=False))
        assert len(tiles) == len(groups), f"week {week}"
        for tile, (award, winners) in zip(tiles, groups):
            where = f"week {week}, {award}"
            assert winners["value"].nunique() == 1, where  # co-winners share a tile because they tied
            value = winners["value"].iloc[0]
            assert tile.one("h3", "award").text() == winners["award_name"].iloc[0], where
            assert tile.one("p", "award-value").text() == AWARD_FORMATS.get(award, one_dp)(value), where
            assert [p.text() for p in tile.all("p", "winner")] == [teams.at[r, "team_name"] for r in winners["roster_id"]], where
            assert [p.text() for p in tile.all("p", "caption")] == winners["caption"].tolist(), where


# --- Charts match metrics_season.csv and power_rankings.csv -----------------------------------

def named(text, label, names):
    """The team a summary names after `label`, e.g. 'Luckiest: '; the longest matching name wins."""
    rest = text[text.index(label) + len(label):]
    return max((r for r, n in names.items() if rest.startswith(n)), key=lambda r: len(names[r]))


def rows_by_team(annotations):
    """{row: roster_id} from the tappable team-name labels of a one-row-per-team chart."""
    return {a["y"]: int(a["name"]) for a in annotations if a.get("name")}


def test_charts_highlight_the_weeks_top_ranked_team(season):
    power = season.tables["power_rankings"]
    for week, node in week_nodes(season.doc).items():
        top = int(power.loc[(power["week"] == week) & (power["rank"] == 1), "roster_id"].iloc[0])
        for script in node.all("script", type="application/json"):
            fig = json.loads(script.text())
            assert fig["highlight"] == top, f"week {week}"
            for trace in fig["data"]:
                meta = trace.get("meta") or {}
                if "rosters" in meta and "marker.color" in meta["paint"]:
                    assert [r for r, c in zip(meta["rosters"], trace["marker"]["color"]) if c == "@pylon"] == \
                           [r for r in meta["rosters"] if r == top]


def test_luck_chart_matches_metrics_season(season):
    names = season.tables["teams"].set_index("roster_id")["team_name"].to_dict()
    for week, node in week_nodes(season.doc).items():
        s = standings(season.tables, week)
        fig = figure(node, "luck", week)
        points = next(t for t in fig["data"] if t["mode"] == "markers")
        assert sorted(points["meta"]["rosters"]) == s.index.tolist()
        for roster, x, y, hover in zip(points["meta"]["rosters"], points["x"], points["y"], points["hovertext"]):
            team = s.loc[roster]
            assert x == pytest.approx(team.expected_wins, abs=5e-4) and y == team.actual_wins, f"week {week}, roster {roster}"
            assert hover.endswith(f"{wins(team.actual_wins)}, {team.expected_wins:.1f} expected, luck {signed(team.luck)}"), \
                f"week {week}, roster {roster}"
        for label in fig["labels"]:
            team = s.loc[label["roster"]]
            assert (label["x"], label["y"], label["text"]) == (pytest.approx(team.expected_wins, abs=5e-4), team.actual_wins, names[label["roster"]])
        text = summary(node, "luck", week)
        for label, best in (("Luckiest: ", s["luck"].max()), ("Unluckiest: ", s["luck"].min())):
            team = s.loc[named(text, label, names)]
            assert team.luck == pytest.approx(best)
            assert (f"{label}{names[team.name]}, {wins(team.actual_wins)} from {team.expected_wins:.1f} expected "
                    f"({signed(team.luck)})") in text


def test_efficiency_chart_matches_metrics_season(season):
    names = season.tables["teams"].set_index("roster_id")["team_name"].to_dict()
    for week, node in week_nodes(season.doc).items():
        s = standings(season.tables, week)
        fig = figure(node, "efficiency", week)
        annotations = fig["layout"]["annotations"]
        row_team = rows_by_team(annotations)
        values = {a["y"]: a["text"] for a in annotations if not a.get("name")}
        for row, roster in row_team.items():
            assert values[row] == f"{round(s.at[roster, 'efficiency'] * 100)}%", f"week {week}, roster {roster}"
        top_down = [row_team[row] for row in sorted(row_team, reverse=True)]
        assert sorted(top_down) == s.index.tolist()
        assert s.loc[top_down, "efficiency"].is_monotonic_decreasing, f"week {week}: most efficient on top"
        text = summary(node, "efficiency", week)
        for label, team in (("Most efficient: ", top_down[0]), ("Least: ", top_down[-1])):
            assert f"{label}{names[team]}" in text and f"{round(s.at[team, 'efficiency'] * 100)}%" in text


def test_consistency_chart_matches_metrics_season(season):
    names = season.tables["teams"].set_index("roster_id")["team_name"].to_dict()
    for week, node in week_nodes(season.doc).items():
        s = standings(season.tables, week)
        if s["volatility"].isna().all():
            continue
        fig = figure(node, "consistency", week)
        annotations = fig["layout"]["annotations"]
        row_team = rows_by_team(annotations)
        swings = {a["y"]: a["text"] for a in annotations if a.get("xanchor") == "right" and not a.get("name")}
        band = fig["data"][0]
        for i in range(0, len(band["x"]), 3):
            roster = row_team[band["y"][i]]
            team = s.loc[roster]
            assert band["x"][i:i + 2] == [pytest.approx(team.floor), pytest.approx(team.ceiling)], f"week {week}, roster {roster}"
            assert swings[band["y"][i]] == f"±{team.volatility:.1f}"
        top_down = [row_team[row] for row in sorted(row_team, reverse=True)]
        assert sorted(top_down) == s.index.tolist() and s.loc[top_down, "volatility"].is_monotonic_increasing  # steadiest on top
        text = summary(node, "consistency", week)
        steady, swingy = s.loc[top_down[0]], s.loc[top_down[-1]]
        assert f"Steadiest: {names[top_down[0]]} (±{steady.volatility:.1f} points)" in text
        assert f"Swingiest: {names[top_down[-1]]} (±{swingy.volatility:.1f})" in text


def test_schedule_chart_matches_metrics_season(season):
    names = season.tables["teams"].set_index("roster_id")["team_name"].to_dict()
    for week, node in week_nodes(season.doc).items():
        s = standings(season.tables, week)
        if s["sos_played"].isna().all():
            continue
        fig = figure(node, "schedule", week)
        panels = {t["xaxis"]: t for t in fig["data"]}
        remaining = s["sos_remaining"]
        all_average = remaining.notna().any() and bool((remaining.abs() < 0.05).all())
        two_panels = remaining.notna().any() and not all_average
        assert set(panels) == ({"x", "x2"} if two_panels else {"x"}), f"week {week}"
        for axis_name, column in (("x", "sos_played"), ("x2", "sos_remaining")):
            if axis_name not in panels:
                continue
            bars = panels[axis_name]
            assert sorted(bars["customdata"]) == s.index.tolist()
            for roster, x, label in zip(bars["customdata"], bars["x"], bars["text"]):
                value = s.at[roster, column]
                assert x == pytest.approx(value, abs=0.0051) and label == signed(value), f"week {week}, {column}, roster {roster}"
        subtitle = node.one("section", "chart-section", **{"aria-labelledby": f"schedule-{week}-title"}).one("p", "sub").text()
        assert subtitle.endswith("every team's remaining opponents are exactly average (0.0).") == all_average
        text = summary(node, "schedule", week)
        for label, best in (("Toughest so far: ", s["sos_played"].max()), ("Easiest: ", s["sos_played"].min())):
            roster = named(text, label, names)
            assert s.at[roster, "sos_played"] == pytest.approx(best) and f"({signed(best)}" in text


def test_rank_history_matches_power_rankings(season):
    power = season.tables["power_rankings"]
    names = season.tables["teams"].set_index("roster_id")["team_name"].to_dict()
    for week, node in week_nodes(season.doc).items():
        so_far = power[power["week"] <= week]
        if so_far["week"].nunique() < 2:
            continue
        fig = figure(node, "rank-history", week)
        lines = {t["meta"]["roster"]: t for t in fig["data"]}
        assert sorted(lines) == sorted(so_far["roster_id"].unique())
        for roster, line in lines.items():
            history = so_far[so_far["roster_id"] == roster].sort_values("week")
            assert line["x"] == history["week"].tolist() and line["y"] == history["rank"].tolist(), f"week {week}, roster {roster}"
        first = so_far[so_far["week"] == so_far["week"].min()].set_index("roster_id")["rank"]
        latest = so_far[so_far["week"] == week].set_index("roster_id")["rank"]
        moved = first - latest
        text = summary(node, "rank-history", week)
        for label, best in (("Biggest riser: ", moved.max()), ("Biggest faller: ", moved.min())):
            roster = named(text, label, names)
            assert moved[roster] == best and f"{names[roster]}, from #{first[roster]} to #{latest[roster]}" in text
