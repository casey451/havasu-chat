/**
 * Phase 6.4 — debounced inline catalog search (distinct from Ask Hava composer).
 */
(function () {
  var DEBOUNCE_MS = 300;

  function esc(s) {
    var t = document.createTextNode(s == null ? '' : String(s));
    var d = document.createElement('div');
    d.appendChild(t);
    return d.innerHTML;
  }

  function renderHits(container, rows) {
    container.innerHTML = '';
    if (!rows || !rows.length) {
      container.removeAttribute('hidden');
      var empty = document.createElement('div');
      empty.className = 'hava-search-results-empty';
      empty.textContent = 'No matches yet.';
      container.appendChild(empty);
      return;
    }
    var max = Math.min(8, rows.length);
    for (var i = 0; i < max; i++) {
      var r = rows[i];
      var href = r.profile_url || '/home';
      var a = document.createElement('a');
      a.className = 'hava-search-hit';
      a.href = href;
      var name = document.createElement('div');
      name.className = 'hava-search-hit-name';
      name.innerHTML = esc(r.name);
      var meta = document.createElement('div');
      meta.className = 'hava-search-hit-meta';
      var bits = [];
      if (r.entity_type) bits.push(r.entity_type);
      if (r.district) bits.push(r.district);
      meta.innerHTML = esc(bits.join(' · '));
      a.appendChild(name);
      a.appendChild(meta);
      container.appendChild(a);
    }
    container.removeAttribute('hidden');
  }

  function bindForm(form) {
    var input = form.querySelector('.hava-search-input, input[type="search"]');
    var results = form.querySelector('[data-hava-search-results]');
    if (!input || !results) return;

    var timer = null;

    function clearResults() {
      results.setAttribute('hidden', '');
      results.innerHTML = '';
    }

    function runSearch() {
      var q = (input.value || '').trim();
      if (!q) {
        clearResults();
        return;
      }
      var params = new URLSearchParams();
      params.set('q', q);
      params.set('limit', '8');
      fetch('/api/search?' + params.toString(), {
        method: 'GET',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      })
        .then(function (res) {
          if (!res.ok) throw new Error('search_failed');
          return res.json();
        })
        .then(function (data) {
          renderHits(results, data.results || []);
        })
        .catch(function () {
          renderHits(results, []);
        });
    }

    function scheduleSearch() {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(runSearch, DEBOUNCE_MS);
    }

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      runSearch();
    });

    input.addEventListener('input', scheduleSearch);

    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') {
        input.value = '';
        clearResults();
        input.blur();
      }
    });

    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && document.activeElement === input) {
        input.value = '';
        clearResults();
      }
    });

    document.addEventListener('click', function (ev) {
      if (!form.contains(ev.target)) clearResults();
    });
  }

  document.querySelectorAll('[data-hava-search]').forEach(bindForm);
})();
