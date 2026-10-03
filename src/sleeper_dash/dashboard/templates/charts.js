// Draws the week's charts with the one shared theme (dashboard/theme.py).
// Figures name colours by design token ("@pylon"); they are filled in from the page's CSS custom
// properties, so charts follow light and dark mode. One team is highlighted in pylon: the week's
// #1 by default, or whichever team the viewer taps (a chart point or a ladder row).
(function () {
  var theme = JSON.parse(document.getElementById("chart-theme").textContent);
  var view = document.getElementById("week-view");
  var chosen = null;  // roster_id the viewer tapped; null means each week's #1

  function palette() {
    var css = getComputedStyle(document.documentElement), out = {};
    theme.tokens.forEach(function (t) { out[t] = css.getPropertyValue("--" + t).trim(); });
    return out;
  }
  function resolve(value, colours) {
    if (Array.isArray(value)) return value.map(function (v) { return resolve(v, colours); });
    if (value && typeof value === "object") {
      var out = {};
      Object.keys(value).forEach(function (k) { out[k] = resolve(value[k], colours); });
      return out;
    }
    return typeof value === "string" && value.charAt(0) === "@" ? colours[value.slice(1)] : value;
  }
  function merge(base, extra) {
    var out = JSON.parse(JSON.stringify(base));
    Object.keys(extra).forEach(function (k) {
      var v = extra[k];
      out[k] = v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object" ? merge(out[k], v) : v;
    });
    return out;
  }
  function setPath(obj, path, value) {
    var keys = path.split("."), last = keys.pop();
    keys.forEach(function (k) { obj = obj[k] = obj[k] || {}; });
    obj[last] = value;
  }
  function paint(figure, roster) {
    figure.data.forEach(function (trace) {
      var meta = trace.meta;
      if (!meta || !meta.paint) return;
      var colour = function (r) { return r === roster ? "@pylon" : "@bar"; };
      meta.paint.forEach(function (path) { setPath(trace, path, meta.rosters ? meta.rosters.map(colour) : colour(meta.roster)); });
    });
    // A team drawn as its own trace (a line) goes last, so the highlight sits on top of the grey lines.
    figure.data.sort(function (a, b) {
      return (a.meta && a.meta.roster === roster ? 1 : 0) - (b.meta && b.meta.roster === roster ? 1 : 0);
    });
    // Its name label turns bold (never pylon: small pylon text fails contrast in light mode).
    (figure.layout.annotations || []).forEach(function (a) {
      if (a.name === String(roster)) a.text = "<b>" + a.text + "</b>";
    });
  }
  function escapeText(text) {
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Direct labels for scatter points: try spots around each point, nearest first, and keep the one
  // that overlaps nothing (other labels, other points, the plot edge); farther spots get a leader line.
  var measure = document.createElement("canvas").getContext("2d");
  var DIRECTIONS = [[1, 0, 0], [-1, 0, 2], [1, -1, 4], [1, 1, 4], [-1, -1, 6], [-1, 1, 6], [0, -1, 8], [0, 1, 8]];
  var GAPS = [7, 20, 34, 50];
  function placeLabels(div, figure, roster, colours) {
    if (!figure.labels.length || !div._fullLayout) return;
    var full = div._fullLayout, xa = full.xaxis, ya = full.yaxis;
    var left = xa._offset - 4, right = full.width - 2, top = ya._offset - 6, bottom = ya._offset + ya._length + 4;
    var points = figure.labels.map(function (l) {
      return {label: l, x: xa._offset + xa.l2p(l.x), y: ya._offset + ya.l2p(l.y)};
    });
    var taken = points.map(function (p) { return {x0: p.x - 6, x1: p.x + 6, y0: p.y - 6, y1: p.y + 6}; });
    function overlap(a, b) {
      return Math.max(0, Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0)) * Math.max(0, Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0));
    }
    var labels = [], leaders = [];  // label boxes only (taken also holds the points), and leader lines drawn so far
    function crossings(x0, y0, x1, y1, boxes) {
      var hits = 0;
      boxes.forEach(function (b) {
        for (var s = 1; s < 10; s++) {
          var x = x0 + (x1 - x0) * s / 10, y = y0 + (y1 - y0) * s / 10;
          if (x > b.x0 && x < b.x1 && y > b.y0 && y < b.y1) { hits++; return; }
        }
      });
      return hits;
    }
    // Crowded points choose first, while there is still room near them.
    points.forEach(function (p) {
      p.crowd = points.filter(function (q) { return Math.abs(q.x - p.x) < 60 && Math.abs(q.y - p.y) < 24; }).length;
    });
    points.sort(function (a, b) { return b.crowd - a.crowd || a.y - b.y; });
    var annotations = points.map(function (p) {
      var bold = p.label.roster === roster;
      measure.font = (bold ? "600 " : "400 ") + "12px Barlow, system-ui, sans-serif";
      var w = measure.measureText(p.label.text).width + 4, h = 15, best = null;
      GAPS.forEach(function (gap, ring) {
        DIRECTIONS.forEach(function (d) {
          var cx = p.x + d[0] * (w / 2 + gap * (d[1] ? 0.7 : 1));
          var cy = p.y + d[1] * (h / 2 + gap * (d[0] ? 0.7 : 1));
          var box = {x0: cx - w / 2, x1: cx + w / 2, y0: cy - h / 2, y1: cy + h / 2};
          var cost = ring * 30 + d[2];
          if (box.x0 < left || box.x1 > right || box.y0 < top || box.y1 > bottom) cost += 10000;
          taken.forEach(function (t) { cost += overlap(box, t) * 4; });
          if (ring > 0) cost += 300 * crossings(p.x, p.y, cx, cy, labels);  // a leader line hidden under another label
          leaders.forEach(function (l) { cost += 300 * crossings(l[0], l[1], l[2], l[3], [box]); });  // or a label over one
          if (!best || cost < best.cost) best = {cost: cost, cx: cx, cy: cy, box: box, far: ring > 0};
        });
      });
      taken.push(best.box);
      labels.push(best.box);
      if (best.far) leaders.push([p.x, p.y, best.cx, best.cy]);
      var text = escapeText(p.label.text);
      return {
        name: String(p.label.roster), captureevents: true,
        x: p.label.x, y: p.label.y, xref: "x", yref: "y", ax: best.cx - p.x, ay: best.cy - p.y, axref: "pixel", ayref: "pixel",
        text: bold ? "<b>" + text + "</b>" : text, xanchor: "center", yanchor: "middle",
        font: {size: 12, color: colours.ink}, showarrow: true, arrowhead: 0, arrowwidth: 1, standoff: 6,
        arrowcolor: best.far ? colours.muted : "rgba(0,0,0,0)"
      };
    });
    Plotly.relayout(div, {annotations: (figure.layout.annotations || []).concat(annotations)});
  }

  function draw(div) {
    var figure = JSON.parse(document.getElementById("fig-" + div.dataset.figure).textContent);
    var roster = chosen === null ? figure.highlight : chosen;
    paint(figure, roster);
    var colours = palette();
    var fallback = div.querySelector(".chart-fallback");
    if (fallback) fallback.remove();
    Plotly.react(div, resolve(figure.data, colours), resolve(merge(theme.layout, figure.layout), colours), theme.config)
      .then(function () { placeLabels(div, figure, roster, colours); });
    if (!div.dataset.listening) {
      div.dataset.listening = "1";
      div.on("plotly_click", function (event) {
        var point = event.points && event.points[0];
        if (point && point.customdata !== undefined) highlight(point.customdata);
      });
      div.on("plotly_clickannotation", function (event) {  // a tapped team name
        if (event.annotation && event.annotation.name) highlight(event.annotation.name);
      });
    }
  }
  function drawAll() {
    if (!window.Plotly) return;  // CDN unavailable: each chart keeps its text summary
    view.querySelectorAll(".chart").forEach(draw);
  }
  function highlight(roster) {
    chosen = Number(roster);
    drawAll();
  }

  document.addEventListener("DOMContentLoaded", drawAll);  // runs after the deferred Plotly script
  view.addEventListener("weekshown", drawAll);
  view.addEventListener("toggle", function (event) {  // opening a ladder row highlights that team
    var team = event.target.closest && event.target.closest(".team");
    if (team && event.target.open) highlight(team.dataset.roster);
  }, true);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawAll);
  var resizing;
  window.addEventListener("resize", function () {
    clearTimeout(resizing);
    resizing = setTimeout(drawAll, 200);  // labels are placed in pixels, so place them again
  });
})();
