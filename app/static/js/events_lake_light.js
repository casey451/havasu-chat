(function () {
  "use strict";

  const listBtn = document.getElementById("events-view-list");
  const calBtn = document.getElementById("events-view-calendar");
  const listPanel = document.getElementById("events-list-panel");
  const calPanel = document.getElementById("events-calendar-panel");
  if (!listBtn || !calBtn || !listPanel || !calPanel) return;

  function setView(view) {
    const list = view === "list";
    listPanel.style.display = list ? "block" : "none";
    calPanel.style.display = list ? "none" : "block";
    listBtn.classList.toggle("is-active", list);
    calBtn.classList.toggle("is-active", !list);
    listBtn.setAttribute("aria-selected", list ? "true" : "false");
    calBtn.setAttribute("aria-selected", list ? "false" : "true");
  }

  listBtn.addEventListener("click", function () { setView("list"); });
  calBtn.addEventListener("click", function () { setView("calendar"); });

  const grid = document.getElementById("ll-cal-grid");
  const title = document.getElementById("ll-cal-title");
  const selected = document.getElementById("ll-selected-events");
  const prev = document.getElementById("ll-cal-prev");
  const next = document.getElementById("ll-cal-next");
  if (!grid || !title || !selected || !prev || !next) return;

  const today = new Date();
  const state = {
    year: today.getFullYear(),
    month: today.getMonth(),
    selected: null,
    eventsByDate: {},
  };

  function key(y, m, d) {
    const mm = String(m + 1).padStart(2, "0");
    const dd = String(d).padStart(2, "0");
    return y + "-" + mm + "-" + dd;
  }

  function draw() {
    title.textContent = new Date(state.year, state.month, 1).toLocaleDateString("en-US", {
      month: "long",
      year: "numeric",
    });
    grid.innerHTML = "";
    const first = new Date(state.year, state.month, 1);
    const lead = first.getDay();
    const days = new Date(state.year, state.month + 1, 0).getDate();
    for (let i = 0; i < lead; i += 1) {
      const blank = document.createElement("div");
      grid.appendChild(blank);
    }
    for (let d = 1; d <= days; d += 1) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ll-day";
      btn.textContent = String(d);
      const k = key(state.year, state.month, d);
      if (state.eventsByDate[k]) btn.classList.add("has-events");
      if (state.selected === k) btn.classList.add("selected");
      if (k === key(today.getFullYear(), today.getMonth(), today.getDate())) btn.classList.add("today");
      btn.addEventListener("click", function () {
        state.selected = k;
        draw();
        drawSelected();
      });
      grid.appendChild(btn);
    }
  }

  function drawSelected() {
    const items = state.eventsByDate[state.selected] || [];
    selected.innerHTML = "";
    if (!state.selected) {
      selected.innerHTML = '<div class="ll-card" style="padding:12px 14px; color:var(--ll-muted);">Pick a day with a dot to see events.</div>';
      return;
    }
    if (!items.length) {
      selected.innerHTML = '<div class="ll-card" style="padding:12px 14px; color:var(--ll-muted);">No events for this day.</div>';
      return;
    }
    items.forEach(function (ev) {
      const card = document.createElement("a");
      card.className = "ll-list-card";
      card.href = "/events/" + encodeURIComponent(ev.id);
      card.innerHTML =
        '<div class="ll-list-thumb"></div>' +
        '<div><div class="ll-list-time">' +
        (new Date(ev.start_at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })) +
        '</div><h4 class="ll-serif" style="margin:2px 0; font-size:22px;">' +
        (ev.title || "") +
        '</h4><div style="font-size:13px; color:var(--ll-muted);">' +
        (ev.venue || "") +
        '</div></div>';
      selected.appendChild(card);
    });
  }

  function loadWindow(group) {
    return fetch("/api/events?group=" + encodeURIComponent(group))
      .then(function (r) { return r.ok ? r.json() : { items: [] }; })
      .then(function (body) {
        (body.items || []).forEach(function (ev) {
          if (!ev.start_at) return;
          const k = ev.start_at.slice(0, 10);
          if (!state.eventsByDate[k]) state.eventsByDate[k] = [];
          state.eventsByDate[k].push(ev);
        });
      });
  }

  Promise.all([loadWindow("today"), loadWindow("weekend"), loadWindow("next-week")]).finally(function () {
    draw();
    drawSelected();
  });

  prev.addEventListener("click", function () {
    state.month -= 1;
    if (state.month < 0) { state.month = 11; state.year -= 1; }
    draw();
  });
  next.addEventListener("click", function () {
    state.month += 1;
    if (state.month > 11) { state.month = 0; state.year += 1; }
    draw();
  });

  setView("list");
})();
