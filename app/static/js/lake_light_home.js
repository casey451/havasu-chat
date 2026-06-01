(function () {
  "use strict";

  const input = document.getElementById("home-ask-input");
  if (!input) return;

  const prompts = [
    "happy hour near the channel tonight",
    "dog groomers open Saturday",
    "boat rentals for 6",
    "pickleball courts open now",
    "kids activities this weekend",
  ];

  let idx = 0;
  window.setInterval(function () {
    idx = (idx + 1) % prompts.length;
    input.placeholder = prompts[idx];
  }, 2600);

  document.querySelectorAll(".ll-chip[data-q]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const q = btn.getAttribute("data-q") || "";
      input.value = q;
      const form = document.getElementById("home-ask-form");
      if (form) form.submit();
    });
  });
})();
