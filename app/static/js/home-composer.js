/**
 * Composer placeholder cycling — §B5.3.1
 *
 * On page load, cycles through 10 audit-verified example queries every 4 seconds
 * with a 280ms fade. Halts on focus, resumes on blur if input is empty.
 * Respects prefers-reduced-motion: reduce.
 */

(() => {
  const input = document.querySelector('.hero .composer input');
  if (!input) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const initial = "Ask Hava — what's open, what's on, who to call…";

  // Every example below maps to a documented intent or filter the backend
  // can actually answer today. Verified against intent_classifier.py +
  // tier2_db_query.py + Tier2Filters schema. See spec §B5.3.1.
  const examples = [
    "Ask Hava — What's going on tonight?",
    "Ask Hava — Find me a plumber",
    "Ask Hava — When does the Aquatic Center open?",
    "Ask Hava — What's open right now?",
    "Ask Hava — Kids yoga in town",
    "Ask Hava — Coffee shops on McCulloch",
    "Ask Hava — What's on this weekend?",
    "Ask Hava — What time does Mudshark close?",
    "Ask Hava — Library hours for Saturday",
    "Ask Hava — Programs for 8-year-olds"
  ].sort(() => Math.random() - 0.5);

  const HOLD_INITIAL_MS = 3000, HOLD_PER_MS = 4000, FADE_MS = 280;
  let index = -1, timer = null, cycling = false;

  function applyNext() {
    index = (index + 1) % examples.length;
    input.style.transition = "opacity " + FADE_MS + "ms ease";
    input.style.opacity = "0";
    setTimeout(() => { input.placeholder = examples[index]; input.style.opacity = "1"; }, FADE_MS);
  }

  function start() {
    if (cycling) return;
    cycling = true;
    timer = setTimeout(function tick() { applyNext(); timer = setTimeout(tick, HOLD_PER_MS); }, HOLD_INITIAL_MS);
  }

  function stop() {
    cycling = false;
    if (timer) { clearTimeout(timer); timer = null; }
    input.style.opacity = "1";
    if (!input.value) input.placeholder = initial;
  }

  input.addEventListener("focus", stop);
  input.addEventListener("blur", () => { if (!input.value) start(); });
  start();
})();
