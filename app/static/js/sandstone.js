/* Ask Hava — Sandstone front-end behaviors.
   Progressive enhancement only: every link/form works without JS. This adds the
   live mode re-theming (incl. the Night dark transformation), the Explore
   mega-menu, the rotating search placeholder (Ask mode only), and the mobile
   mode-cycle button. No fabricated data — purely presentational. */
(function () {
  "use strict";

  var MODE_ORDER = ["ask", "lake", "night", "family"];
  var STORAGE_KEY = "hava.mode";

  function applyMode(mode) {
    if (MODE_ORDER.indexOf(mode) === -1) mode = "ask";
    document.body.dataset.mode = mode;
    var btns = document.querySelectorAll("#modes button");
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle("on", btns[i].dataset.mode === mode);
    }
    try { localStorage.setItem(STORAGE_KEY, mode); } catch (e) { /* ignore */ }
  }

  // ---- Mode toggle ----
  // Buttons carry data-mode and (when a mode landing exists) an href. We re-theme
  // immediately for the live preview; if the button is a real link the browser
  // still navigates, so the landing page renders server-side in the chosen mode.
  function wireModes() {
    var modes = document.getElementById("modes");
    if (modes) {
      modes.addEventListener("click", function (e) {
        var btn = e.target.closest("button[data-mode]");
        if (!btn) return;
        applyMode(btn.dataset.mode);
      });
    }
    var menuBtn = document.querySelector(".menu-btn");
    if (menuBtn) {
      menuBtn.addEventListener("click", function () {
        var cur = document.body.dataset.mode || "ask";
        var next = MODE_ORDER[(MODE_ORDER.indexOf(cur) + 1) % MODE_ORDER.length];
        applyMode(next);
      });
    }
  }

  // ---- Explore mega-menu ----
  function wireMega() {
    var trigger = document.querySelector(".explore > .mega-trigger");
    var mega = document.getElementById("mega");
    if (!trigger || !mega) return;
    trigger.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var open = mega.classList.toggle("open");
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".explore")) {
        mega.classList.remove("open");
        trigger.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        mega.classList.remove("open");
        trigger.setAttribute("aria-expanded", "false");
      }
    });
  }

  // ---- Rotating search placeholder (Ask mode only) ----
  function wirePlaceholder() {
    var input = document.getElementById("home-ask-input");
    if (!input) return;
    var phrases = [
      "Mexican food near the channel",
      "Happy hour tonight",
      "Something to do with the kids",
      "Boat rental for Saturday",
      "A plumber today",
      "Best sunset patio",
    ];
    var i = 0;
    setInterval(function () {
      if ((document.body.dataset.mode || "ask") !== "ask") return;
      if (input === document.activeElement || input.value) return;
      i = (i + 1) % phrases.length;
      input.placeholder = phrases[i];
    }, 2700);
  }

  function init() {
    // Restore the persisted mode without clobbering a server-rendered landing
    // that already set its own mode (e.g. /lake renders with data-mode="lake").
    if (!document.body.dataset.mode || document.body.dataset.mode === "ask") {
      try {
        var saved = localStorage.getItem(STORAGE_KEY);
        if (saved) applyMode(saved);
      } catch (e) { /* ignore */ }
    }
    wireModes();
    wireMega();
    wirePlaceholder();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
