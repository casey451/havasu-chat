(function () {
  var strip = document.getElementById("conditions-strip");
  if (!strip) return;

  var pollUrl = strip.getAttribute("data-poll-url") || "/api/conditions";
  var pollMs = 60000;

  function formatAqiChip(data) {
    if (data.current_aqi == null) return null;
    var param = data.current_aqi_parameter || "AQI";
    var base = "AQI " + data.current_aqi + " (" + param + ")";
    if (data.aqi_source_station_name && data.aqi_source_state_code) {
      var dist = data.aqi_source_distance_mi
        ? " ~" + Math.round(data.aqi_source_distance_mi) + "mi south"
        : "";
      return base + " — from " + data.aqi_source_station_name + ", " + data.aqi_source_state_code + dist;
    }
    return base;
  }

  function refreshFromApi() {
    if (document.hidden) return;
    fetch(pollUrl, { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        var aqiTile = strip.querySelector('[data-kind="aqi"] .cond-tile__attribution');
        if (aqiTile) {
          var chip = formatAqiChip(data);
          if (chip) aqiTile.textContent = chip;
        }
      })
      .catch(function () {});
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) refreshFromApi();
  });
  setInterval(refreshFromApi, pollMs);
})();
