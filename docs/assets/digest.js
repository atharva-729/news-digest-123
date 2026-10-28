/* L1·L2·L3 page behaviour. Plain JS, no dependencies. Every page works without it, just less fun. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- theme: auto -> light -> dark ---------- */
  var THEMES = ["auto", "light", "dark"];
  function getTheme() { try { return localStorage.getItem("l123-theme") || "auto"; } catch (e) { return "auto"; } }
  function setTheme(t) {
    if (t === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("l123-theme", t); } catch (e) {}
    var label = $(".theme-label");
    if (label) label.textContent = t.charAt(0).toUpperCase() + t.slice(1);
    requestAnimationFrame(drawMap);
  }
  var themeBtn = $(".theme-btn");
  if (themeBtn) {
    setTheme(getTheme());
    themeBtn.addEventListener("click", function () {
      setTheme(THEMES[(THEMES.indexOf(getTheme()) + 1) % THEMES.length]);
    });
  }

  /* ---------- tabs (#feed, #means, #play) ---------- */
  var tabs = $$("[data-tab]");
  var panels = $$("[data-panel]");
  function showTab(name, keepScroll) {
    if (!panels.length) return;
    if (!panels.some(function (p) { return p.dataset.panel === name; })) name = panels[0].dataset.panel;
    panels.forEach(function (p) { p.hidden = p.dataset.panel !== name; });
    tabs.forEach(function (t) { t.setAttribute("aria-selected", String(t.dataset.tab === name)); });
    if (location.hash.slice(1) !== name) history.replaceState(null, "", "#" + name);
    if (!keepScroll) window.scrollTo(0, 0);
    requestAnimationFrame(drawMap);
  }
  tabs.forEach(function (t) { t.addEventListener("click", function () { showTab(t.dataset.tab); }); });
  window.addEventListener("hashchange", function () { showTab(location.hash.slice(1)); });
  if (panels.length) showTab(location.hash.slice(1), true);

  function flash(el) {
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
  }

  /* links between tabs: [data-tab-link] switches tab, [data-scroll] then scrolls to an element */
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest("[data-tab-link]");
    if (a) {
      ev.preventDefault();
      showTab(a.dataset.tabLink, !!a.dataset.scroll);
      if (a.dataset.scroll) {
        resetFilter();
        requestAnimationFrame(function () { flash(document.getElementById(a.dataset.scroll)); });
      }
      return;
    }
    var g = ev.target.closest("[data-goto]");
    if (g) {
      showTab("means", true);
      resetForceFilter();
      requestAnimationFrame(function () { flash(document.getElementById(g.dataset.goto)); });
      return;
    }
    var f = ev.target.closest("[data-force-link]");
    if (f) {
      showTab("means", true);
      applyForceFilter(f.dataset.forceLink);
      requestAnimationFrame(function () { var t = $(".threads"); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); });
    }
  });

  /* ---------- feed filters ---------- */
  var filters = $$("[data-filter]");
  function applyFilter(key) {
    filters.forEach(function (b) { b.classList.toggle("is-on", b.dataset.filter === key); });
    $$(".sec-block").forEach(function (s) { s.hidden = key !== "all" && s.dataset.section !== key; });
  }
  function resetFilter() { if (filters.length) applyFilter("all"); }
  filters.forEach(function (b) { b.addEventListener("click", function () { applyFilter(b.dataset.filter); }); });

  /* ---------- pattern filter by force ---------- */
  var ffs = $$("[data-ff]");
  function applyForceFilter(key) {
    ffs.forEach(function (b) { b.classList.toggle("is-on", b.dataset.ff === key); });
    $$(".thread").forEach(function (t) {
      t.classList.toggle("is-hidden", key !== "all" && (" " + t.dataset.forces + " ").indexOf(" " + key + " ") < 0);
    });
  }
  function resetForceFilter() { if (ffs.length) applyForceFilter("all"); }
  ffs.forEach(function (b) { b.addEventListener("click", function () { applyForceFilter(b.dataset.ff); }); });

  /* ---------- the map: lines from L1 -> L2 -> L3 ---------- */
  var map = $(".map");
  function colorOf(el) { return getComputedStyle(el).getPropertyValue("--c").trim() || getComputedStyle(el).color; }
  function drawMap() {
    if (!map || !map.offsetParent) return;
    var svg = $(".map-lines", map), box = map.getBoundingClientRect();
    svg.setAttribute("viewBox", "0 0 " + box.width + " " + box.height);
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    $$("[data-to]", map).forEach(function (n) {
      n.dataset.to.trim().split(/\s+/).forEach(function (id) {
        var m = $('[data-id="' + id + '"]', map);
        if (!m) return;
        var a = n.getBoundingClientRect(), b = m.getBoundingClientRect();
        var x1 = a.right - box.left, y1 = a.top + a.height / 2 - box.top;
        var x2 = b.left - box.left, y2 = b.top + b.height / 2 - box.top, dx = (x2 - x1) / 2;
        var p = document.createElementNS("http://www.w3.org/2000/svg", "path");
        p.setAttribute("d", "M" + x1 + "," + y1 + " C" + (x1 + dx) + "," + y1 + " " + (x2 - dx) + "," + y2 + " " + x2 + "," + y2);
        p.style.stroke = n.classList.contains("n1") ? colorOf(n) : colorOf(m);
        p.dataset.a = n.dataset.id; p.dataset.b = id;
        svg.appendChild(p);
      });
    });
  }
  // Node ids: i-* headlines (L1), t-* threads (L2), f-* forces (L3). Edges run i -> t and t -> f.
  function trace(id) {
    var lit = {}; lit[id] = true;
    var paths = $$("path", map);
    var edges = paths.map(function (p) { return [p.dataset.a, p.dataset.b]; });
    var kind = id.charAt(0);
    if (kind === "i") {        // a headline: its thread, then that thread's forces
      edges.forEach(function (e) { if (e[0] === id) lit[e[1]] = true; });
      edges.forEach(function (e) { if (e[0].charAt(0) === "t" && lit[e[0]]) lit[e[1]] = true; });
    } else if (kind === "t") { // a thread: every headline feeding it and every force behind it
      edges.forEach(function (e) { if (e[1] === id) lit[e[0]] = true; if (e[0] === id) lit[e[1]] = true; });
    } else {                   // a force: its threads, then the headlines feeding those threads
      edges.forEach(function (e) { if (e[1] === id) lit[e[0]] = true; });
      edges.forEach(function (e) { if (e[1].charAt(0) === "t" && lit[e[1]]) lit[e[0]] = true; });
    }
    map.classList.add("is-tracing");
    $$(".node", map).forEach(function (n) { n.classList.toggle("lit", !!lit[n.dataset.id]); });
    paths.forEach(function (p) { p.classList.toggle("lit", !!(lit[p.dataset.a] && lit[p.dataset.b])); });
  }
  function untrace() {
    if (!map) return;
    map.classList.remove("is-tracing");
    $$(".lit", map).forEach(function (n) { n.classList.remove("lit"); });
  }
  if (map) {
    $$(".node", map).forEach(function (n) {
      n.addEventListener("mouseenter", function () { trace(n.dataset.id); });
      n.addEventListener("mouseleave", untrace);
      n.addEventListener("click", function () { n.classList.contains("lit") && map.classList.contains("is-tracing") ? untrace() : trace(n.dataset.id); });
    });
    window.addEventListener("resize", function () { requestAnimationFrame(drawMap); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(drawMap);
    window.addEventListener("load", drawMap);
  }

  /* ---------- quiz ---------- */
  $$(".quiz").forEach(function (quiz) {
    var score = 0, answered = 0, total = +quiz.dataset.total;
    $$(".q", quiz).forEach(function (q) {
      var right = +q.dataset.answer;
      $$(".opt", q).forEach(function (o) {
        o.addEventListener("click", function () {
          var pick = +o.dataset.i;
          $$(".opt", q).forEach(function (x) {
            x.disabled = true;
            if (+x.dataset.i === right) x.classList.add("is-right");
          });
          if (pick === right) score++; else o.classList.add("is-wrong");
          $(".why", q).hidden = false;
          $(".score-n", quiz).textContent = score;
          if (++answered === total) {
            var done = $(".quiz-done", quiz);
            done.textContent = score === total ? "All right. It's sticking. 🧠" : "Got " + score + "/" + total + ". Wrong answers still help you remember; the explanations above are the bit to keep.";
            done.hidden = false;
          }
        });
      });
    });
  });

  /* ---------- reading progress ---------- */
  var bar = $(".progress span");
  if (bar) {
    var onScroll = function () {
      var h = document.documentElement.scrollHeight - innerHeight;
      bar.style.width = (h > 0 ? Math.min(100, (scrollY / h) * 100) : 0) + "%";
    };
    addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }
})();
