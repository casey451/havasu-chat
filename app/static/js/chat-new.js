// app/static/js/chat-new.js
//
// Hava — new /chat client (BUILD.md step 5).
//
// One file, no framework. Each turn is added to the thread. Hava's response
// has two parts: a voice line (1–3 sentences) and an optional component
// payload that the front-end renders by `component.type`.
//
// Component renderers live in this file as small functions. As new types
// land (week_strip, card_row, single_card, business_list), add a renderer
// in the COMPONENT_RENDERERS map below — the dispatch is one switch.

(function () {
  "use strict";

  // ─────────── Plausible analytics (Q5) ───────────
  //
  // Three custom events. All payloads are structural metadata only —
  // never the user's query text, business name, or any PII. That's
  // load-bearing for the GDPR-compliant / no-cookie-banner posture.
  //
  // Guarded with a typeof check so local dev (where PLAUSIBLE_DOMAIN
  // is unset and the script tag isn't injected) is a silent no-op.

  function trackPlausible(eventName, props) {
    if (typeof plausible !== "function") return;
    try {
      plausible(eventName, props ? { props: props } : undefined);
    } catch (_) {
      // Never let analytics break the chat surface.
    }
  }

  function lengthBucket(text) {
    const n = (text || "").length;
    if (n < 20) return "short";
    if (n <= 100) return "medium";
    return "long";
  }

  // ─────────── session ───────────
  // Session ID survives back/forward but resets on hard reload. URL-bound
  // so /chat?q=foo always starts a fresh conversation, but submitting from
  // the same /chat keeps the same session.
  const url = new URL(window.location.href);
  const initialQuery = url.searchParams.get("q");
  const sessionId = makeSessionId();

  // ─────────── DOM refs ───────────
  const thread = document.getElementById("thread");
  const empty = document.getElementById("empty-state");
  const form = document.getElementById("composer-form");
  const input = document.getElementById("composer-input");
  const sendBtn = document.getElementById("composer-send");

  // ─────────── render helpers ───────────

  function makeSessionId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "s-" + Date.now() + "-" + Math.random().toString(36).slice(2);
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  // [name](url) markdown → safe <a>. Text outside links is escaped via
  // textContent. Only http(s) and root-relative URLs allowed.
  function renderVoiceWithLinks(text) {
    const fragment = document.createDocumentFragment();
    const re = /\[([^\]]+)\]\(([^)]+)\)/g;
    let last = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) {
        fragment.appendChild(document.createTextNode(text.slice(last, m.index)));
      }
      const label = m[1];
      const href = m[2].trim();
      if (/^https?:\/\//i.test(href) || href.startsWith("/")) {
        const a = document.createElement("a");
        a.href = href;
        a.textContent = label;
        if (href.startsWith("http")) {
          a.target = "_blank";
          a.rel = "noopener noreferrer";
        }
        fragment.appendChild(a);
      } else {
        // Defensive: don't render unknown schemes.
        fragment.appendChild(document.createTextNode(m[0]));
      }
      last = re.lastIndex;
    }
    if (last < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(last)));
    }
    return fragment;
  }

  function showEmptyState() {
    if (empty) empty.style.display = "";
  }
  function hideEmptyState() {
    if (empty) empty.style.display = "none";
  }

  function appendUserTurn(text) {
    hideEmptyState();
    const row = el("div", "turn-user");
    const bubble = el("div", "bubble");
    bubble.textContent = text;
    row.appendChild(bubble);
    thread.appendChild(row);
    scrollToBottom();
    return row;
  }

  function appendHavaTurn() {
    const row = el("div", "turn-hava is-loading");
    row.appendChild(el("span", "avatar"));
    const said = el("div", "said");
    const voice = el("p", "voice");
    voice.appendChild(typingDots());
    said.appendChild(voice);
    row.appendChild(said);
    thread.appendChild(row);
    scrollToBottom();
    return { row, said, voice };
  }

  function typingDots() {
    const wrap = el("span", "typing-dots");
    wrap.appendChild(el("span"));
    wrap.appendChild(el("span"));
    wrap.appendChild(el("span"));
    return wrap;
  }

  function fillHavaTurn(turn, payload) {
    turn.row.classList.remove("is-loading");
    turn.voice.textContent = "";
    turn.voice.appendChild(renderVoiceWithLinks(payload.voice || payload.response || ""));
    const slot = el("div", "component-slot");
    const renderer = COMPONENT_RENDERERS[payload.component && payload.component.type] || null;
    if (renderer) {
      const node = renderer(payload.component.data || {});
      if (node) slot.appendChild(node);
    }
    if (slot.childNodes.length > 0) {
      turn.said.appendChild(slot);
    }
    scrollToBottom();
  }

  function failHavaTurn(turn, message) {
    turn.row.classList.remove("is-loading");
    turn.row.classList.add("is-error");
    turn.voice.textContent = message;
    scrollToBottom();
  }

  function scrollToBottom() {
    // Smooth-scroll to keep the latest turn visible above the sticky
    // composer. Use requestAnimationFrame so layout has settled.
    requestAnimationFrame(() => {
      window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    });
  }

  // ─────────── component renderers ───────────
  //
  // Each renderer takes the component's `data` and returns an HTMLElement
  // (or null to skip). Renderers are pure: no network, no side effects.

  function renderDayAgenda(data) {
    if (!data || !Array.isArray(data.events) || data.events.length === 0) {
      return null;
    }
    const root = el("div", "agenda");

    // Head
    const head = el("div", "agenda-head");
    const dateLabel = el("span", "agenda-date", data.date_label || formatDate(data.date));
    const meta = el("span", "agenda-meta");
    const count = data.events.length;
    meta.textContent = count === 1 ? "1 event" : count + " events";
    head.appendChild(dateLabel);
    head.appendChild(meta);
    root.appendChild(head);

    // Events grouped by morning / afternoon / evening if start_time present
    const grouped = groupByPartOfDay(data.events);
    for (const [label, events] of grouped) {
      if (events.length === 0) continue;
      const section = el("div", "agenda-section");
      section.appendChild(el("div", "agenda-section-label", label));
      events.forEach((ev) => section.appendChild(renderAgendaRow(ev)));
      root.appendChild(section);
    }

    // Foot
    const foot = el("div", "agenda-foot");
    foot.appendChild(el("span", null, "Showing " + count + " of " + count));
    root.appendChild(foot);

    return root;
  }

  function renderAgendaRow(ev) {
    const a = document.createElement("a");
    a.className = "agenda-row";
    a.href = ev.url || "#";
    // Q5: card_type for Plausible "Chat Card Tap" delegated listener.
    a.dataset.cardType = "event";

    const time = el("div", "time");
    const t = formatTime(ev.start);
    if (t) {
      const tn = document.createTextNode(t.hm);
      time.appendChild(tn);
      const ampm = el("span", "ampm", " " + t.ampm);
      time.appendChild(ampm);
    } else if (ev.time_label) {
      time.textContent = ev.time_label;
    }
    if (ev.end || ev.range_label) {
      const range = el("span", "range",
        ev.range_label || ("until " + (formatTime(ev.end) || {}).hm || ""));
      time.appendChild(range);
    }
    a.appendChild(time);

    const content = el("div", "content");
    content.appendChild(el("div", "title", ev.title || ""));
    const meta = el("div", "meta");
    if (ev.category) {
      const tag = el("span", "tag" + (ev.category_warm ? " warm" : ""));
      tag.appendChild(el("span", "dot"));
      tag.appendChild(document.createTextNode(ev.category));
      meta.appendChild(tag);
    }
    if (ev.venue) {
      meta.appendChild(document.createTextNode(ev.venue));
    }
    content.appendChild(meta);
    a.appendChild(content);

    return a;
  }

  function groupByPartOfDay(events) {
    const morning = [];
    const afternoon = [];
    const evening = [];
    const undated = [];
    for (const ev of events) {
      const t = formatTime(ev.start);
      if (!t) {
        undated.push(ev);
        continue;
      }
      const h = t.hour24;
      if (h < 12) morning.push(ev);
      else if (h < 17) afternoon.push(ev);
      else evening.push(ev);
    }
    const out = [];
    if (morning.length) out.push(["Morning", morning]);
    if (afternoon.length) out.push(["Afternoon", afternoon]);
    if (evening.length) out.push(["Evening", evening]);
    if (undated.length) out.push(["", undated]);
    return out;
  }

  function formatTime(s) {
    // Accepts "HH:MM" 24h or "HH:MM:SS"; returns {hm, ampm, hour24} or null
    if (!s || typeof s !== "string") return null;
    const m = /^(\d{1,2}):(\d{2})/.exec(s);
    if (!m) return null;
    const hour24 = parseInt(m[1], 10);
    const min = parseInt(m[2], 10);
    if (isNaN(hour24) || hour24 < 0 || hour24 > 23) return null;
    const ampm = hour24 < 12 ? "am" : "pm";
    const h12 = hour24 % 12 || 12;
    const hm = min === 0 ? String(h12) : h12 + ":" + String(min).padStart(2, "0");
    return { hm: hm, ampm: ampm, hour24: hour24 };
  }

  function formatDate(iso) {
    // "2026-05-08" → "Friday, May 8"
    if (!iso) return "";
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    if (!m) return iso;
    const d = new Date(parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10));
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  }


  // ─────────── week_strip renderer (BUILD.md step 6) ───────────
  //
  // Schema (from BUILD.md):
  //   { days: [{ date, count, dow?, num?, is_today? }],
  //     selected_date, agenda: [<agenda_row items>] }
  //
  // Tap on a non-selected day fires a new chat query ("what's on Sat May 9?")
  // — fits the chat metaphor. The current turn's week_strip stays put.

  function renderWeekStrip(data) {
    if (!data || !Array.isArray(data.days) || data.days.length === 0) return null;
    const root = el("div", "weekstrip");

    // Head
    const head = el("div", "weekstrip-head");
    head.appendChild(el("span", "title", data.title || formatWeekRange(data.days)));
    if (typeof data.total_count === "number") {
      head.appendChild(
        el("span", "meta", data.total_count + (data.total_count === 1 ? " event" : " events"))
      );
    }
    root.appendChild(head);

    // Day picker
    const picker = el("div", "weekstrip-days");
    data.days.forEach((d) => picker.appendChild(renderWsDay(d, data.selected_date)));
    root.appendChild(picker);

    // Selected day's agenda
    const content = el("div", "weekstrip-content");
    if (Array.isArray(data.agenda) && data.agenda.length > 0) {
      data.agenda.forEach((ev) => content.appendChild(renderAgendaRow(ev)));
    } else {
      content.appendChild(el("div", "agenda-empty", "Nothing on this day yet."));
    }
    root.appendChild(content);

    // Foot — link to /chat for the full week, if provided
    if (data.foot_link) {
      const foot = el("div", "weekstrip-foot");
      const a = document.createElement("a");
      a.href = data.foot_link;
      a.textContent = data.foot_label || "Open the full calendar →";
      foot.appendChild(a);
      root.appendChild(foot);
    }
    return root;
  }

  function renderWsDay(d, selectedDate) {
    const btn = document.createElement("button");
    btn.className = "wsday";
    btn.type = "button";
    btn.dataset.date = d.date || "";
    if (d.is_today) btn.classList.add("is-today");
    if (d.date && d.date === selectedDate) btn.classList.add("is-selected");

    const dow = d.dow || dowFromIso(d.date);
    const num = d.num != null ? d.num : numFromIso(d.date);
    btn.appendChild(el("div", "dow", dow));
    btn.appendChild(el("div", "num", String(num)));

    // Dot indicator: cap at 6 + show "+N" beyond
    const dots = el("div", "dots");
    const count = Math.max(0, parseInt(d.count, 10) || 0);
    const visible = Math.min(count, 6);
    for (let i = 0; i < visible; i++) dots.appendChild(el("span"));
    if (count > visible) {
      const more = el("span", "more", "+" + (count - visible));
      dots.appendChild(more);
    }
    btn.appendChild(dots);

    btn.addEventListener("click", function () {
      // Tapping a day = ask Hava for that day. New turn, new component.
      const dayLabel = formatLongDate(d.date);
      submit("What's happening on " + dayLabel + "?");
    });
    return btn;
  }

  function dowFromIso(iso) {
    const d = isoToDate(iso);
    if (!d) return "";
    return d.toLocaleDateString("en-US", { weekday: "short" });
  }
  function numFromIso(iso) {
    const d = isoToDate(iso);
    return d ? d.getDate() : "";
  }
  function formatLongDate(iso) {
    const d = isoToDate(iso);
    if (!d) return iso || "";
    return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  }
  function formatWeekRange(days) {
    if (!days || days.length === 0) return "";
    const a = isoToDate(days[0].date);
    const b = isoToDate(days[days.length - 1].date);
    if (!a || !b) return "";
    const fmt = (d) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    return fmt(a) + " – " + fmt(b);
  }
  function isoToDate(iso) {
    if (!iso) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    if (!m) return null;
    const d = new Date(parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10));
    return isNaN(d.getTime()) ? null : d;
  }

  // ─────────── card_row renderer (BUILD.md step 6) ───────────
  //
  // Schema: { items: [{ title, blurb, meta, image_url, url, category, category_warm? }] }

  function renderCardRow(data) {
    if (!data || !Array.isArray(data.items) || data.items.length === 0) return null;
    const root = el("div", "cardrow");
    data.items.forEach((it) => root.appendChild(renderMiniCard(it)));
    return root;
  }

  function renderMiniCard(it) {
    const a = document.createElement("a");
    a.className = "mini-card";
    a.href = it.url || "#";
    a.dataset.cardType = "card_row";

    const img = el("div", "img");
    if (it.image_url) {
      const i = document.createElement("img");
      i.loading = "lazy";
      i.alt = it.image_alt || it.title || "";
      i.src = it.image_url;
      img.appendChild(i);
    }
    a.appendChild(img);

    const body = el("div", "body");
    const meta = el("div", "meta");
    if (it.category || it.meta) {
      const dot = el("span", "dot" + (it.category_warm ? " warm" : ""));
      meta.appendChild(dot);
      meta.appendChild(document.createTextNode(it.category || it.meta || ""));
    }
    body.appendChild(meta);
    body.appendChild(el("div", "name", it.title || ""));
    if (it.blurb) body.appendChild(el("p", "blurb", it.blurb));
    a.appendChild(body);

    return a;
  }


  // ─────────── single_card renderer (BUILD.md step 7) ───────────
  //
  // Schema: {
  //   title, image_url, image_alt, summary,
  //   category, category_warm?,
  //   facts: [{ key, val, val_url? }],
  //   actions: [{ label, url, primary? }],
  // }
  //
  // Use cases: a single venue lookup ("tell me about Channel Brewing"),
  // a single event ("when's the Bridgewater 5K"). For business lookups
  // with phone-tap and hours, use single_business_card (step 7.5).

  function renderSingleCard(data) {
    if (!data || !data.title) return null;
    const root = el("article", "single-card");
    root.dataset.cardType = "single_card";

    // Image (skipped if no URL — placeholder gradient takes over)
    const img = el("div", "img");
    if (data.image_url) {
      const i = document.createElement("img");
      i.loading = "lazy";
      i.alt = data.image_alt || data.title;
      i.src = data.image_url;
      img.appendChild(i);
    }
    root.appendChild(img);

    const body = el("div", "body");

    // Meta row: category + optional status pill
    const metaRow = el("div", "meta-row");
    if (data.category) {
      metaRow.appendChild(el("span", "tag-dot" + (data.category_warm ? " warm" : "")));
      metaRow.appendChild(document.createTextNode(data.category));
    }
    if (data.status) {
      const status = el("span", "status " + (data.status_class || data.status));
      status.appendChild(el("span", "dot"));
      status.appendChild(document.createTextNode(data.status_text || data.status));
      metaRow.appendChild(status);
    }
    if (metaRow.childNodes.length > 0) body.appendChild(metaRow);

    body.appendChild(el("h3", null, data.title));
    if (data.summary) body.appendChild(el("p", "summary", data.summary));

    // Facts table — key/value rows
    if (Array.isArray(data.facts) && data.facts.length > 0) {
      const facts = el("div", "facts");
      data.facts.forEach((f) => {
        const row = el("div", "fact");
        row.appendChild(el("span", "key", f.key || ""));
        const val = el("span", "val");
        if (f.val_url) {
          const a = document.createElement("a");
          a.href = f.val_url;
          a.textContent = f.val || f.val_url;
          if (f.val_url.startsWith("http")) {
            a.target = "_blank";
            a.rel = "noopener noreferrer";
          }
          val.appendChild(a);
        } else {
          val.textContent = f.val || "";
        }
        row.appendChild(val);
        facts.appendChild(row);
      });
      body.appendChild(facts);
    }

    // Actions row
    if (Array.isArray(data.actions) && data.actions.length > 0) {
      const actions = el("div", "actions");
      data.actions.forEach((a) => {
        const link = document.createElement("a");
        link.className = "btn" + (a.primary ? " primary" : "");
        link.href = a.url || "#";
        link.textContent = a.label || "View";
        if (a.url && a.url.startsWith("http")) {
          link.target = "_blank";
          link.rel = "noopener noreferrer";
        }
        actions.appendChild(link);
      });
      body.appendChild(actions);
    }

    root.appendChild(body);
    return root;
  }


  // ─────────── business_list renderer (BUILD.md step 7.5) ───────────
  //
  // Schema: {
  //   category, total_count,
  //   items: [{
  //     name, thumb_url, category, rating, review_count,
  //     status, status_text, blurb,
  //     phone, phone_raw, address_short, url,
  //     spotlight: bool
  //   }],
  //   disclosure: bool        // show "Spotlight = paid placement" footer
  // }
  //
  // Spotlights are visually distinguished (warm-tinted row, "Spotlight" tag)
  // AND disclosed in the footer copy. Both surfaces are part of the design
  // contract — never silently re-rank by spotlight.

  function renderBusinessList(data) {
    if (!data || !Array.isArray(data.items) || data.items.length === 0) return null;
    const root = el("div", "biz-list");

    // Head: category + count
    const head = el("div", "biz-list-head");
    head.appendChild(el("span", "title", data.category || data.title || "Local pros"));
    if (typeof data.total_count === "number") {
      head.appendChild(
        el("span", "count", data.items.length + " of " + data.total_count)
      );
    }
    root.appendChild(head);

    // Rows
    let anySpotlight = false;
    data.items.forEach((it) => {
      if (it.spotlight) anySpotlight = true;
      root.appendChild(renderBizRow(it));
    });

    // Foot: disclosure (auto-show when any row is a spotlight, regardless
    // of the data.disclosure flag — trust depends on this) + count link
    const foot = el("div", "biz-list-foot");
    if (anySpotlight || data.disclosure) {
      foot.appendChild(el(
        "span", "disclosure",
        "Spotlight = paid placement. Hava's recommendations aren't pay-to-play."
      ));
    } else {
      foot.appendChild(document.createTextNode(""));
    }
    if (data.foot_link) {
      const a = document.createElement("a");
      a.href = data.foot_link;
      a.textContent = data.foot_label || "See all →";
      foot.appendChild(a);
    }
    root.appendChild(foot);

    return root;
  }

  function renderBizRow(it) {
    const a = document.createElement("a");
    a.className = "biz-row" + (it.spotlight ? " is-spotlight" : "");
    a.href = it.url || "#";
    a.dataset.cardType = "business_list";
    // Q5: Spotlight rows are paid placements. Stamp slot + id so the
    // delegated "Sponsor Click" listener can fire alongside the row tap.
    // ``id`` falls back to slug/url so the event is never empty.
    if (it.spotlight) {
      a.dataset.sponsorSlot = "biz_spotlight";
      a.dataset.sponsorId = String(it.id || it.slug || it.url || "");
    }

    // Thumbnail
    const thumb = el("div", "thumb");
    if (it.thumb_url || it.image_url) {
      const i = document.createElement("img");
      i.loading = "lazy";
      i.alt = it.name || "";
      i.src = it.thumb_url || it.image_url;
      thumb.appendChild(i);
    }
    a.appendChild(thumb);

    const body = el("div", "body");

    // Head line: name + Spotlight tag
    const headLine = el("div", "head-line");
    headLine.appendChild(el("h4", "name", it.name || ""));
    if (it.spotlight) {
      const tag = el("span", "spotlight-tag");
      tag.appendChild(el("span", "dot"));
      tag.appendChild(document.createTextNode("Spotlight"));
      headLine.appendChild(tag);
    }
    body.appendChild(headLine);

    // Meta line: category · rating · status pill
    const meta = el("div", "meta");
    if (it.category) meta.appendChild(el("span", "cat", it.category));
    if (typeof it.rating === "number") {
      meta.appendChild(el("span", "sep", "·"));
      const rating = el("span", "rating");
      const star = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      star.setAttribute("viewBox", "0 0 12 12");
      star.setAttribute("fill", "currentColor");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", "M6 1l1.5 3.5L11 5l-2.5 2.5L9 11 6 9.5 3 11l.5-3.5L1 5l3.5-.5z");
      star.appendChild(path);
      rating.appendChild(star);
      const reviewLabel = it.review_count != null ? " (" + it.review_count + ")" : "";
      rating.appendChild(document.createTextNode(it.rating.toFixed(1) + reviewLabel));
      meta.appendChild(rating);
    }
    if (it.status) {
      meta.appendChild(el("span", "sep", "·"));
      const status = el("span", "status " + (it.status_class || it.status));
      status.appendChild(el("span", "dot"));
      status.appendChild(document.createTextNode(it.status_text || it.status));
      meta.appendChild(status);
    }
    if (meta.childNodes.length > 0) body.appendChild(meta);

    // Blurb
    if (it.blurb) body.appendChild(el("p", "blurb", it.blurb));

    // Actions (Call + Directions when phone is present)
    if (it.phone || it.phone_raw || it.phone_tel || it.address_short || it.address_query) {
      const actions = el("div", "actions");
      if (it.phone_raw || it.phone_tel || it.phone) {
        const call = document.createElement("a");
        call.className = "btn primary";
        call.href = "tel:" + (it.phone_raw || it.phone_tel || it.phone.replace(/\D/g, ""));
        // Phone icon
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 16 16");
        svg.setAttribute("fill", "none");
        svg.setAttribute("stroke", "currentColor");
        svg.setAttribute("stroke-width", "1.5");
        const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
        p.setAttribute("d", "M3 4c0 5 4 9 9 9l1-3-3-1-1 1c-2-1-3-2-4-4l1-1-1-3z");
        svg.appendChild(p);
        call.appendChild(svg);
        call.appendChild(document.createTextNode(
          " " + (it.phone ? "Call " + it.phone : "Call")
        ));
        // Stop the row anchor from intercepting the tel: tap
        call.addEventListener("click", function (e) { e.stopPropagation(); });
        actions.appendChild(call);
      }
      if (it.address_short || it.address_query || it.url) {
        const dir = document.createElement("a");
        dir.className = "btn";
        const mapsQuery = it.address_query
          ? "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(it.address_query)
          : null;
        dir.href = it.directions_url || mapsQuery || it.url || "#";
        dir.textContent = "Directions";
        dir.addEventListener("click", function (e) { e.stopPropagation(); });
        actions.appendChild(dir);
      }
      body.appendChild(actions);
    }

    a.appendChild(body);
    return a;
  }

  // ─────────── component dispatch ───────────
  // Add a key here when a new component type lands. Returning null falls
  // through to voice-only rendering.
  const COMPONENT_RENDERERS = {
    day_agenda: renderDayAgenda,
    week_strip: renderWeekStrip,
    card_row: renderCardRow,
    single_card: renderSingleCard,
    single_business_card: renderSingleCard,           // shares the single_card shape
    business_list: renderBusinessList,
    none: function () { return null; },
  };

  // ─────────── network ───────────

  async function postChat(query) {
    const turn = appendHavaTurn();
    sendBtn.disabled = true;
    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query: query, session_id: sessionId }),
      });
      if (!resp.ok) {
        // Rate-limit returns 429 with a message string — surface plainly.
        let msg = "Something went sideways on my end. Try again in a sec.";
        try {
          const data = await resp.json();
          if (data && typeof data === "object" && data.detail) {
            msg = data.detail;
          }
        } catch (_) {
          // body wasn't JSON; keep default
        }
        failHavaTurn(turn, msg);
        return;
      }
      const payload = await resp.json();
      fillHavaTurn(turn, payload);
    } catch (e) {
      failHavaTurn(turn, "Couldn't reach me — check your connection and try again.");
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  // ─────────── form wiring ───────────

  function submit(query) {
    const q = (query || "").trim();
    if (!q) return;
    // Plausible: fire BEFORE the network request so a page-unload navigation
    // between submit and response doesn't drop the event. Only the length
    // bucket goes on the wire — never the query text.
    trackPlausible("Chat Query Sent", { length_bucket: lengthBucket(q) });
    appendUserTurn(q);
    postChat(q);
    input.value = "";
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    submit(input.value);
  });

  // Q5: delegated Plausible listener for card + sponsor taps. Walks up
  // from the event target to find:
  //   1. The nearest ``[data-card-type]`` ancestor → ``Chat Card Tap``.
  //      Catches clicks on links inside cards (Call/Directions buttons in
  //      single_card, action anchors inside biz-row, etc.) as well as the
  //      outer card anchor itself.
  //   2. The nearest ``[data-sponsor-slot]`` ancestor OR any anchor whose
  //      href starts with ``/sponsor/click`` → ``Sponsor Click`` with the
  //      slot + id parsed off the element (data attrs preferred, otherwise
  //      pulled from the URL query string). Fires alongside the regular
  //      navigation, so the server-side ``/sponsor/click`` redirect logic
  //      still records the click independently.
  //
  // Only structural metadata (card_type / slot / id) goes on the wire —
  // never the user's query text, business name, or any PII. Required by
  // the cookieless / no-consent-banner GDPR posture.
  if (thread) {
    thread.addEventListener("click", function (e) {
      const target = e.target;
      if (!target || typeof target.closest !== "function") return;

      const card = target.closest("[data-card-type]");
      if (card) {
        trackPlausible("Chat Card Tap", { card_type: card.dataset.cardType });
      }

      const sponsorEl = target.closest("[data-sponsor-slot]");
      if (sponsorEl) {
        trackPlausible("Sponsor Click", {
          slot: sponsorEl.dataset.sponsorSlot || "",
          id: sponsorEl.dataset.sponsorId || "",
        });
        return;
      }
      const sponsorLink = target.closest('a[href^="/sponsor/click"]');
      if (sponsorLink) {
        let slot = "";
        let id = "";
        try {
          const u = new URL(sponsorLink.getAttribute("href"), window.location.origin);
          slot = u.searchParams.get("slot") || "";
          id = u.searchParams.get("id") || "";
        } catch (_) {
          // Malformed href — fire with empty props rather than dropping the event.
        }
        trackPlausible("Sponsor Click", { slot: slot, id: id });
      }
    });
  }

  // Chips (in the empty state) submit the chip text as a query.
  document.querySelectorAll(".chip[data-q]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      submit(btn.getAttribute("data-q"));
    });
  });

  // If the URL has ?q=…, fire it off on load.
  if (initialQuery && initialQuery.trim()) {
    submit(initialQuery);
  } else {
    showEmptyState();
  }
})();
