/* Sandstone provider profile — Save-button behavior for logged-out viewers.
 *
 * Logged-in viewers: the Save button carries `.favorite-heart` + a
 * `data-entity-id`, so the shared `/static/favorites.js` wires it to
 * POST `/api/favorites/toggle` (real persistence). This file only handles the
 * anonymous case: send the viewer to login with a `next` back to this page,
 * so Save is never a dead end and never silently no-ops.
 */
(function () {
  function init() {
    var btn = document.querySelector('.fav-save[data-requires-login="1"]');
    if (!btn) return;
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var next = window.location.pathname + window.location.search;
      window.location.href = '/login?next=' + encodeURIComponent(next);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
