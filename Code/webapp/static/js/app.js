/* Advance Search front end: small, dependency-free helpers on top of htmx. */
(function () {
  "use strict";

  var THEME_KEY = "advsearch-theme";
  var RECENT_KEY = "advsearch-recent";
  var MAX_RECENT = 6;

  function $(selector, root) { return (root || document).querySelector(selector); }
  function $all(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
    } catch (e) { return null; }
    return null;
  }
  function csrfToken() { var m = $('meta[name="csrf-token"]'); return m ? m.getAttribute("content") : ""; }

  // ------------------------------------------------------------------ toast
  var toastTimer;
  function toast(message) {
    var el = $("#toast");
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 2600);
  }

  // ------------------------------------------------------------------ theme
  function effectiveTheme() {
    var explicit = document.documentElement.getAttribute("data-theme");
    if (explicit) return explicit;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function labelThemeButton() {
    var btn = $("#theme-toggle");
    if (!btn) return;
    var next = effectiveTheme() === "dark" ? "light" : "dark";
    btn.setAttribute("aria-label", "Switch to " + next + " theme");
    btn.setAttribute("title", "Switch to " + next + " theme");
  }
  function initTheme() {
    var btn = $("#theme-toggle");
    if (!btn) return;
    labelThemeButton();
    btn.addEventListener("click", function () {
      var next = effectiveTheme() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      store(THEME_KEY, next);
      labelThemeButton();
    });
    if (window.matchMedia) {
      var mq = window.matchMedia("(prefers-color-scheme: dark)");
      if (mq.addEventListener) mq.addEventListener("change", labelThemeButton);
    }
  }

  // ------------------------------------------------------------------ match meters
  function initMeters(root) {
    $all(".match[data-match]", root).forEach(function (el) {
      if (el.classList.contains("is-ready")) return;
      var value = Math.max(0, Math.min(100, parseInt(el.getAttribute("data-match"), 10) || 0));
      el.style.setProperty("--match", value + "%");
      el.style.setProperty("--match-hue", String(Math.round(4 + value * 1.36)));  // red -> amber -> green
      el.classList.add("has-hue");
      requestAnimationFrame(function () { requestAnimationFrame(function () { el.classList.add("is-ready"); }); });
    });
  }

  // ------------------------------------------------------------------ search page
  function recent() {
    try { var list = JSON.parse(store(RECENT_KEY) || "[]"); return Array.isArray(list) ? list.filter(function (q) { return typeof q === "string"; }) : []; }
    catch (e) { return []; }
  }
  function saveRecent(query) {
    query = (query || "").trim();
    if (!query) return;
    var list = recent().filter(function (q) { return q.toLowerCase() !== query.toLowerCase(); });
    list.unshift(query);
    store(RECENT_KEY, JSON.stringify(list.slice(0, MAX_RECENT)));
    renderRecent();
  }
  function renderRecent() {
    var row = $("#recent-searches");
    if (!row) return;
    var holder = $(".recent-list", row);
    var list = recent();
    holder.textContent = "";
    list.forEach(function (q) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip chip-recent";
      chip.setAttribute("data-query", q);
      chip.textContent = q;
      holder.appendChild(chip);
    });
    row.hidden = list.length === 0;
  }

  function initSearch() {
    var form = $("#search-form");
    if (!form) return;
    var input = $("#q", form);
    var clear = $("#clear-search");

    function syncClear() { if (clear) clear.hidden = !input.value; }
    function run(query) {
      input.value = query;
      syncClear();
      if (query.trim()) {
        if (form.requestSubmit) form.requestSubmit(); else htmx.trigger(form, "submit");
      }
    }

    input.addEventListener("input", syncClear);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && input.value) { e.preventDefault(); input.value = ""; syncClear(); }
    });
    form.addEventListener("submit", function (e) {
      if (!input.value.trim()) { e.preventDefault(); e.stopImmediatePropagation(); input.focus(); }
    }, true);
    if (clear) clear.addEventListener("click", function () {
      input.value = "";
      syncClear();
      $("#results").textContent = "";
      document.body.classList.remove("has-query");
      history.replaceState(null, "", window.location.pathname);
      document.title = "Advance Search";
      input.focus();
    });

    document.addEventListener("click", function (e) {
      var chip = e.target.closest ? e.target.closest(".chip[data-query]") : null;
      if (chip) run(chip.getAttribute("data-query"));
    });
    var clearRecent = $("#clear-recent");
    if (clearRecent) clearRecent.addEventListener("click", function () { store(RECENT_KEY, null); renderRecent(); input.focus(); });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      var t = e.target;
      var typing = t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
      if (typing) return;
      e.preventDefault();
      input.focus();
      input.select();
    });

    document.body.addEventListener("htmx:afterSwap", function (e) {
      if (!e.detail.target || e.detail.target.id !== "results") return;
      var query = input.value.trim();
      document.body.classList.toggle("has-query", !!query);
      var url = query ? "?q=" + encodeURIComponent(query) : window.location.pathname;
      if (window.location.search !== (query ? url : "")) history.pushState({ q: query }, "", url);
      document.title = query ? query + " · Advance Search" : "Advance Search";
      if (query && $(".result-card", e.detail.target)) saveRecent(query);
      initMeters(e.detail.target);
    });
    document.body.addEventListener("htmx:responseError", function (e) {
      if (!e.detail.target || e.detail.target.id !== "results") return;
      var box = document.createElement("div");
      box.className = "empty-state empty-error";
      box.setAttribute("role", "alert");
      var h = document.createElement("h2");
      h.textContent = "Search is temporarily unavailable";
      var p = document.createElement("p");
      p.textContent = "Try again in a moment.";
      box.appendChild(h);
      box.appendChild(p);
      e.detail.target.textContent = "";
      e.detail.target.appendChild(box);
    });
    window.addEventListener("popstate", function () {
      var q = new URLSearchParams(window.location.search).get("q") || "";
      if (q) run(q); else { input.value = ""; syncClear(); $("#results").textContent = ""; document.body.classList.remove("has-query"); }
    });

    renderRecent();
    syncClear();
    if (input.value.trim()) saveRecent(input.value); else input.focus();
  }

  // ------------------------------------------------------------------ copy link
  function initCopy() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest ? e.target.closest("[data-copy]") : null;
      if (!btn) return;
      var url = new URL(btn.getAttribute("data-copy"), window.location.href).href;
      function done() { toast("Link copied"); }
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(url).then(done, function () { fallbackCopy(url) ? done() : toast(url); });
      } else if (fallbackCopy(url)) { done(); } else { toast(url); }
    });
  }
  function fallbackCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.className = "visually-hidden";
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    document.body.removeChild(area);
    return ok;
  }

  // ------------------------------------------------------------------ confirmation dialog
  function initConfirm() {
    var dialog = $("#confirm-dialog");
    document.addEventListener("submit", function (e) {
      var form = e.target;
      if (!form.hasAttribute || !form.hasAttribute("data-confirm")) return;
      if (form.getAttribute("data-confirmed") === "1") { form.removeAttribute("data-confirmed"); return; }
      e.preventDefault();
      e.stopImmediatePropagation();
      if (!dialog || !dialog.showModal) {
        if (window.confirm(form.getAttribute("data-confirm"))) { form.setAttribute("data-confirmed", "1"); form.requestSubmit(); }
        return;
      }
      $("#confirm-title").textContent = form.getAttribute("data-confirm-title") || "Are you sure?";
      $("#confirm-message").textContent = form.getAttribute("data-confirm");
      $("#confirm-ok").textContent = form.getAttribute("data-confirm-ok") || "Confirm";
      dialog.returnValue = "";
      dialog.showModal();
      dialog.addEventListener("close", function onClose() {
        dialog.removeEventListener("close", onClose);
        if (dialog.returnValue === "confirm") { form.setAttribute("data-confirmed", "1"); form.requestSubmit(); }
      });
    }, true);
  }

  // ------------------------------------------------------------------ uploads
  var ALLOWED = [".pdf", ".docx", ".xlsx"];
  function initUpload() {
    var form = $("#upload-form");
    if (!form) return;
    var input = $("#file-input");
    var list = $("#upload-list");
    var maxBytes = (parseInt(form.getAttribute("data-max-mb"), 10) || 20) * 1024 * 1024;
    var queue = [];
    var busy = false;

    function item(file) {
      var li = document.createElement("li");
      li.className = "upload-item";
      var name = document.createElement("span");
      name.className = "upload-name";
      name.textContent = file.name;
      var state = document.createElement("span");
      state.className = "upload-state";
      state.textContent = "Waiting";
      var progress = document.createElement("div");
      progress.className = "progress";
      progress.setAttribute("role", "progressbar");
      progress.setAttribute("aria-label", "Upload progress for " + file.name);
      progress.setAttribute("aria-valuemin", "0");
      progress.setAttribute("aria-valuemax", "100");
      progress.setAttribute("aria-valuenow", "0");
      var bar = document.createElement("div");
      bar.className = "progress-bar";
      progress.appendChild(bar);
      var msg = document.createElement("p");
      msg.className = "upload-msg";
      li.appendChild(name); li.appendChild(state); li.appendChild(progress); li.appendChild(msg);
      list.appendChild(li);
      return {
        li: li,
        set: function (pct, text) {
          bar.style.setProperty("--progress", pct + "%");
          progress.setAttribute("aria-valuenow", String(Math.round(pct)));
          if (text) state.textContent = text;
        },
        finish: function (ok, text) {
          li.classList.add(ok ? "is-done" : "is-error");
          state.textContent = ok ? "Uploaded" : "Not uploaded";
          bar.style.setProperty("--progress", "100%");
          progress.setAttribute("aria-valuenow", "100");
          msg.textContent = text || "";
        }
      };
    }

    function validate(file) {
      var name = file.name.toLowerCase();
      if (!ALLOWED.some(function (ext) { return name.slice(-ext.length) === ext; })) return "Only PDF (.pdf), Word (.docx) and Excel (.xlsx) files are supported.";
      if (file.size === 0) return "The file is empty.";
      if (file.size > maxBytes) return "The file is larger than the " + (maxBytes / 1048576) + " MB limit.";
      return "";
    }

    function next() {
      if (busy) return;
      var job = queue.shift();
      if (!job) { refreshTable(); return; }
      busy = true;
      var data = new FormData();
      data.append("file", job.file, job.file.name);
      var xhr = new XMLHttpRequest();
      xhr.open("POST", form.getAttribute("action"));
      xhr.setRequestHeader("Accept", "application/json");
      xhr.setRequestHeader("X-CSRFToken", csrfToken());
      xhr.upload.addEventListener("progress", function (e) {
        if (e.lengthComputable) job.ui.set(Math.min(99, (e.loaded / e.total) * 100), "Uploading " + Math.round((e.loaded / e.total) * 100) + "%");
      });
      xhr.addEventListener("load", function () {
        var body = {};
        try { body = JSON.parse(xhr.responseText); } catch (err) { body = {}; }
        if (xhr.status === 401) { window.location.reload(); return; }
        job.ui.finish(xhr.status === 200 && body.ok, body.message || (xhr.status === 413 ? "The file is too large." : "The upload failed. Try again."));
        busy = false;
        next();
      });
      xhr.addEventListener("error", function () { job.ui.finish(false, "Network error. Check your connection and try again."); busy = false; next(); });
      job.ui.set(1, "Uploading");
      xhr.send(data);
    }

    function addFiles(files) {
      Array.prototype.forEach.call(files, function (file) {
        var ui = item(file);
        var problem = validate(file);
        if (problem) { ui.finish(false, problem); return; }
        queue.push({ file: file, ui: ui });
      });
      next();
    }

    function refreshTable() {
      var filters = $("#doc-filters");
      if (filters && window.htmx) htmx.trigger(filters, "submit");
    }

    input.addEventListener("change", function () { addFiles(input.files); input.value = ""; });
    form.addEventListener("click", function (e) { if (e.target === form || e.target.closest(".dropzone-inner") && !e.target.closest("label")) input.click(); });
    ["dragenter", "dragover"].forEach(function (type) {
      form.addEventListener(type, function (e) { e.preventDefault(); form.classList.add("is-dragover"); });
    });
    ["dragleave", "dragend", "drop"].forEach(function (type) {
      form.addEventListener(type, function (e) { e.preventDefault(); form.classList.remove("is-dragover"); });
    });
    form.addEventListener("drop", function (e) { if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files); });
    form.addEventListener("submit", function (e) { e.preventDefault(); if (input.files.length) addFiles(input.files); });
  }

  // ------------------------------------------------------------------ misc
  function initReveal() {
    $all("[data-reveal]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var field = document.getElementById(btn.getAttribute("data-reveal"));
        var show = field.type === "password";
        field.type = show ? "text" : "password";
        btn.setAttribute("aria-pressed", show ? "true" : "false");
        btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      });
    });
  }
  function initPopovers() {
    document.addEventListener("click", function (e) {
      $all("details.popover[open]").forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute("open"); });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      $all("details.popover[open]").forEach(function (d) { d.removeAttribute("open"); var s = $("summary", d); if (s) s.focus(); });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTheme();
    initMeters(document);
    initSearch();
    initCopy();
    initConfirm();
    initUpload();
    initReveal();
    initPopovers();
    document.body.addEventListener("htmx:afterSettle", function (e) { initMeters(e.detail.target); });
  });
})();
