// Week selector: every week is already in the page, so switching needs no network call.
// The latest week is drawn in #week-view; earlier weeks wait in <template id="week-N"> blocks.
(function () {
  var view = document.getElementById("week-view");
  var select = document.getElementById("week");
  var title = document.getElementById("title");
  var shown = view.dataset.week;
  var titles = {};
  var parked = {};  // weeks already drawn, kept so expanded rows stay expanded
  titles[shown] = title.textContent;

  select.addEventListener("change", function () {
    var week = select.value;
    if (week === shown) return;
    var current = document.createDocumentFragment();
    while (view.firstChild) current.appendChild(view.firstChild);
    parked[shown] = current;
    var template = document.getElementById("week-" + week);
    if (template) titles[week] = template.dataset.title;
    view.appendChild(parked[week] || template.content.cloneNode(true));
    delete parked[week];
    view.dataset.week = shown = week;
    title.textContent = titles[week];
    view.dispatchEvent(new Event("weekshown"));  // charts.js draws this week's charts
  });

  // Stale data: when the last update is older than the limit on the viewer's own clock, say which week the
  // rankings are from and when the next scheduled update is due. Python writes the update times in; this only
  // picks the first one still ahead. Checked in the browser because a page that stopped updating can't rebuild itself.
  var status = document.getElementById("status");
  var stale = document.getElementById("stale");
  if (stale) {
    var now = Date.now();
    var limit = Number(status.dataset.staleAfterDays) * 24 * 60 * 60 * 1000;
    if (now - Date.parse(status.dataset.updated) > limit) {
      var upcoming = JSON.parse(document.getElementById("next-updates").textContent);
      var next = upcoming.find(function (u) { return Date.parse(u.at) > now; });
      if (next) {
        var due = document.getElementById("next-update");
        due.querySelector(".when").textContent = next.text;
        due.hidden = false;
      }
      stale.hidden = false;
    }
  }

  // The ladder's bars grow out from the average line once, on first load (CSS skips it for reduced motion).
  requestAnimationFrame(function () {
    requestAnimationFrame(function () { document.documentElement.classList.remove("preload"); });
  });
})();
