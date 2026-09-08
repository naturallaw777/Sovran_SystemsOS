"use strict";

/* ── The Hub dashboard chrome ──────────────────────────────────────
   Welcome dashboard (default view), category navigation, service
   search, status cards, and the Systems Operational modal.

   Everything lives in an IIFE so no globals leak into the other Hub
   scripts; tiles.js calls window.dashboardServicesUpdated() whenever
   the service list refreshes. */

(function () {

  var $nav = document.getElementById("sidebar-nav");
  var $pageTitle = document.getElementById("page-title");
  var $search = document.getElementById("search-input");
  var $sysModal = document.getElementById("systems-modal");
  var $sysBody = document.getElementById("systems-body");
  var $welcome = document.getElementById("welcome-view");
  var $tilesArea = document.getElementById("tiles-area");
  var $wcSystems = document.getElementById("wc-systems");
  var $wcMore = document.getElementById("wc-more");
  var $greeting = document.getElementById("welcome-greeting");
  var $welcomeRole = document.getElementById("welcome-role");
  var $browseBtn = document.getElementById("welcome-browse-btn");

  var _view = "dashboard";   // "dashboard" | "services"
  var _cat = "all";
  var _query = "";

  var CAT_ICONS = {
    "all":            "g-grid",
    "infrastructure": "g-server",
    "bitcoin":        "g-btc-sym",
    "communication":  "g-chat",
    "apps":           "g-dots",
    "nostr":          "g-antenna",
    "other":          "g-dots"
  };

  var CAT_FALLBACK_LABELS = {
    "infrastructure": "Infrastructure",
    "bitcoin":        "Bitcoin",
    "communication":  "Communication",
    "apps":           "Personal Apps",
    "nostr":          "Nostr",
    "other":          "Other"
  };

  /* Units that serve a domain — used to find a live diagnostics
     checklist for the Systems Operational modal (order matters only
     for which service is polled first). */
  var DOMAIN_UNITS = [
    "matrix-synapse.service",
    "btcpayserver.service",
    "vaultwarden.service",
    "phpfpm-nextcloud.service",
    "phpfpm-wordpress.service",
    "haven-relay.service",
    "livekit.service",
    "albyhub.service"
  ];

  function icon(id) {
    return '<svg><use href="#' + id + '"/></svg>';
  }

  function visibleServices() {
    var services = (typeof _servicesCache !== "undefined" && _servicesCache) ? _servicesCache : [];
    return services.filter(function (s) {
      return s.category !== "support" && s.type !== "support";
    });
  }

  /* ── Views ────────────────────────────────────────────────────── */

  function setTitle(t) {
    if ($pageTitle) $pageTitle.textContent = t;
  }

  function syncNav() {
    if (!$nav) return;
    $nav.querySelectorAll(".nav-item").forEach(function (b) {
      var isActive;
      if (b.dataset.cat === "__dash") isActive = (_view === "dashboard");
      else isActive = (_view === "services" && b.dataset.cat === _cat);
      b.classList.toggle("active", isActive);
    });
  }

  function showDashboard() {
    _view = "dashboard";
    _cat = "all";
    if ($welcome) $welcome.style.display = "";
    if ($tilesArea) $tilesArea.style.display = "none";
    setTitle("Dashboard");
    syncNav();
  }

  function showServices(cat) {
    _view = "services";
    if (cat) _cat = cat;
    if ($welcome) $welcome.style.display = "none";
    if ($tilesArea) $tilesArea.style.display = "";
    setTitle(_cat === "all" ? "All services" : catLabel(_cat));
    syncNav();
    applyFilter();
  }

  /* ── Category navigation ──────────────────────────────────────── */

  function renderNav() {
    if (!$nav) return;
    var counts = {};
    var order = [];
    visibleServices().forEach(function (s) {
      var cat = s.category || "other";
      if (CATEGORY_ALIASES[cat]) cat = CATEGORY_ALIASES[cat];
      if (!counts[cat]) { counts[cat] = 0; order.push(cat); }
      counts[cat]++;
    });
    var total = visibleServices().length;

    var html = '<div class="nav-label">Menu</div>';
    html += '<button class="nav-item' + (_view === "dashboard" ? " active" : "") + '" data-cat="__dash" type="button">' +
      icon("g-home") +
      '<span class="nav-text">Dashboard</span>' +
      '</button>';
    html += '<div class="nav-label">Services</div>';
    html += navItem("all", "All services", total);
    order.forEach(function (cat) {
      html += navItem(cat, catLabel(cat), counts[cat]);
    });
    $nav.innerHTML = html;

    $nav.querySelectorAll(".nav-item").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (btn.dataset.cat === "__dash") showDashboard();
        else showServices(btn.dataset.cat);
      });
    });
  }

  function navItem(cat, label, count) {
    return '<button class="nav-item' + (_view === "services" && cat === _cat ? " active" : "") + '" data-cat="' + escHtml(cat) + '" type="button">' +
      icon(CAT_ICONS[cat] || "g-dots") +
      '<span class="nav-text">' + escHtml(label) + '</span>' +
      '<span class="nav-count">' + count + '</span>' +
      '</button>';
  }

  function catLabel(cat) {
    if (typeof _categoryLabels !== "undefined" && _categoryLabels[cat]) return _categoryLabels[cat];
    return CAT_FALLBACK_LABELS[cat] || cat;
  }

  /* ── Filtering (applies in the services view) ─────────────────── */

  function applyFilter() {
    if (_view !== "services") return;
    var area = $tilesArea;
    if (!area) return;
    var q = _query.trim().toLowerCase();
    area.querySelectorAll(".category-section").forEach(function (section) {
      var catMatch = (_cat === "all") || (section.dataset.category === _cat);
      var anyVisible = false;
      section.querySelectorAll(".service-tile").forEach(function (tile) {
        var nameEl = tile.querySelector(".tile-name");
        var name = nameEl ? nameEl.textContent.toLowerCase() : "";
        var match = catMatch && (!q || name.indexOf(q) !== -1);
        tile.style.display = match ? "" : "none";
        if (match) anyVisible = true;
      });
      section.style.display = (catMatch && (anyVisible || !q)) ? "" : "none";
    });
  }

  if ($search) {
    $search.addEventListener("input", function () {
      // Searching implies browsing services — leave the welcome view.
      if (_view === "dashboard" && $search.value) showServices("all");
      _query = $search.value;
      applyFilter();
    });
  }

  if ($browseBtn) {
    $browseBtn.addEventListener("click", function () { showServices("all"); });
  }

  /* ── Welcome header ───────────────────────────────────────────── */

  function updateWelcomeMeta() {
    if ($greeting) {
      var h = new Date().getHours();
      var g;
      if (h >= 5 && h < 12) g = "Good morning";
      else if (h >= 12 && h < 17) g = "Good afternoon";
      else g = "Good evening";
      $greeting.textContent = g;
    }
    if ($welcomeRole) {
      $welcomeRole.textContent = (typeof window._roleLabel !== "undefined" && window._roleLabel) ? window._roleLabel : "";
    }
  }

  /* ── Status cards ─────────────────────────────────────────────── */

  function serviceCounts() {
    var services = visibleServices();
    var running = 0, attention = 0, off = 0;
    var attentionNames = [], offNames = [];
    services.forEach(function (s) {
      if (!s.enabled) { off++; offNames.push(s.name); return; }
      var h = s.health || s.status;
      if (h === "needs_attention" || h === "failed") { attention++; attentionNames.push(s.name); }
      else running++;
    });
    return { services: services, running: running, attention: attention, off: off, attentionNames: attentionNames, offNames: offNames };
  }

  function renderWidgets() {
    if (!$wcSystems) return;
    var c = serviceCounts();
    if (!c.services.length) { $wcSystems.innerHTML = ""; if ($wcMore) $wcMore.innerHTML = ""; return; }

    /* Systems operational */
    var sub = '<b>' + c.running + '</b> running';
    if (c.attention) sub += ' · <span class="warn">' + c.attention + ' needs attention</span>';
    if (c.off) sub += ' · ' + c.off + ' off';
    var attentionTitle = c.attention ? "Systems need attention" : "Systems operational";
    $wcSystems.innerHTML =
      '<div class="widget clickable" id="w-systems" role="button" tabindex="0" title="System status and router setup">' +
        '<div class="widget-chip chip-green">' + icon("g-shield-check") + '</div>' +
        '<div class="w-body"><h3>' + attentionTitle + '</h3><div class="sub">' + sub + '</div></div>' +
        '<span class="w-chev">' + icon("g-chev") + '</span>' +
      '</div>';

    var wSys = document.getElementById("w-systems");
    if (wSys) {
      wSys.addEventListener("click", openSystemsModal);
      wSys.addEventListener("keydown", function (e) { if (e.key === "Enter") openSystemsModal(); });
    }

    if (!$wcMore) return;
    var more = "";

    /* Bitcoin Core sync */
    var btc = null;
    c.services.forEach(function (s) {
      if (s.sync_ibd && s.enabled) btc = s;
    });
    if (btc) {
      var pct = Math.round((btc.sync_progress || 0) * 100);
      var blocks = btc.sync_blocks ? btc.sync_blocks.toLocaleString() : "—";
      var eta = (typeof _calcBtcEta === "function") ? _calcBtcEta(btc.unit + "::" + btc.name, btc.sync_progress || 0) : "";
      more +=
        '<div class="widget clickable" id="w-btc" role="button" tabindex="0" title="' + escHtml(btc.name) + ' details">' +
          '<div class="widget-chip chip-btc"><img src="/static/icons/' + escHtml(btc.icon) + '.svg" alt="" style="width:46px;height:46px;display:block;object-fit:contain"/></div>' +
          '<div class="w-body"><h3>' + escHtml(btc.name) + ' — syncing timechain</h3>' +
          '<div class="w-bar"><div class="w-bar-fill" style="width:' + pct + '%"></div></div>' +
          '<div class="sub">Block <b>' + blocks + '</b> · ' + pct + '% · <span class="warn">' + escHtml(eta) + '</span></div></div>' +
          '<span class="w-chev">' + icon("g-chev") + '</span>' +
        '</div>';
    } else {
      var btcDone = null;
      c.services.forEach(function (s) { if (s.unit === "bitcoind.service" && s.enabled) btcDone = s; });
      if (btcDone) {
        var blk = btcDone.sync_blocks ? btcDone.sync_blocks.toLocaleString() : "";
        more +=
          '<div class="widget clickable" id="w-btc" role="button" tabindex="0" title="' + escHtml(btcDone.name) + ' details">' +
            '<div class="widget-chip chip-btc"><img src="/static/icons/' + escHtml(btcDone.icon) + '.svg" alt="" style="width:46px;height:46px;display:block;object-fit:contain"/></div>' +
            '<div class="w-body"><h3>' + escHtml(btcDone.name) + '</h3><div class="sub"><span class="good">Fully synced</span>' + (blk ? ' · Block <b>' + blk + '</b>' : '') + '</div></div>' +
            '<span class="w-chev">' + icon("g-chev") + '</span>' +
          '</div>';
      }
    }

    /* Updates */
    var upd = (typeof window._lastUpdateCheck === "object" && window._lastUpdateCheck) ? window._lastUpdateCheck : null;
    var hasUpdates = !!(upd && upd.available);
    more +=
      '<div class="widget clickable" id="w-updates" role="button" tabindex="0" title="Check for system updates">' +
        '<div class="widget-chip ' + (hasUpdates ? "chip-amber" : "chip-green") + '">' + icon("g-update") + '</div>' +
        '<div class="w-body"><h3>' + (hasUpdates ? "Updates available" : "System is up to date") + '</h3>' +
        '<div class="sub">' + (hasUpdates ? 'Click to review and update' : 'Sovran_SystemsOS keeps itself current') + '</div></div>' +
        '<span class="w-chev">' + icon("g-chev") + '</span>' +
      '</div>';

    $wcMore.innerHTML = more;

    var wBtc = document.getElementById("w-btc");
    if (wBtc) {
      var svc = btc || btcDone;
      if (svc) {
        wBtc.addEventListener("click", function () { openServiceDetailModal(svc.unit, svc.name, svc.icon); });
        wBtc.addEventListener("keydown", function (e) { if (e.key === "Enter") openServiceDetailModal(svc.unit, svc.name, svc.icon); });
      }
    }
    var wUpd = document.getElementById("w-updates");
    if (wUpd) {
      wUpd.addEventListener("click", function () { openUpdateModal(); });
      wUpd.addEventListener("keydown", function (e) { if (e.key === "Enter") openUpdateModal(); });
    }
  }

  /* ── Systems Operational modal ────────────────────────────────── */

  function isNodeRole() {
    return (typeof _currentRole !== "undefined" && _currentRole === "node");
  }

  function hasEnabledDomainService(services) {
    return DOMAIN_UNITS.some(function (u) {
      return services.some(function (s) { return s.unit === u && s.enabled; });
    });
  }

  function whoUsesPorts() {
    if (isNodeRole()) {
      return 'On this <strong>Bitcoin Node</strong> install, <strong>BTCPay Server</strong> and <strong>Lightning Wallet Connections (LNURL)</strong> are the domain services that use these ports.';
    }
    return 'All your domain services share ports 80 and 443 — Matrix, BTCPay Server, VaultWarden, Nextcloud, WordPress, Haven Relay, Lightning Wallet Connections, and Element Calling.';
  }

  function step(n, title, sub, value) {
    return '<div class="sysstep"><div class="sysnum">' + n + '</div><div class="sysstep-x">' +
      '<div class="sysstep-t">' + title + (sub ? ' <span class="sysstep-sub">· ' + sub + '</span>' : '') + '</div>' +
      (value ? '<div class="sysval"><span class="sysval-text">' + value + '</span></div>' : '') +
      '</div></div>';
  }

  function openSystemsModal() {
    if (!$sysModal || !$sysBody) return;
    var c = serviceCounts();

    var html = "";

    /* System status */
    html += '<div class="sysmodal-card">' +
      '<div class="sysmodal-card-title">' + icon("g-shield-check") + 'System Status</div>' +
      step(1, "Services running", "", String(c.running)) +
      step(2, "Needs attention", "", c.attention ? escHtml(c.attentionNames.join(", ")) : "None") +
      step(3, "Turned off", "", c.off ? escHtml(c.offNames.join(", ")) : "None") +
      '</div>';

    /* Router — a simple open / not-open verdict. How to open the ports is
       covered during onboarding, so the modal does not repeat instructions.
       Node-only role: ports only matter once BTCPay Server or Lightning
       Wallet Connections (LNURL) is turned on. */
    if (isNodeRole() && !hasEnabledDomainService(c.services)) {
      html += '<div class="sysmodal-card">' +
        '<div class="sysmodal-card-title">' + icon("g-wifi") + 'Router</div>' +
        '<div class="sysnote"><div class="sysnote-title">' + icon("g-check") + 'No router setup needed yet</div>' +
        '<div class="sysnote-desc">Ports 80 and 443 only need to be forwarded on your router if you turn on <strong>BTCPay Server</strong> or <strong>Lightning Wallet Connections (LNURL)</strong>. If you enable one of them, come back here to check your ports.</div></div>' +
        '</div>';
    } else {
      html += '<div class="sysmodal-card" id="sys-ports-card" style="display:none">' +
        '<div class="sysmodal-card-title">' + icon("g-wifi") + 'Router</div>' +
        '<div id="sys-ports-status"><div class="sysfineprint">Checking…</div></div>' +
        '</div>';
    }

    /* Who uses these ports (redundant on a Node install with no domain
       services on — the router note above already covers it) */
    if (!isNodeRole() || hasEnabledDomainService(c.services)) {
      html += '<div class="sysnote" style="margin-top:14px">' +
        '<div class="sysnote-title">' + icon("g-antenna") + 'Who uses these ports</div>' +
        '<div class="sysnote-desc">' + whoUsesPorts() + '</div></div>';
    }

    $sysBody.innerHTML = html;
    $sysModal.classList.add("open");

    /* Poll the first configured domain service and reduce its diagnostics
       to one verdict: the ports are open or they are not. */
    var portsCard = document.getElementById("sys-ports-card");
    var portsEl = document.getElementById("sys-ports-status");
    var units = DOMAIN_UNITS.filter(function (u) {
      return c.services.some(function (s) { return s.unit === u && s.enabled; });
    });
    if (!units.length || !portsCard || !portsEl) return;
    portsCard.style.display = "";

    apiFetch("/api/service-detail/" + encodeURIComponent(units[0]))
      .then(function (data) {
        var steps = (data && data.domain_check_steps) || [];
        var portsStep = null;
        steps.forEach(function (s) {
          if (Number(s.step) === 3 || /ports?\s*80/i.test(s.label || "")) portsStep = s;
        });
        if (!portsStep) { portsCard.style.display = "none"; return; }
        if (portsStep.status === "ok") {
          portsEl.innerHTML = '<div class="svc-detail-status" style="font-size:0.92rem"><span class="status-dot active"></span>Ports 80 and 443 are open</div>';
        } else {
          portsEl.innerHTML = '<div class="svc-detail-status" style="font-size:0.92rem"><span class="status-dot failed"></span>Ports 80 and 443 are not open</div>';
        }
      })
      .catch(function () {
        portsCard.style.display = "none";
      });
  }

  function closeSystemsModal() {
    if ($sysModal) $sysModal.classList.remove("open");
  }

  var sysClose = document.getElementById("systems-close-btn");
  if (sysClose) sysClose.addEventListener("click", closeSystemsModal);
  if ($sysModal) {
    $sysModal.addEventListener("click", function (e) {
      if (e.target === $sysModal) closeSystemsModal();
    });
    $sysModal.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeSystemsModal();
    });
  }

  /* ── Public hook for tiles.js ────────────────────────────────── */

  window.dashboardServicesUpdated = function () {
    renderNav();
    updateWelcomeMeta();
    renderWidgets();
    applyFilter();
  };

  // Initial view
  showDashboard();
  updateWelcomeMeta();

})();
