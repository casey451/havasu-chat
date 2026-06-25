/* Home + calendar redesign — progressive enhancement only.
 * Every interaction here upgrades server-rendered HTML that already works
 * without JS: sections are open/closed via class, count pills + jump items are
 * real links to /events-ui, the gas panel is a link target, day + calendar cells
 * are real links. JS just makes them in-place. Honors prefers-reduced-motion via
 * CSS (transitions are disabled there; behavior is unchanged). */
(function () {
  "use strict";

  /* ---- scroll-shrink header ------------------------------------------- */
  var body = document.getElementById("rd-body") || document.body;
  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () {
      body.classList.toggle("scrolled", window.scrollY > 8);
      ticking = false;
    });
  }
  window.addEventListener("scroll", onScroll, { passive: true });

  /* ---- gas top-5 expander --------------------------------------------- */
  var gasTile = document.getElementById("gasTile");
  var gasPanel = document.getElementById("gasPanel");
  if (gasTile && gasPanel) {
    gasTile.addEventListener("click", function () {
      var open = gasPanel.classList.toggle("open");
      gasTile.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* Sections are native <details> — open/close + keyboard work with no JS. */
  var sections = document.getElementById("sections");

  /* ---- count overview filter ------------------------------------------ */
  var counts = document.getElementById("counts");
  function applyFilter(key) {
    if (!sections) return;
    var secs = sections.querySelectorAll(".sec");
    for (var i = 0; i < secs.length; i++) {
      var s = secs[i];
      var show = key === "all" || s.getAttribute("data-k") === key;
      s.classList.toggle("hidden", !show);
      if (key !== "all" && show) s.open = true; // <details> open the focused bucket
    }
    // In-feed ads only read right when the full list is shown.
    var ads = sections.querySelectorAll(".adslot.infeed");
    for (var j = 0; j < ads.length; j++) ads[j].style.display = key === "all" ? "" : "none";
  }
  if (counts) {
    counts.addEventListener("click", function (e) {
      var pill = e.target.closest(".cpill");
      if (!pill) return;
      var key = pill.getAttribute("data-k");
      if (key === "movies") return; // movies has its own page; let the link work
      e.preventDefault();
      var pills = counts.querySelectorAll(".cpill");
      for (var i = 0; i < pills.length; i++) pills[i].classList.remove("on");
      pill.classList.add("on");
      applyFilter(key);
    });
  }

  /* ---- jump-to-category dropdown -------------------------------------- */
  var jump = document.getElementById("jump");
  if (jump) {
    var btn = jump.querySelector(".dd-btn");
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = jump.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function () {
      jump.classList.remove("open");
      btn.setAttribute("aria-expanded", "false");
    });
    jump.querySelector(".dd-menu").addEventListener("click", function (e) {
      var item = e.target.closest("[data-k]");
      if (!item) return;
      var key = item.getAttribute("data-k");
      if (key === "movies") return; // let the /movies link work
      e.preventDefault();
      jump.classList.remove("open");
      btn.setAttribute("aria-expanded", "false");
      // reset any active count filter so the jumped-to section is visible
      if (counts) {
        var pills = counts.querySelectorAll(".cpill");
        for (var i = 0; i < pills.length; i++) pills[i].classList.remove("on");
        var all = counts.querySelector('[data-k="all"]');
        if (all) all.classList.add("on");
      }
      applyFilter("all");
      var sec = document.getElementById("sec-" + key);
      if (sec) {
        sec.open = true;
        if (sec.scrollIntoView) sec.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  }
})();
