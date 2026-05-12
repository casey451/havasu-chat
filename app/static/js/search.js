/**
 * Phase 2B.3 — directory search: fetch /api/search and render top 8 hits.
 * Vanilla JS; no auth. Forms are marked with [data-directory-search].
 */
(function () {
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
      empty.className = 'directory-search-hit';
      empty.textContent = 'No matches yet.';
      container.appendChild(empty);
      return;
    }
    var max = Math.min(8, rows.length);
    for (var i = 0; i < max; i++) {
      var r = rows[i];
      var href = r.profile_url || '/home';
      var a = document.createElement('a');
      a.className = 'directory-search-hit';
      a.href = href;
      var name = document.createElement('div');
      name.className = 'name';
      name.innerHTML = esc(r.name);
      var meta = document.createElement('div');
      meta.className = 'meta';
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
    var results = form.querySelector('[data-directory-search-results]');
    if (!results) return;

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var fd = new FormData(form);
      var q = (fd.get('q') || '').toString().trim();
      if (!q) {
        results.setAttribute('hidden', '');
        results.innerHTML = '';
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
    });

    document.addEventListener('click', function (ev) {
      if (!form.contains(ev.target)) {
        results.setAttribute('hidden', '');
      }
    });
  }

  document.querySelectorAll('[data-directory-search]').forEach(bindForm);
})();
