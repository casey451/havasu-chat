// app/static/js/chat.js
// Slice 65 (campaign #31 step 3/3, close): the cross-module calendar
// bridge is now an explicit import from ./calendar.js (was a defensive
// read of window.havasuChatCalendar in Slices 61–64). The defensive
// null-check is preserved because the export can be null when the
// calendar DOM isn't present at module-load time (extreme edge case;
// the HTML shell always includes the calendar markup, but the check
// costs nothing and matches the prior contract).
// History: Slice 61 (65f71e8) extracted this module from
// app/static/index.html's chat IIFE body.

import { havasuChatCalendar } from "./calendar.js";

var sessionId = (typeof crypto !== "undefined" && crypto.randomUUID)
  ? crypto.randomUUID()
  : "s-" + Date.now() + "-" + Math.random().toString(36).slice(2);
var log = document.getElementById("log");
var form = document.getElementById("form");
var input = document.getElementById("msg");
var sendBtn = document.getElementById("send");

function scrollToBottom() {
  log.scrollTop = log.scrollHeight;
}

function renderWithLinks(text) {
  var fragment = document.createDocumentFragment();
  var s = text == null ? "" : String(text);
  var re = /\[([^\]]*)\]\(([^)]*)\)/g;
  var lastIndex = 0;
  var match;
  while ((match = re.exec(s)) !== null) {
    if (match.index > lastIndex) {
      fragment.appendChild(document.createTextNode(s.slice(lastIndex, match.index)));
    }
    var label = match[1];
    var rawUrl = match[2].trim();
    var valid = /^https?:\/\//i.test(rawUrl);
    if (valid) {
      var a = document.createElement("a");
      a.href = rawUrl;
      a.textContent = label;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      fragment.appendChild(a);
    } else {
      fragment.appendChild(document.createTextNode(match[0]));
    }
    lastIndex = re.lastIndex;
  }
  if (lastIndex < s.length) {
    fragment.appendChild(document.createTextNode(s.slice(lastIndex)));
  }
  return fragment;
}

function setBubbleContentFromAssistant(bubble, text) {
  while (bubble.firstChild) {
    bubble.removeChild(bubble.firstChild);
  }
  var payload = text ? String(text) : "(no response)";
  bubble.appendChild(renderWithLinks(payload));
}

function addRow(role, text, extraClass) {
  var row = document.createElement("div");
  row.className = "row " + (role === "user" ? "user" : "bot");
  var bubble = document.createElement("div");
  bubble.className = "bubble" + (extraClass ? " " + extraClass : "");
  bubble.textContent = text;
  row.appendChild(bubble);
  log.appendChild(row);
  scrollToBottom();
  return { row: row, bubble: bubble };
}

