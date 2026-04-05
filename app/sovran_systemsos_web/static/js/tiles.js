"use strict";

// ── Render: initial build ─────────────────────────────────────────

function buildTiles(services, categoryLabels) {
  _servicesCache = services;
  var grouped = {};
  var supportServices = [];
  for (var i = 0; i < services.length; i++) {
    var svc = services[i];
    // Support tiles go to the sidebar, not the main grid
    if (svc.category === "support" || svc.type === "support") {
      supportServices.push(svc);
      continue;
    }
    var cat = svc.category || "other";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(svc);
  }
  renderSidebarSupport(supportServices);
  $tilesArea.innerHTML = "";
  var orderedKeys = CATEGORY_ORDER.filter(function(k) { return grouped[k]; });
  Object.keys(grouped).forEach(function(k) {
    if (orderedKeys.indexOf(k) === -1) orderedKeys.push(k);
  });
  for (var j = 0; j < orderedKeys.length; j++) {
    var catKey = orderedKeys[j];
    var entries = grouped[catKey];
    if (!entries || entries.length === 0) continue;
    var label = categoryLabels[catKey] || catKey;
    var section = document.createElement("div");
    section.className = "category-section";
    section.dataset.category = catKey;
    section.innerHTML = '<div class="section-header">' + escHtml(label) + '</div><hr class="section-divider" /><div class="tiles-grid" data-cat="' + escHtml(catKey) + '"></div>';
    var grid = section.querySelector(".tiles-grid");
    for (var k = 0; k < entries.length; k++) {
      grid.appendChild(buildTile(entries[k]));
    }
    $tilesArea.appendChild(section);
  }
  if ($tilesArea.children.length === 0) {
    $tilesArea.innerHTML = '<div class="empty-state"><p>No services configured.</p></div>';
  }
}

function renderSidebarSupport(supportServices) {
  $sidebarSupport.innerHTML = "";

  // ── Update System button (above Tech Help)
  var sidebarUpdateBtn = document.createElement("button");
  sidebarUpdateBtn.className = "sidebar-support-btn";
  sidebarUpdateBtn.id = "sidebar-btn-update";
  sidebarUpdateBtn.innerHTML =
    '<img class="sidebar-support-icon" src="/static/icons/update.svg" alt="Update" style="width:1.5rem;height:1.5rem;">' +
    '<span class="sidebar-support-text">' +
      '<span class="sidebar-support-title">Update System</span>' +
      '<span class="sidebar-support-hint" id="sidebar-update-hint">Check for updates</span>' +
    '</span>';
  sidebarUpdateBtn.addEventListener("click", function() { openUpdateModal(); });
  $sidebarSupport.appendChild(sidebarUpdateBtn);

  for (var i = 0; i < supportServices.length; i++) {
    var svc = supportServices[i];
    var btn = document.createElement("button");
    btn.className = "sidebar-support-btn";
    btn.innerHTML =
      '<span class="sidebar-support-icon">🛟</span>' +
      '<span class="sidebar-support-text">' +
        '<span class="sidebar-support-title">' + escHtml(svc.name || "Tech Support") + '</span>' +
        '<span class="sidebar-support-hint">Click for help</span>' +
      '</span>';
    btn.addEventListener("click", function() { openSupportModal(); });
    $sidebarSupport.appendChild(btn);
  }

  // ── Manual Backup button
  var backupBtn = document.createElement("button");
  backupBtn.className = "sidebar-support-btn";
  backupBtn.innerHTML =
    '<span class="sidebar-support-icon">💾</span>' +
    '<span class="sidebar-support-text">' +
      '<span class="sidebar-support-title">Manual Backup</span>' +
      '<span class="sidebar-support-hint">Back up to external drive</span>' +
    '</span>';
  backupBtn.addEventListener("click", function() { openBackupModal(); });
  $sidebarSupport.appendChild(backupBtn);

  // ── Upgrade button (Node role only)
  if (_currentRole === "node") {
    var upgradeBtn = document.createElement("button");
    upgradeBtn.className = "sidebar-support-btn sidebar-upgrade-btn";
    upgradeBtn.innerHTML =
      '<span class="sidebar-support-icon">🚀</span>' +
      '<span class="sidebar-support-text">' +
        '<span class="sidebar-support-title">Upgrade to Full Server</span>' +
        '<span class="sidebar-support-hint">Unlock all services</span>' +
      '</span>';
    upgradeBtn.addEventListener("click", function() { openUpgradeModal(); });
    $sidebarSupport.appendChild(upgradeBtn);
  }

  var hr = document.createElement("hr");
  hr.className = "sidebar-divider";
  $sidebarSupport.appendChild(hr);
}

