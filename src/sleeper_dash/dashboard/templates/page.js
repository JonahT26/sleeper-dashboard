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
  });

  // The ladder's bars grow out from the average line once, on first load (CSS skips it for reduced motion).
  requestAnimationFrame(function () {
    requestAnimationFrame(function () { document.documentElement.classList.remove("preload"); });
  });
})();
