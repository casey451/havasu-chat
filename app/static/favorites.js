(function () {
  function showToast(msg) {
    var el = document.getElementById('fav-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'fav-toast';
      el.className = 'fav-toast';
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(function () { el.classList.remove('show'); }, 1400);
  }

  function wire(btn) {
    var entityId = btn.getAttribute('data-entity-id') || '';
    if (!entityId) return;
    btn.addEventListener('click', function () {
      fetch('/api/favorites/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_id: entityId }),
      })
        .then(function (r) {
          if (r.status === 401) return null;
          if (!r.ok) return r.json().then(function (j) { throw new Error((j && j.detail) || 'error'); });
          return r.json();
        })
        .then(function (data) {
          if (!data) return;
          if (data.action === 'added') {
            btn.classList.add('is-saved');
            showToast('Saved!');
          } else {
            btn.classList.remove('is-saved');
            showToast('Removed');
          }
        })
        .catch(function () { showToast('Could not update'); });
    });
  }

  function init() {
    var body = document.body;
    var uid = body.getAttribute('data-current-user') || '';
    var hearts = document.querySelectorAll('.favorite-heart');
    if (!uid) {
      hearts.forEach(function (h) { h.setAttribute('hidden', 'hidden'); });
      return;
    }
    hearts.forEach(function (h) {
      h.removeAttribute('hidden');
      wire(h);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
