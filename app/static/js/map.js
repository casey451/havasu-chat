/**
 * Phase 6.4 — Leaflet + OSM map with marker clustering (CDN assets required).
 */
(function () {
  var MAP_COLLAPSED_KEY = 'hava.map_collapsed';
  var OSM_TILE = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  var OSM_ATTRIB =
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

  function boatActive() {
    if (window.HavaBoatMode && window.HavaBoatMode.resolveBoatActive) {
      return window.HavaBoatMode.resolveBoatActive();
    }
    try {
      return window.localStorage.getItem('hava.boat_mode') === '1';
    } catch (_e) {
      return false;
    }
  }

  function mapCollapsedDefault() {
    var wrap = document.querySelector('[data-map-scope]');
    if (wrap && wrap.getAttribute('data-map-default-expanded') === 'true') {
      return false;
    }
    return true;
  }

  function readCollapsed(scope) {
    try {
      var raw = window.localStorage.getItem(MAP_COLLAPSED_KEY + ':' + scope);
      if (raw === '0') return false;
      if (raw === '1') return true;
    } catch (_e) {
      /* ignore */
    }
    return mapCollapsedDefault();
  }

  function writeCollapsed(scope, collapsed) {
    try {
      window.localStorage.setItem(MAP_COLLAPSED_KEY + ':' + scope, collapsed ? '1' : '0');
    } catch (_e) {
      /* ignore */
    }
  }

  function boatQuery() {
    return boatActive() ? '&boat=1' : '';
  }

  function initMap(scopeSlug, container, toggleBtn) {
    if (!window.L || !container) return null;

    var map = window.L.map(container, { scrollWheelZoom: false });
    window.L.tileLayer(OSM_TILE, {
      maxZoom: 19,
      attribution: OSM_ATTRIB,
    }).addTo(map);

    var waterLayer = null;
    function syncWaterLayer() {
      if (boatActive()) {
        if (!waterLayer) {
          waterLayer = window.L.tileLayer(
            'https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png',
            { maxZoom: 18, opacity: 0.55, attribution: 'Seamarks &copy; OpenSeaMap' }
          );
          waterLayer.addTo(map);
        }
      } else if (waterLayer) {
        map.removeLayer(waterLayer);
        waterLayer = null;
      }
    }

    var clusterGroup = window.L.markerClusterGroup({ maxClusterRadius: 50 });
    map.addLayer(clusterGroup);

    function loadMarkers() {
      clusterGroup.clearLayers();
      fetch(
        '/api/map_data/' + encodeURIComponent(scopeSlug) + '?_=' + Date.now() + boatQuery(),
        { credentials: 'same-origin', headers: { Accept: 'application/json' } }
      )
        .then(function (res) {
          if (!res.ok) throw new Error('map_failed');
          return res.json();
        })
        .then(function (data) {
          (data.entities || []).forEach(function (row) {
            if (row.lat == null || row.lng == null) return;
            var m = window.L.marker([row.lat, row.lng]);
            var label = '<strong>' + (row.name || '') + '</strong>';
            if (row.status_line) label += '<br>' + row.status_line;
            m.bindPopup(label);
            m.on('click', function () {
              if (row.profile_url) window.location.href = row.profile_url;
            });
            clusterGroup.addLayer(m);
          });
          if (data.truncated_at_n) {
            container.setAttribute('data-map-truncated', 'true');
          } else {
            container.removeAttribute('data-map-truncated');
          }
          setTimeout(function () {
            try {
              map.invalidateSize();
              if (clusterGroup.getLayers().length) {
                map.fitBounds(clusterGroup.getBounds(), { padding: [24, 24], maxZoom: 14 });
              }
            } catch (_e) {
              /* empty */
            }
          }, 80);
        })
        .catch(function () {
          container.setAttribute('data-map-error', 'true');
        });
    }

    syncWaterLayer();
    loadMarkers();

    document.addEventListener('hava:boat-mode', function () {
      syncWaterLayer();
      loadMarkers();
    });

    return { map: map, reload: loadMarkers, syncWaterLayer: syncWaterLayer };
  }

  function bindPage() {
    var wrap = document.querySelector('[data-map-scope]');
    if (!wrap) return;
    var scope = wrap.getAttribute('data-map-scope');
    var container = document.getElementById('map-container');
    var toggleBtn = document.querySelector('[data-map-toggle]');
    if (!scope || !container || !toggleBtn) {
      // [data-map-scope] is present, so this IS a map page — a missing hook here
      // is a real wiring bug, not an off-page no-op. Surface it.
      console.warn('[map.js] map scope present but hooks missing:', {
        scope: !!scope,
        '#map-container': !!container,
        '[data-map-toggle]': !!toggleBtn,
      });
      return;
    }

    var collapsed = readCollapsed(scope);
    var mapApi = null;

    function setCollapsed(collapsed) {
      writeCollapsed(scope, collapsed);
      wrap.classList.toggle('map-wrap--collapsed', collapsed);
      container.hidden = collapsed;
      toggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      if (!collapsed) {
        if (!mapApi) mapApi = initMap(scope, container, toggleBtn);
        else {
          mapApi.reload();
          setTimeout(function () {
            if (mapApi.map) mapApi.map.invalidateSize();
          }, 120);
        }
      }
    }

    toggleBtn.addEventListener('click', function () {
      setCollapsed(!wrap.classList.contains('map-wrap--collapsed'));
    });

    setCollapsed(collapsed);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindPage);
  } else {
    bindPage();
  }
})();
