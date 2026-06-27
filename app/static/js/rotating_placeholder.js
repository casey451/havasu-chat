/**
 * Rotating search-box placeholder.
 *
 * Cycles example queries through the `placeholder` attribute of any input
 * tagged `data-rotating-placeholder`, so an idle search box advertises what it
 * can find. Opt-in by attribute (not hard-coded ids) so it stays reusable.
 *
 * Rules (the important part):
 *   - We only ever set the *placeholder*, never `value`. Focusing the field
 *     always leaves it empty and type-ready — nothing to erase.
 *   - Rotation runs only while the field is unfocused and empty. Focus or any
 *     typed text stops it; it resumes on blur if the field is still empty.
 *   - First frame shown is a real term, not the static HTML fallback.
 *   - `prefers-reduced-motion: reduce` -> show one static term, never cycle.
 *   - Pauses while the tab is hidden (no timer spinning in a background tab).
 *   - The placeholder is decorative: we never add aria-live (the inputs keep
 *     their static aria-label), and we never touch tab order / the submit
 *     button / the search icon.
 */
(function () {
  var INTERVAL_MS = 2500;

  // Edit freely — Havasu-flavored example searches. Rendered as: Search "<term>".
  var PLACEHOLDER_TERMS = [
    'pool cleaners',
    'electricians',
    'plumbers',
    'general contractors',
    'restaurants',
    'boat mechanics',
    'AC & heating repair',
    'landscapers',
    'handyman services',
    'auto repair',
    'house cleaners',
    'roofers',
    'pest control',
    'hair & nail salons',
    'dentists',
    'coffee shops',
    'boat rentals',
    'jet ski rentals',
    'real estate agents',
    'tow trucks',
  ];

  function label(term) {
    return 'Search "' + term + '"';
  }

  function prefersReducedMotion() {
    return !!(
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    );
  }

  function init(input) {
    var i = 0;
    var timer = null;

    function show(n) {
      input.setAttribute('placeholder', label(PLACEHOLDER_TERMS[n]));
    }

    function tick() {
      i = (i + 1) % PLACEHOLDER_TERMS.length;
      show(i);
    }

    function start() {
      if (timer !== null) return; // already running
      if (document.activeElement === input) return; // user is in the field
      if (input.value) return; // user has typed something
      if (document.hidden) return; // tab not visible
      timer = window.setInterval(tick, INTERVAL_MS);
    }

    function stop() {
      if (timer !== null) {
        window.clearInterval(timer);
        timer = null;
      }
    }

    // First frame is always a real term (overrides the static HTML fallback,
    // which stays in the markup for the no-JS / JS-failed case).
    show(0);

    // Reduced motion: one static term, no cycling, no listeners.
    if (prefersReducedMotion()) return;

    input.addEventListener('focus', stop);
    input.addEventListener('blur', function () {
      if (!input.value) start();
    });
    input.addEventListener('input', function () {
      if (input.value) stop();
    });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) stop();
      else start();
    });

    start();
  }

  var inputs = document.querySelectorAll('input[data-rotating-placeholder]');
  for (var k = 0; k < inputs.length; k++) init(inputs[k]);
})();
