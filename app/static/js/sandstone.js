/* Ask Hava — Sandstone front-end behaviors.
   Progressive enhancement only: every link/form works without JS. The four mode
   controls are real <a> links to /home, /lake, /night, /family, so each landing
   loads server-side pre-themed (incl. the Night dark transformation) with no JS.
   This file adds the Explore mega-menu, the rotating search placeholder (Ask
   only), and the mobile ☰ mode-cycle. No fabricated data — purely presentational. */
(function () {
  "use strict";

  var MODE_ORDER = ["ask", "lake", "night", "family"];
  var MODE_ROUTE = { ask: "/home", lake: "/lake", night: "/night", family: "/family" };

  // ---- Mobile mode-cycle (the ☰ button at <680px) ----
  // Falls back to its href when JS is off; with JS it advances to the NEXT mode
  // relative to the page's current mode.
  function wireMenuBtn() {
    var menuBtn = document.querySelector(".menu-btn[data-mode-cycle]");
    if (!menuBtn) return;
    menuBtn.addEventListener("click", function (e) {
      var cur = document.body.dataset.mode || "ask";
      var next = MODE_ORDER[(MODE_ORDER.indexOf(cur) + 1) % MODE_ORDER.length];
      if (MODE_ROUTE[next]) {
        e.preventDefault();
        window.location.href = MODE_ROUTE[next];
      }
    });
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
    wireMenuBtn();
    wireMega();
    wirePlaceholder();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
