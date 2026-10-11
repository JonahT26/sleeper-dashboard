// Motion (UI_GUIDE.md "Motion"): GSAP with its ScrollTrigger, Flip and SplitText plugins, and Lenis, all bundled in js/.
// The title, count-up and scroll-reveal effects follow react-bits' SplitText, CountUp and AnimatedContent, rebuilt
// without React. Everything here runs only while the viewer hasn't asked for reduced motion, and the page is complete
// without it: if a script is missing or anything fails, everything shows at once, as written by Python.
(function () {
  var root = document.documentElement;
  if (!root.classList.contains("motion")) return;  // reduced motion requested (the head script decides)
  var view = document.getElementById("week-view");
  var title = document.getElementById("title");
  var REVEAL = "main section:not(.ladder-section)";  // every section after the ladder, History and How this works included

  // Starts once the last bundled script has run (deferred scripts run in page order, all after this one), without
  // waiting for Plotly; if it fails to load, there's no motion and nothing stays hidden.
  var scripts = document.getElementById("motion-scripts");
  scripts.addEventListener("load", begin);
  scripts.addEventListener("error", begin);
  function begin() {
    var onTime = root.classList.contains("motion-wait");  // false once the head script's 3-second limit has shown everything
    try {
      if (window.gsap && window.ScrollTrigger && window.Flip && window.SplitText && window.Lenis) start(onTime);
      else root.classList.remove("motion");
    } finally {
      root.classList.remove("motion-wait");
    }
  }

  function start(onTime) {
    gsap.registerPlugin(ScrollTrigger, Flip, SplitText);
    var first = true;
    // Reverts everything (styles, split title, numbers) if the viewer turns reduced motion on while the page is open.
    gsap.matchMedia().add("(prefers-reduced-motion: no-preference)", function () {
      var intro = first && onTime;
      first = false;
      var running = [], counts = [], split = null, before = null;

      // Smooth scrolling for the mouse wheel and trackpad (touch scrolling stays the phone's own), on GSAP's clock so
      // ScrollTrigger sees every frame: the Lenis README's GSAP setup. Wide tables keep their own sideways scroll.
      var lenis = new Lenis({ allowNestedScroll: true, anchors: true });
      lenis.on("scroll", ScrollTrigger.update);
      function tick(time) { lenis.raf(time * 1000); }
      gsap.ticker.add(tick);
      gsap.ticker.lagSmoothing(0);

      // A number runs from `from` to the value Python wrote (react-bits CountUp), then the written text is put back exactly.
      function countUp(el, from, duration) {
        var node = el && el.lastChild;
        var m = node && node.nodeType === 3 && /^(.*?)(\d+)(\.\d+)?(\D*)$/.exec(node.nodeValue);
        if (!m || typeof from !== "number" || isNaN(from)) return null;
        var text = node.nodeValue, places = m[3] ? m[3].length - 1 : 0, counter = { v: from };
        function show() { node.nodeValue = m[1] + counter.v.toFixed(places) + m[4]; }
        counts.push({ node: node, text: text });
        show();
        return gsap.to(counter, { v: parseFloat(m[2] + (m[3] || "")), duration: duration, ease: "power2.out",
                                  onUpdate: show, onComplete: function () { node.nodeValue = text; } });
      }
      function scoreOf(row) {
        var node = row.querySelector(".l3 .val").lastChild;
        return node ? parseFloat(node.nodeValue) : NaN;
      }
      function rowsOf() {
        var rows = view.querySelectorAll(".ladder .team");
        rows.forEach(function (row) { row.dataset.flipId = "team-" + row.dataset.roster; });  // Flip pairs rows across weeks
        return rows;
      }

      // First load: the title rises in word by word, the ladder rows follow one after another, and each bar grows out
      // from the average line while its score counts up from the league average (50).
      if (intro) {
        var tl = gsap.timeline({ defaults: { ease: "power3.out" } });
        split = SplitText.create(title, { type: "words" });
        tl.from(split.words, { yPercent: 60, opacity: 0, duration: 0.7, stagger: 0.06 }, 0);
        var rows = rowsOf();
        tl.from(rows, { y: 16, opacity: 0, duration: 0.5, stagger: 0.04 }, 0.15);
        // Both ends given: the CSS may still hold the bars at zero (.preload) when this starts
        tl.fromTo(view.querySelectorAll(".ladder .l3 .fill"), { scaleX: 0 }, { scaleX: 1, duration: 0.8, stagger: 0.04 }, 0.25);
        rows.forEach(function (row, i) {
          var count = countUp(row.querySelector(".l3 .val"), 50, 0.8);
          if (count) tl.add(count, 0.25 + i * 0.04);
        });
        running.push(tl);
      }

      // Sections after the ladder rise and fade in once, as each scrolls into view (react-bits AnimatedContent);
      // weekly award values count up from 0 as theirs arrives. After the first load only sections still below the
      // screen take part, so nothing already seen disappears. Opacity only, never visibility, so a waiting section's
      // buttons stay in the Tab order, and tabbing to one scrolls it into view, which reveals it.
      var reveal = Array.prototype.filter.call(document.querySelectorAll(REVEAL), function (el) {
        return intro || el.getBoundingClientRect().top > window.innerHeight;
      });
      if (reveal.length) {
        gsap.set(reveal, { opacity: 0, y: 24 });
        ScrollTrigger.batch(reveal, { start: "top 92%", once: true, onEnter: function (batch) {
          running.push(gsap.to(batch, { opacity: 1, y: 0, duration: 0.7, ease: "power3.out", stagger: 0.08 }));
          batch.forEach(function (section) {
            section.querySelectorAll(".award-value").forEach(function (el) {
              var count = countUp(el, 0, 0.9);
              if (count) running.push(count);
            });
          });
        } });
      }

      // Switching weeks: whatever is still moving finishes at once, so a week put away comes back whole. The ladder
      // rows then slide from their old places to their new ones (Flip), each bar stretches from its old length, and
      // each score counts from its old value.
      function leave() {
        running.forEach(function (t) { t.progress(1); });
        running = [];
        ScrollTrigger.getAll().forEach(function (st) { if (view.contains(st.trigger)) st.kill(); });
        gsap.set(view.querySelectorAll(REVEAL), { clearProps: "opacity,transform" });
        if (split) { split.revert(); split = null; }  // page.js writes the new week's title next
        var rows = rowsOf();
        before = { state: Flip.getState(rows), bars: {}, scores: {} };
        rows.forEach(function (row) {
          var fill = row.querySelector(".l3 .fill");
          before.bars[row.dataset.roster] = { left: fill.style.left, width: fill.style.width };
          before.scores[row.dataset.roster] = scoreOf(row);
        });
      }
      function shown() {
        var tl = gsap.timeline({ defaults: { ease: "power2.inOut" } });
        split = SplitText.create(title, { type: "words" });
        tl.from(split.words, { yPercent: 60, opacity: 0, duration: 0.5, stagger: 0.04, ease: "power3.out" }, 0);
        var rows = rowsOf();
        if (before) {
          tl.add(Flip.from(before.state, { targets: rows, duration: 0.6, ease: "power2.inOut", simple: true }), 0);
          rows.forEach(function (row) {
            var was = before.bars[row.dataset.roster];
            if (was) tl.from(row.querySelector(".l3 .fill"), { left: was.left, width: was.width, duration: 0.6 }, 0);
            var count = countUp(row.querySelector(".l3 .val"), before.scores[row.dataset.roster], 0.6);
            if (count) tl.add(count, 0);
          });
        }
        tl.from(view.querySelectorAll(REVEAL), { opacity: 0, y: 12, duration: 0.4, stagger: 0.05, ease: "power3.out" }, 0.1);
        running.push(tl);
        before = null;
        ScrollTrigger.refresh();
      }
      view.addEventListener("weekleave", leave);
      view.addEventListener("weekshown", shown);

      return function () {
        view.removeEventListener("weekleave", leave);
        view.removeEventListener("weekshown", shown);
        running.forEach(function (t) { t.progress(1); });
        counts.forEach(function (c) { c.node.nodeValue = c.text; });  // reverting skips onComplete, so put each number back
        if (split) split.revert();
        gsap.ticker.remove(tick);
        gsap.ticker.lagSmoothing(500, 33);  // GSAP's default
        lenis.destroy();
      };
    });
  }
})();
