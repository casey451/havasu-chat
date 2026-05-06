// app/static/js/calendar.js
// Slice 61 (campaign #31 step 1/3): extracted from app/static/index.html
// (calendar IIFE, lines 878-1130). The IIFE wrapper is preserved because
// the body has a top-level early-return guard (if (!overlay || !btn) return;)
// that cannot live at module top level. Sets window.havasuChatCalendar as
// the cross-module bridge to chat.js; chat.js reads it defensively. Slice 3
// of the campaign refactors the bridge to explicit imports; this slice
// preserves the global pattern for behavior parity.

(function () {
  var overlay = document.getElementById("calendar-overlay");
  var btn = document.getElementById("calendar-btn");
  var titleEl = document.getElementById("cal-title");
  var gridEl = document.getElementById("cal-grid");
  var detailEl = document.getElementById("cal-day-detail");
  var prevBtn = document.getElementById("cal-prev");
  var nextBtn = document.getElementById("cal-next");
  var closeBtn = document.getElementById("cal-close");
  if (!overlay || !btn) return;

  var state = {
    year: new Date().getFullYear(),
    month: new Date().getMonth(),
    selectedKey: null,
    eventsByDate: null,
    loading: false,
  };

  var MONTH_LABELS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  function pad(n) { return n < 10 ? "0" + n : String(n); }
  function dateKey(y, m, d) { return y + "-" + pad(m + 1) + "-" + pad(d); }

  function isToday(y, m, d) {
    var t = new Date();
    return t.getFullYear() === y && t.getMonth() === m && t.getDate() === d;
  }

  function fmtTime(isoTime) {
    if (!isoTime) return "";
    var parts = isoTime.split(":");
    var h = parseInt(parts[0], 10);
    var m = parts[1] || "00";
    var ampm = h < 12 ? "AM" : "PM";
    var h12 = h % 12;
    if (h12 === 0) h12 = 12;
    return h12 + ":" + m + " " + ampm;
  }

  function loadEvents() {
    if (state.eventsByDate !== null || state.loading) return;
    state.loading = true;
    detailEl.innerHTML = '<div class="cal-loading">Loading events…</div>';
    fetch("/events", { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (events) {
        var map = {};
        (events || []).forEach(function (ev) {
          if (!ev || ev.status !== "live") return;
          var key = ev.date;
          if (!key) return;
          (map[key] = map[key] || []).push(ev);
        });
        Object.keys(map).forEach(function (k) {
          map[k].sort(function (a, b) {
            return (a.start_time || "").localeCompare(b.start_time || "");
          });
        });
        state.eventsByDate = map;
        state.loading = false;
        render();
      })
      .catch(function () {
        state.eventsByDate = {};
        state.loading = false;
        render();
      });
  }

  function renderGrid() {
    titleEl.textContent = MONTH_LABELS[state.month] + " " + state.year;
    gridEl.innerHTML = "";
    var first = new Date(state.year, state.month, 1);
    var leading = first.getDay();
    var daysInMonth = new Date(state.year, state.month + 1, 0).getDate();
    for (var i = 0; i < leading; i++) {
      var blank = document.createElement("div");
      blank.className = "cal-cell empty";
      gridEl.appendChild(blank);
    }
    for (var d = 1; d <= daysInMonth; d++) {
      var cell = document.createElement("button");
      cell.type = "button";
      cell.className = "cal-cell";
      cell.textContent = d;
      var key = dateKey(state.year, state.month, d);
      cell.setAttribute("data-key", key);
      if (isToday(state.year, state.month, d)) cell.classList.add("today");
      if (state.eventsByDate && state.eventsByDate[key]) cell.classList.add("has-events");
      if (state.selectedKey === key) cell.classList.add("selected");
      cell.addEventListener("click", (function (k) {
        return function () { selectDay(k); };
      })(key));
      gridEl.appendChild(cell);
    }
  }

  function renderDetail() {
    if (state.loading) {
      detailEl.innerHTML = '<div class="cal-loading">Loading events…</div>';
      return;
    }
    if (!state.selectedKey) {
      detailEl.innerHTML = '<div class="cal-empty-day">Tap a highlighted day to see what\'s on.</div>';
      return;
    }
    var events = (state.eventsByDate && state.eventsByDate[state.selectedKey]) || [];
    var parts = state.selectedKey.split("-");
    var y = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10) - 1;
    var d = parseInt(parts[2], 10);
    var label = MONTH_LABELS[m] + " " + d + ", " + y;
    var html = "<h3>" + label + "</h3>";
    if (events.length === 0) {
      html += '<div class="cal-empty-day">Nothing on the calendar for that day.</div>';
    } else {
      events.forEach(function (ev, idx) {
        var when = fmtTime(ev.start_time);
        if (ev.end_time) when += " – " + fmtTime(ev.end_time);
        var titleTxt = (ev.title || "").replace(/</g, "&lt;");
        var locTxt = (ev.location_name || "").replace(/</g, "&lt;");
        html += '<div class="cal-event" data-event-idx="' + idx +
          '" role="button" tabindex="0" title="Tap to open in chat">' +
          '<div class="title">' + titleTxt + "</div>" +
          '<div class="when">' + when + "</div>" +
          '<div class="where">' + locTxt + "</div>" +
          "</div>";
      });
    }
    detailEl.innerHTML = html;
  }

  // Build a chat bubble text blob for an event. Mirrors the backend's
  // _event_card format roughly so it reads natural when injected.
  function eventToChatText(ev) {
    var parts = (ev.date || "").split("-");
    var y = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10) - 1;
    var d = parseInt(parts[2], 10);
    var when = "";
    if (!isNaN(y) && !isNaN(m) && !isNaN(d)) {
      when = MONTH_LABELS[m] + " " + d + ", " + y;
    }
    var time = fmtTime(ev.start_time);
    if (ev.end_time) time += " – " + fmtTime(ev.end_time);
    var lines = [];
    if (when) lines.push("📅 " + when + (time ? " · " + time : ""));
    if (ev.location_name) lines.push("📍 " + ev.location_name);
    lines.push(ev.title || "");
    if (ev.description) {
      lines.push("");
      lines.push(String(ev.description).replace(/\r?\n/g, " "));
    }
    if (ev.event_url) lines.push("🔗 " + ev.event_url);
    return lines.join("\n");
  }

  function pushEventToChat(ev) {
    var log = document.getElementById("log");
    if (!log) return;
    var row = document.createElement("div");
    row.className = "row bot";
    var bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = eventToChatText(ev);
    row.appendChild(bubble);
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  function handleEventTap(target) {
    var card = target.closest && target.closest(".cal-event");
    if (!card) return;
    var idx = parseInt(card.getAttribute("data-event-idx") || "-1", 10);
    if (idx < 0) return;
    var events = (state.eventsByDate && state.eventsByDate[state.selectedKey]) || [];
    var ev = events[idx];
    if (!ev) return;
    closeCalendar();
    pushEventToChat(ev);
  }

  function render() {
    renderGrid();
    renderDetail();
  }

  function selectDay(key) {
    state.selectedKey = key;
    render();
  }

  function openCalendar() {
    overlay.classList.add("open");
    document.body.style.overflow = "hidden";
    loadEvents();
    render();
  }

  function closeCalendar() {
    overlay.classList.remove("open");
    document.body.style.overflow = "";
  }

  btn.addEventListener("click", openCalendar);
  closeBtn.addEventListener("click", closeCalendar);
  detailEl.addEventListener("click", function (e) {
    handleEventTap(e.target);
  });
  detailEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") {
      var card = e.target && e.target.closest && e.target.closest(".cal-event");
      if (card) { e.preventDefault(); handleEventTap(e.target); }
    }
  });
  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) closeCalendar();
  });
  prevBtn.addEventListener("click", function () {
    state.month -= 1;
    if (state.month < 0) { state.month = 11; state.year -= 1; }
    render();
  });
  nextBtn.addEventListener("click", function () {
    state.month += 1;
    if (state.month > 11) { state.month = 0; state.year += 1; }
    render();
  });
  document.addEventListener("keydown", function (e) {
    if (!overlay.classList.contains("open")) return;
    if (e.key === "Escape") { e.preventDefault(); closeCalendar(); }
  });

  // Expose a hook so AC-2 (chat integration) can open from the chat flow.
  window.havasuChatCalendar = {
    open: openCalendar,
    close: closeCalendar,
    selectDay: function (key) {
      state.selectedKey = key;
      // Jump to that month if needed.
      var parts = (key || "").split("-");
      if (parts.length === 3) {
        state.year = parseInt(parts[0], 10);
        state.month = parseInt(parts[1], 10) - 1;
      }
      openCalendar();
    },
  };
})();
