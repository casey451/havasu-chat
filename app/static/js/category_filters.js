/**
 * Phase 6.2 — category landing chip + sort interactions (vanilla JS).
 * Links remain functional without JS; the sort <select> navigates via change handler.
 */
(function () {
  "use strict";

  function initSortSelect() {
    var sel = document.querySelector("[data-category-sort]");
    if (!sel) {
      return;
    }
    sel.addEventListener("change", function () {
      var url = sel.value;
      if (url) {
        window.location.assign(url);
      }
    });
  }

  /** Keeps chip anchors primary; optional keyboard activation parity for buttons if added later. */
  function initChipRows() {
    document.querySelectorAll("[data-category-chip]").forEach(function (el) {
      el.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          el.click();
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initSortSelect();
      initChipRows();
    });
  } else {
    initSortSelect();
    initChipRows();
  }
})();
