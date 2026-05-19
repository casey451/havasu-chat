/**
 * Phase 6.4 — boat-access mode toggle (URL > localStorage > user preference).
 */
(function () {
  var STORAGE_KEY = 'hava.boat_mode';
  var BOAT_PARAM = 'boat';
  var BOAT_VALUE = '1';

  function parseBoatFromUrl() {
    try {
      var params = new URLSearchParams(window.location.search);
      if (!params.has(BOAT_PARAM)) return null;
      var v = (params.get(BOAT_PARAM) || '').trim().toLowerCase();
      return v === '1' || v === 'true' || v === 'yes';
    } catch (_e) {
      return null;
    }
  }

  function readLocalBoat() {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === '1';
    } catch (_e) {
      return false;
    }
  }

  function writeLocalBoat(on) {
    try {
      window.localStorage.setItem(STORAGE_KEY, on ? '1' : '0');
    } catch (_e) {
      /* ignore */
    }
  }

  function resolveBoatActive() {
    var fromUrl = parseBoatFromUrl();
    if (fromUrl !== null) return fromUrl;
    return readLocalBoat();
  }

  function setUrlBoatParam(on) {
    try {
      var url = new URL(window.location.href);
      if (on) {
        url.searchParams.set(BOAT_PARAM, BOAT_VALUE);
      } else {
        url.searchParams.delete(BOAT_PARAM);
      }
      window.history.replaceState({}, '', url.toString());
    } catch (_e) {
      /* ignore */
    }
  }

  function syncDom(on) {
    document.body.classList.toggle('boat-mode-active', !!on);
    document.querySelectorAll('[data-boat-mode-toggle]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      btn.classList.toggle('boat-mode-toggle--active', !!on);
    });
    document.dispatchEvent(
      new CustomEvent('hava:boat-mode', { detail: { active: !!on } })
    );
  }

  function postUserPreference(on) {
    fetch('/api/users/me/boat_mode_preference', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ enabled: !!on }),
    }).catch(function () {
      /* anonymous or offline — localStorage only */
    });
  }

  function applyBoatMode(on, opts) {
    opts = opts || {};
    writeLocalBoat(on);
    if (opts.syncUrl !== false) setUrlBoatParam(on);
    syncDom(on);
    if (opts.persistUser) postUserPreference(on);
  }

  function bindToggle(btn) {
    btn.addEventListener('click', function () {
      var next = !document.body.classList.contains('boat-mode-active');
      applyBoatMode(next, { syncUrl: true, persistUser: true });
      if (optsReloadOnToggle()) {
        window.location.reload();
      }
    });
  }

  function optsReloadOnToggle() {
    return document.body.hasAttribute('data-boat-reload-on-toggle');
  }

  function init() {
    var active = resolveBoatActive();
    var urlHad = parseBoatFromUrl();
    if (urlHad !== null) writeLocalBoat(active);
    applyBoatMode(active, { syncUrl: false, persistUser: false });
    document.querySelectorAll('[data-boat-mode-toggle]').forEach(bindToggle);
  }

  window.HavaBoatMode = {
    parseBoatFromUrl: parseBoatFromUrl,
    readLocalBoat: readLocalBoat,
    resolveBoatActive: resolveBoatActive,
    applyBoatMode: applyBoatMode,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