function attachFeedbackThumbs(row, chatLogId) {
  if (!chatLogId || row.querySelector(".msg-feedback")) return;
  var wrap = document.createElement("div");
  wrap.className = "msg-feedback";
  var btnRow = document.createElement("div");
  btnRow.className = "msg-feedback-btns";
  var errEl = document.createElement("span");
  errEl.className = "msg-feedback-err";
  errEl.setAttribute("aria-live", "polite");

  var up = document.createElement("button");
  up.type = "button";
  up.className = "thumb-btn";
  up.setAttribute("aria-label", "Thumbs up");
  up.textContent = "👍";

  var down = document.createElement("button");
  down.type = "button";
  down.className = "thumb-btn";
  down.setAttribute("aria-label", "Thumbs down");
  down.textContent = "👎";

  var inflight = false;
  var lockedSignal = null;

  function clearError() {
    errEl.textContent = "";
    errEl.style.display = "none";
  }

  function showError(msg) {
    errEl.textContent = msg;
    errEl.style.display = "block";
  }

  function setLockedUI(signal) {
    lockedSignal = signal;
    up.classList.remove("thumb-selected", "thumb-dim");
    down.classList.remove("thumb-selected", "thumb-dim");
    if (signal === "positive") {
      up.classList.add("thumb-selected");
      down.classList.add("thumb-dim");
    } else {
      down.classList.add("thumb-selected");
      up.classList.add("thumb-dim");
    }
  }

  function unlockUI() {
    lockedSignal = null;
    up.classList.remove("thumb-selected", "thumb-dim");
    down.classList.remove("thumb-selected", "thumb-dim");
  }

  function postSignal(signal) {
    if (inflight) return;
    clearError();
    inflight = true;
    up.disabled = true;
    down.disabled = true;
    fetch("/api/chat/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_log_id: chatLogId, signal: signal }),
    })
      .then(function (res) {
        return res.text().then(function (t) {
          var body = {};
          try {
            body = t ? JSON.parse(t) : {};
          } catch (ignore) {
            body = {};
          }
          return { ok: res.ok, status: res.status, body: body };
        });
      })
      .then(function (result) {
        inflight = false;
        up.disabled = false;
        down.disabled = false;
        if (result.ok && result.body && result.body.ok === true) {
          setLockedUI(signal);
          return;
        }
        unlockUI();
        var msg = "Couldn't save that — try again";
        if (result.body && result.body.error) msg = String(result.body.error);
        else if (result.body && result.body.message) msg = String(result.body.message);
        showError(msg);
      })
      .catch(function () {
        inflight = false;
        up.disabled = false;
        down.disabled = false;
        unlockUI();
        showError("Couldn't save that — try again");
      });
  }

  up.addEventListener("click", function () {
    if (inflight) return;
    if (lockedSignal === "positive") return;
    postSignal("positive");
  });
  down.addEventListener("click", function () {
    if (inflight) return;
    if (lockedSignal === "negative") return;
    postSignal("negative");
  });

  btnRow.appendChild(up);
  btnRow.appendChild(down);
  wrap.appendChild(btnRow);
  wrap.appendChild(errEl);
  row.appendChild(wrap);
}

function setLoading(on) {
  sendBtn.disabled = on;
  input.disabled = on;
}

function copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text);
  }
  return new Promise(function (resolve, reject) {
    var textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "absolute";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    try {
      var ok = document.execCommand("copy");
      document.body.removeChild(textarea);
      if (ok) resolve();
      else reject(new Error("copy failed"));
    } catch (err) {
      document.body.removeChild(textarea);
      reject(err);
    }
  });
}

function setTemporaryButtonText(btn, text) {
  var original = btn.getAttribute("data-default-label") || "Share";
  btn.textContent = text;
  window.setTimeout(function () {
    btn.textContent = original;
  }, 2000);
}

function attachShareButtons() {
  var cards = log.querySelectorAll(".event-card[data-event-id]");
  cards.forEach(function (card) {
    if (card.querySelector(".event-share-btn")) return;
    var eventId = card.getAttribute("data-event-id");
    if (!eventId) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "event-share-btn";
    btn.textContent = "Share";
    btn.setAttribute("data-default-label", "Share");
    btn.addEventListener("click", function () {
      var permalink = window.location.origin + "/events/" + eventId;
      copyToClipboard(permalink)
        .then(function () {
          setTemporaryButtonText(btn, "Link copied");
        })
        .catch(function () {
          setTemporaryButtonText(btn, "Copy failed");
        });
    });
    card.appendChild(btn);
  });
}

function removeAllChipsWraps() {
  log.querySelectorAll(".chips-wrap").forEach(function (w) {
    w.remove();
  });
}

var EXAMPLE_PROMPTS = [
  "What's on this weekend?",
  "Kids activities or swim lessons",
  "I'd like to add an event",
];

function showExamplePromptChips() {
  var wrap = document.createElement("div");
  wrap.className = "chips-wrap";
  wrap.setAttribute("role", "group");
  wrap.setAttribute("aria-label", "Example prompts");
  EXAMPLE_PROMPTS.forEach(function (label) {
    var chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = label;
    chip.addEventListener("click", function () {
      input.value = label;
      if (form.requestSubmit) form.requestSubmit();
      else form.dispatchEvent(new Event("submit", { cancelable: true }));
    });
    wrap.appendChild(chip);
  });
  log.appendChild(wrap);
  scrollToBottom();
}

