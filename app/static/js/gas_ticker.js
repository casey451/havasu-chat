/* Home gas-price ticker (2026-05-29).
 * Fetches /api/gas and fills #gas-ticker-track with a scrolling list of
 * stations + regular prices. Hides the bar when there's no data so the
 * home page never shows an empty ticker. Track content is duplicated so the
 * CSS marquee (-50% translate) loops seamlessly. */
(function () {
  var bar = document.getElementById("gas-ticker");
  if (!bar) return;
  var track = document.getElementById("gas-ticker-track");
  if (!track) return;
  var url = bar.getAttribute("data-poll-url") || "/api/gas";

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function fmtPrice(p) {
    return p == null ? "n/a" : "$" + p;
  }

  function render(data) {
    var stations = (data && data.stations) || [];
    if (!stations.length) {
      bar.classList.remove("is-visible");
      return;
    }
    var parts = [];
    for (var i = 0; i < stations.length; i++) {
      var s = stations[i];
      var reg = s.prices && s.prices.regular;
      parts.push(
        '<span class="gt-item">' +
          escapeHtml(s.name || "Station") +
          ' <span class="gt-price">' +
          fmtPrice(reg) +
          "</span></span>"
      );
    }
    var html = parts.join("");
    // Duplicate so the -50% marquee wraps seamlessly.
    track.innerHTML = html + html;
    bar.classList.add("is-visible");
  }

  fetch(url, { credentials: "same-origin" })
    .then(function (r) {
      return r.json();
    })
    .then(render)
    .catch(function () {
      bar.classList.remove("is-visible");
    });
})();