function buildTile(svc) {
  var isSupport = svc.type === "support";
  var sc = statusClass(svc.health || svc.status);
  var st = statusText(svc.health || svc.status, svc.enabled);
  var dis = !svc.enabled;

  var tile = document.createElement("div");
  tile.className = "service-tile" + (dis ? " disabled" : "") + (isSupport ? " support-tile" : "");
  tile.dataset.unit = svc.unit;
  tile.dataset.tileId = tileId(svc);
  if (dis) tile.title = svc.name + " is not enabled in custom.nix";

  if (isSupport) {
    tile.innerHTML = '<img class="tile-icon" src="/static/icons/' + escHtml(svc.icon) + '.svg" alt="' + escHtml(svc.name) + '" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"><div class="tile-icon-fallback" style="display:none">?</div><div class="tile-name">' + escHtml(svc.name) + '</div><div class="tile-status"><span class="support-status-label">Click for help</span></div>';
    tile.style.cursor = "pointer";
    tile.addEventListener("click", function() { openSupportModal(); });
    return tile;
  }

  tile.innerHTML = '<img class="tile-icon" src="/static/icons/' + escHtml(svc.icon) + '.svg" alt="' + escHtml(svc.name) + '" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"><div class="tile-icon-fallback" style="display:none">?</div><div class="tile-name">' + escHtml(svc.name) + '</div><div class="tile-status"><span class="status-dot ' + sc + '"></span><span class="status-text">' + st + '</span></div>';

  tile.style.cursor = "pointer";
  tile.addEventListener("click", function() {
    openServiceDetailModal(svc.unit, svc.name, svc.icon);
  });

  return tile;
}

// ── Render: live update ───────────────────────────────────────────

function updateTiles(services) {
  _servicesCache = services;
  for (var i = 0; i < services.length; i++) {
    var svc = services[i];
    if (svc.type === "support") continue;
    var id = CSS.escape(tileId(svc));
    var tile = $tilesArea.querySelector('.service-tile[data-tile-id="' + id + '"]');
    if (!tile) continue;
    var sc = statusClass(svc.health || svc.status);
    var st = statusText(svc.health || svc.status, svc.enabled);
    var dot = tile.querySelector(".status-dot");
    var text = tile.querySelector(".status-text");
    if (dot) dot.className = "status-dot " + sc;
    if (text) text.textContent = st;
  }
}

// ── Service polling ───────────────────────────────────────────────

var _firstLoad = true;

async function refreshServices() {
  try {
    var services = await apiFetch("/api/services");
    if (_firstLoad) { buildTiles(services, _categoryLabels); _firstLoad = false; }
    else { updateTiles(services); }
  } catch (err) { console.warn("Failed to fetch services:", err); }
}

// ── Network IPs ───────────────────────────────────────────────────

async function loadNetwork() {
  try {
    var data = await apiFetch("/api/network");
    if ($internalIp) $internalIp.textContent = data.internal_ip || "—";
    if ($externalIp) $externalIp.textContent = data.external_ip || "—";
    _cachedExternalIp = data.external_ip || "unavailable";
  } catch (_) {
    if ($internalIp) $internalIp.textContent = "—";
    if ($externalIp) $externalIp.textContent = "—";
  }
}

// ── Update check ──────────────────────────────────────────────────

async function checkUpdates() {
  try {
    var data = await apiFetch("/api/updates/check");
    var hasUpdates = !!data.available;
    var sidebarUpdateBtn = document.getElementById("sidebar-btn-update");
    var sidebarUpdateHint = document.getElementById("sidebar-update-hint");
    if (sidebarUpdateBtn) {
      if (hasUpdates) {
        sidebarUpdateBtn.style.borderColor = "#2ec27e";
        sidebarUpdateBtn.style.backgroundColor = "rgba(46, 194, 126, 0.08)";
        if (sidebarUpdateHint) sidebarUpdateHint.textContent = "Updates available!";
      } else {
        sidebarUpdateBtn.style.borderColor = "";
        sidebarUpdateBtn.style.backgroundColor = "";
        if (sidebarUpdateHint) sidebarUpdateHint.textContent = "System is up to date";
      }
    }
  } catch (_) {}
}