function postOnboarding(body, onSuccess, onFailure) {
  fetch("/api/chat/onboarding", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(Object.assign({ session_id: sessionId }, body)),
  })
    .then(function (res) {
      return res.text().then(function (t) {
        var parsed = {};
        try {
          parsed = t ? JSON.parse(t) : {};
        } catch (ignore) {
          parsed = {};
        }
        return { ok: res.ok, body: parsed };
      });
    })
    .then(function (r) {
      if (r.ok && r.body && r.body.ok === true) onSuccess(r.body);
      else onFailure(r);
    })
    .catch(function () {
      onFailure(null);
    });
}

function showKidsChips() {
  var wrap = document.createElement("div");
  wrap.className = "chips-wrap";
  wrap.setAttribute("role", "group");
  wrap.setAttribute("aria-label", "Kids with you");
  [["Yes", true], ["No", false]].forEach(function (pair) {
    var chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = pair[0];
    chip.addEventListener("click", function () {
      chip.disabled = true;
      Array.prototype.forEach.call(wrap.querySelectorAll(".chip"), function (c) {
        c.disabled = true;
      });
      postOnboarding(
        { has_kids: pair[1] },
        function () {
          wrap.remove();
          showExamplePromptChips();
        },
        function () {
          chip.disabled = false;
          Array.prototype.forEach.call(wrap.querySelectorAll(".chip"), function (c) {
            c.disabled = false;
          });
        }
      );
    });
    wrap.appendChild(chip);
  });
  log.appendChild(wrap);
  scrollToBottom();
}

function showVisitorStatusChips() {
  var wrap = document.createElement("div");
  wrap.className = "chips-wrap";
  wrap.setAttribute("role", "group");
  wrap.setAttribute("aria-label", "Visiting or local");
  [["Visiting", "visiting"], ["Local", "local"]].forEach(function (pair) {
    var chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = pair[0];
    chip.addEventListener("click", function () {
      chip.disabled = true;
      Array.prototype.forEach.call(wrap.querySelectorAll(".chip"), function (c) {
        c.disabled = true;
      });
      postOnboarding(
        { visitor_status: pair[1] },
        function () {
          wrap.remove();
          addRow("bot", "Kids with you?");
          showKidsChips();
        },
        function () {
          chip.disabled = false;
          Array.prototype.forEach.call(wrap.querySelectorAll(".chip"), function (c) {
            c.disabled = false;
          });
        }
      );
    });
    wrap.appendChild(chip);
  });
  log.appendChild(wrap);
  scrollToBottom();
}

function showOnboardingFirstTurn() {
  addRow("bot", "Hey — welcome to Havasu. You visiting, or local?");
  showVisitorStatusChips();
}

showOnboardingFirstTurn();

form.addEventListener("submit", function (e) {
  e.preventDefault();
  var text = input.value.trim();
  if (!text) return;
  removeAllChipsWraps();
  input.value = "";
  addRow("user", text);
  var pendingOut = addRow("bot", "…", "loading");
  var pendingBubble = pendingOut.bubble;
  var pendingRow = pendingOut.row;

  setLoading(true);
  fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, query: text }),
  })
    .then(function (res) {
      if (!res.ok) throw new Error("Request failed");
      return res.json();
    })
    .then(function (data) {
      pendingBubble.classList.remove("loading");
      setBubbleContentFromAssistant(pendingBubble, data.response);
      if (data.chat_log_id != null && data.chat_log_id !== "") {
        pendingRow.setAttribute("data-chat-log-id", String(data.chat_log_id));
      } else {
        pendingRow.removeAttribute("data-chat-log-id");
      }
      if (data.tier_used != null && data.tier_used !== "") {
        pendingRow.setAttribute("data-tier-used", String(data.tier_used));
      } else {
        pendingRow.removeAttribute("data-tier-used");
      }
      if (data.tier_used === "3" && data.chat_log_id) {
        attachFeedbackThumbs(pendingRow, String(data.chat_log_id));
      }
      attachShareButtons();
      scrollToBottom();
      if (data && data.data && data.data.open_calendar && havasuChatCalendar) {
        havasuChatCalendar.open();
      }
    })
    .catch(function () {
      pendingBubble.classList.remove("loading");
      pendingBubble.textContent = "Hmm, that didn’t go through — check your connection and try again.";
      scrollToBottom();
    })
    .finally(function () {
      setLoading(false);
      input.focus();
    });
});

input.focus();
attachShareButtons();
