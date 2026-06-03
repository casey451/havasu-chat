/* Ask Hava — Sandstone category page: in-place subcategory chip filtering.
   Progressive enhancement: the chips are real <a> facet links (work without JS,
   server filters + SEO). With JS we intercept and filter the already-rendered
   grid in place — no page reload feel (01_UI_BUILD_GUIDE.md §4.8). The weighted
   "Locals' favorites" sort and the Open-now/Closest pills stay server-side
   (they need a re-query), so those remain normal links. */
(function () {
  "use strict";

  function init() {
    var chipBar = document.getElementById("chips");
    var grid = document.getElementById("bizGrid");
    if (!chipBar || !grid) return;

    var chips = chipBar.querySelectorAll(".chip");
    var cards = grid.querySelectorAll(".biz[data-subcategory]");

    chipBar.addEventListener("click", function (e) {
      var chip = e.target.closest(".chip");
      if (!chip) return;
      var filter = chip.dataset.filter;
      if (!filter) return;
      // Only enhance when the full set is present (the unfiltered grid). If the
      // server already narrowed to one subcategory, let the link navigate.
      if (filter !== "all" && cards.length === 0) return;
      e.preventDefault();
      for (var i = 0; i < chips.length; i++) chips[i].classList.remove("on");
      chip.classList.add("on");
      for (var j = 0; j < cards.length; j++) {
        var show = filter === "all" || cards[j].dataset.subcategory === filter;
        cards[j].style.display = show ? "" : "none";
      }
      // Reflect the filter in the URL without a reload (shareable / back-button).
      try {
        var url = filter === "all" ? chip.getAttribute("href") : chip.getAttribute("href");
        if (url) window.history.replaceState(null, "", url);
      } catch (err) { /* ignore */ }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
