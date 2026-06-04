/* Ask Hava -- Sandstone front-end behaviors.
   Progressive enhancement only: every link/form works without JS. The four mode
   controls are real <a> links to /home, /lake, /night, /family, so each landing
   loads server-side pre-themed (incl. the Night dark transformation) with no JS.
   This file wires the Explore mega-menu (a plain disclosure), the mobile
   hamburger drawer (a real menu, not a mode-cycle no-op), and the rotating
   search placeholder (Ask only). No fabricated data -- purely presentational. */
(function () {
  "use strict";

  // ---- Mobile hamburger -> real disclosure menu ----
  // Opens the #nav-drawer panel. Without JS the menu is hidden and the page's
  // bottom-nav / header links still cover navigation, so nothing is trapped.
  function wireMenuBtn() {
    var btn = document.getElementById("nav-menu-btn");
    var drawer = document.getElementById("nav-drawer");
    if (!btn || !drawer) return;
    function setOpen(open) {
      drawer.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    }
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      setOpen(drawer.hidden);
    });
    document.addEventListener("click", function (e) {
      if (!drawer.hidden && !e.target.closest("#nav-drawer") && e.target !== btn) {
        setOpen(false);
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !drawer.hidden) {
        setOpen(false);
        btn.focus();
      }
    });
  }

  // ---- Explore mega-menu (plain disclosure: aria-controls + hidden) ----
  function wireMega() {
    var trigger = document.getElementById("mega-trigger");
    var mega = document.getElementById("mega");
    if (!trigger || !mega) return;
    function setOpen(open) {
      mega.hidden = !open;
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
    }
    trigger.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      setOpen(mega.hidden);
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".explore")) setOpen(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !mega.hidden) {
        setOpen(false);
        trigger.focus();
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
