(function () {
  "use strict";

  const input = document.getElementById("home-ask-input");
  if (!input) return;

  const prompts = [
    "happy hour near the channel tonight",
    "dog groomers open Saturday",
    "boat rentals for 6",
    "pickleball courts open now",
    "kids activities this weekend",
  ];

  let idx = 0;
  window.setInterval(function () {
    idx = (idx + 1) % prompts.length;
    input.placeholder = prompts[idx];
  }, 2600);

  document.querySelectorAll(".ll-chip[data-q]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const q = btn.getAttribute("data-q") || "";
      input.value = q;
      const form = document.getElementById("home-ask-form");
      if (form) form.submit();
    });
  });

  // --- Search autocomplete (debounced) ----------------------------------
  function attachAutocomplete(field) {
    if (!field || field.dataset.acBound) return;
    field.dataset.acBound = "1";

    // Wrap the input in a positioned container so the dropdown can anchor
    // to it without disturbing the surrounding form layout.
    const wrap = document.createElement("span");
    wrap.className = "ll-ac-wrap";
    field.parentNode.insertBefore(wrap, field);
    wrap.appendChild(field);

    const list = document.createElement("ul");
    list.className = "ll-suggestions";
    list.hidden = true;
    wrap.appendChild(list);

    let items = [];
    let active = -1;
    let timer = null;
    let seq = 0;

    function close() {
      list.hidden = true;
      list.innerHTML = "";
      items = [];
      active = -1;
    }

    function setActive(i) {
      const lis = list.querySelectorAll("li");
      lis.forEach(function (el, n) {
        el.classList.toggle("is-active", n === i);
      });
      active = i;
    }

    function render(rows) {
      items = rows || [];
      list.innerHTML = "";
      active = -1;
      if (!items.length) {
        close();
        return;
      }
      items.forEach(function (it, i) {
        const li = document.createElement("li");
        li.setAttribute("role", "option");
        const name = document.createElement("span");
        name.className = "ll-ac-name";
        name.textContent = it.name || "";
        li.appendChild(name);
        if (it.subcategory) {
          const meta = document.createElement("span");
          meta.className = "ll-ac-meta";
          meta.textContent = String(it.subcategory).replace(/_/g, " ");
          li.appendChild(meta);
        }
        li.addEventListener("mousedown", function (e) {
          // mousedown (not click) so we beat the input's blur handler.
          e.preventDefault();
          choose(i);
        });
        list.appendChild(li);
      });
      list.hidden = false;
    }

    function choose(i) {
      const it = items[i];
      if (!it) return;
      if (it.url) {
        window.location.href = it.url;
      } else {
        field.value = it.name || "";
        close();
      }
    }

    function fetchSuggestions(q) {
      const mySeq = ++seq;
      fetch("/api/search/suggestions?q=" + encodeURIComponent(q), {
        headers: { Accept: "application/json" },
      })
        .then(function (r) {
          return r.ok ? r.json() : [];
        })
        .then(function (rows) {
          if (mySeq !== seq) return; // stale response
          render(Array.isArray(rows) ? rows : []);
        })
        .catch(function () {
          /* network error — silently ignore */
        });
    }

    field.setAttribute("autocomplete", "off");
    field.addEventListener("input", function () {
      const q = field.value.trim();
      if (timer) window.clearTimeout(timer);
      if (q.length < 2) {
        close();
        return;
      }
      timer = window.setTimeout(function () {
        fetchSuggestions(q);
      }, 200);
    });

    field.addEventListener("keydown", function (e) {
      if (list.hidden || !items.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((active + 1) % items.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((active - 1 + items.length) % items.length);
      } else if (e.key === "Enter") {
        if (active >= 0) {
          e.preventDefault();
          choose(active);
        }
      } else if (e.key === "Escape") {
        close();
      }
    });

    field.addEventListener("blur", function () {
      window.setTimeout(close, 120);
    });
  }

  attachAutocomplete(input);
  document
    .querySelectorAll(".ll-desktop-search input[name='q']")
    .forEach(attachAutocomplete);
})();
