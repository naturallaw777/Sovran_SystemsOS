/* Sovran_SystemsOS Hub — Vanilla JS Frontend
   v8 — Status-only dashboard + Tech Support + Feature Manager */
"use strict";

var POLL_INTERVAL_SERVICES = 5000;
var POLL_INTERVAL_UPDATES  = 1800000;
var UPDATE_POLL_INTERVAL   = 2000;
var REBOOT_CHECK_INTERVAL  = 5000;
var SUPPORT_TIMER_INTERVAL = 1000;

var CATEGORY_ORDER = [
  "infrastructure",
  "bitcoin-base",
  "bitcoin-apps",
  "communication",
  "apps",
  "nostr",
  "support",
  "feature-manager",
];

var FEATURE_SUBCATEGORY_LABELS = {
  "infrastructure": "🔧 Infrastructure",
  "bitcoin":        "₿ Bitcoin",
  "communication":  "💬 Communication",
  "nostr":          "📡 Nostr",
};

var FEATURE_SUBCATEGORY_ORDER = ["infrastructure", "bitcoin", "communication", "nostr"];

var FEATURE_UNIT_MAP = {
  "rdp": "gnome-remote-desktop.service",
  "haven": "haven-relay.service",
  "element-calling": "livekit.service",
  "mempool": "mempool-frontend.service",
};

var STATUS_LOADING_STATES = new Set([
  "reloading", "activating", "deactivating", "maintenance",
]);

// ── State ─────────────────────────────────────────────────────────

var _servicesCache    = [];
var _categoryLabels   = {};
var _updateLog        = "";
var _updatePollTimer  = null;
var _updateLogOffset  = 0;
var _serverWasDown    = false;
var _updateFinished   = false;
var _supportTimerInt  = null;
var _supportEnabledAt = null;
var _cachedExternalIp = null;

// Feature Manager state
var _featuresData       = null;
var _rebuildLog         = "";
var _rebuildLogOffset   = 0;
var _rebuildPollTimer   = null;
var _rebuildFinished    = false;
var _rebuildServerDown  = false;
var _pendingToggle      = null;

// ── DOM refs ──────────────────────────────────────────────────────

var $tilesArea      = document.getElementById("tiles-area");
var $updateBtn      = document.getElementById("btn-update");
var $updateBadge    = document.getElementById("update-badge");
var $refreshBtn     = document.getElementById("btn-refresh");
var $internalIp     = document.getElementById("ip-internal");
var $externalIp     = document.getElementById("ip-external");

var $modal          = document.getElementById("update-modal");
var $modalSpinner   = document.getElementById("modal-spinner");
var $modalStatus    = document.getElementById("modal-status");
var $modalLog       = document.getElementById("modal-log");
var $btnReboot      = document.getElementById("btn-reboot");
var $btnSave        = document.getElementById("btn-save-report");
var $btnCloseModal  = document.getElementById("btn-close-modal");

var $rebootOverlay  = document.getElementById("reboot-overlay");

var $credsModal     = document.getElementById("creds-modal");
var $credsTitle     = document.getElementById("creds-modal-title");
var $credsBody      = document.getElementById("creds-body");
var $credsCloseBtn  = document.getElementById("creds-close-btn");

var $supportModal     = document.getElementById("support-modal");
var $supportBody      = document.getElementById("support-body");
var $supportCloseBtn  = document.getElementById("support-close-btn");

// Feature Manager — rebuild modal
var $rebuildModal    = document.getElementById("rebuild-modal");
var $rebuildSpinner  = document.getElementById("rebuild-spinner");
var $rebuildStatus   = document.getElementById("rebuild-status");
var $rebuildLogEl    = document.getElementById("rebuild-log");
var $rebuildReboot   = document.getElementById("rebuild-reboot-btn");
var $rebuildSave     = document.getElementById("rebuild-save-report");
var $rebuildClose    = document.getElementById("rebuild-close-btn");

// Feature Manager — domain setup modal
var $domainSetupModal = document.getElementById("domain-setup-modal");
var $domainSetupTitle = document.getElementById("domain-setup-title");
var $domainSetupBody  = document.getElementById("domain-setup-body");
var $domainSetupClose = document.getElementById("domain-setup-close-btn");

// Feature Manager — SSL email modal
var $sslEmailModal  = document.getElementById("ssl-email-modal");
var $sslEmailInput  = document.getElementById("ssl-email-input");
var $sslEmailSave   = document.getElementById("ssl-email-save-btn");
var $sslEmailCancel = document.getElementById("ssl-email-cancel-btn");
var $sslEmailClose  = document.getElementById("ssl-email-close-btn");

// Feature Manager — confirm modal
var $featureConfirmModal   = document.getElementById("feature-confirm-modal");
var $featureConfirmMsg     = document.getElementById("feature-confirm-message");
var $featureConfirmOk      = document.getElementById("feature-confirm-ok-btn");
var $featureConfirmCancel  = document.getElementById("feature-confirm-cancel-btn");
var $featureConfirmClose   = document.getElementById("feature-confirm-close-btn");

// ── Helpers ───────────────────────────────────────────────────────

function tileId(svc) { return svc.unit + "::" + svc.name; }

function statusClass(status) {
  if (!status) return "unknown";
  if (status === "active")   return "active";
  if (status === "inactive") return "inactive";
  if (status === "failed")   return "failed";
  if (status === "disabled") return "disabled";
  if (STATUS_LOADING_STATES.has(status)) return "loading";
  return "unknown";
}

function statusText(status, enabled) {
  if (!enabled) return "disabled";
  if (!status || status === "unknown") return "unknown";
  return status;
}

function escHtml(str) {
  return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function linkify(str) {
  return escHtml(str).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" class="creds-link">$1</a>');
}

function formatDuration(seconds) {
  var h = Math.floor(seconds / 3600);
  var m = Math.floor((seconds % 3600) / 60);
  var s = Math.floor(seconds % 60);
  if (h > 0) return h + "h " + m + "m " + s + "s";
  if (m > 0) return m + "m " + s + "s";
  return s + "s";
}

// ── Fetch wrappers ────────────────────────────────────────────────

async function apiFetch(path, options) {
  var res = await fetch(path, options || {});
  if (!res.ok) throw new Error(res.status + " " + res.statusText);
  return res.json();
}

// ── Render: initial build ─────────────────────────────────────────

function buildTiles(services, categoryLabels) {
  _servicesCache = services;
  var grouped = {};
  for (var i = 0; i < services.length; i++) {
    var cat = services[i].category || "other";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(services[i]);
  }
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

function buildTile(svc) {
  var isSupport = svc.type === "support";
  var sc = statusClass(svc.status);
  var st = statusText(svc.status, svc.enabled);
  var dis = !svc.enabled;
  var hasCreds = svc.has_credentials && svc.enabled;

  var tile = document.createElement("div");
  tile.className = "service-tile" + (dis ? " disabled" : "") + (isSupport ? " support-tile" : "");
  tile.dataset.unit = svc.unit;
  tile.dataset.tileId = tileId(svc);
  if (dis) tile.title = svc.name + " is not enabled in custom.nix";

  if (isSupport) {
    tile.innerHTML = '<img class="tile-icon" src="/static/icons/' + escHtml(svc.icon) + '.svg" alt="' + escHtml(svc.name) + '" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"><div class="tile-icon-fallback" style="display:none">🛟</div><div class="tile-name">' + escHtml(svc.name) + '</div><div class="tile-status"><span class="support-status-label">Click to manage</span></div>';
    tile.style.cursor = "pointer";
    tile.addEventListener("click", function() { openSupportModal(); });
    return tile;
  }

  var infoBtn = hasCreds ? '<button class="tile-info-btn" data-unit="' + escHtml(svc.unit) + '" title="Connection info">i</button>' : "";
  tile.innerHTML = infoBtn + '<img class="tile-icon" src="/static/icons/' + escHtml(svc.icon) + '.svg" alt="' + escHtml(svc.name) + '" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"><div class="tile-icon-fallback" style="display:none">⚙</div><div class="tile-name">' + escHtml(svc.name) + '</div><div class="tile-status"><span class="status-dot ' + sc + '"></span><span class="status-text">' + escHtml(st) + '</span></div>';

  var infoBtnEl = tile.querySelector(".tile-info-btn");
  if (infoBtnEl) {
    infoBtnEl.addEventListener("click", function(e) {
      e.stopPropagation();
      openCredsModal(svc.unit, svc.name);
    });
  }
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
    var sc = statusClass(svc.status);
    var st = statusText(svc.status, svc.enabled);
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
    if ($updateBadge) $updateBadge.classList.toggle("visible", hasUpdates);
    if ($updateBtn) $updateBtn.classList.toggle("has-updates", hasUpdates);
  } catch (_) {}
}

// ── Credentials info modal ──────────��─────────────────────────────

async function openCredsModal(unit, name) {
  if (!$credsModal) return;
  if ($credsTitle) $credsTitle.textContent = name + " — Connection Info";
  if ($credsBody) $credsBody.innerHTML = '<p class="creds-loading">Loading…</p>';
  $credsModal.classList.add("open");
  try {
    var data = await apiFetch("/api/credentials/" + encodeURIComponent(unit));
    if (!data.credentials || data.credentials.length === 0) {
      $credsBody.innerHTML = '<p class="creds-empty">No connection info available yet.</p>';
      return;
    }
    var html = "";
    for (var i = 0; i < data.credentials.length; i++) {
      var cred = data.credentials[i];
      var id = "cred-" + Math.random().toString(36).substring(2, 8);
      var displayValue = linkify(cred.value);
      var qrBlock = "";
      if (cred.qrcode) {
        qrBlock = '<div class="creds-qr-wrap"><img class="creds-qr-img" src="' + cred.qrcode + '" alt="QR Code for ' + escHtml(cred.label) + '"><div class="creds-qr-hint">Scan with Zeus app on your phone</div></div>';
      }
      html += '<div class="creds-row"><div class="creds-label">' + escHtml(cred.label) + '</div>' + qrBlock + '<div class="creds-value-wrap"><div class="creds-value" id="' + id + '">' + displayValue + '</div><button class="creds-copy-btn" data-target="' + id + '">Copy</button></div></div>';
    }
    $credsBody.innerHTML = html;
    $credsBody.querySelectorAll(".creds-copy-btn").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var target = document.getElementById(btn.dataset.target);
        if (target) {
          navigator.clipboard.writeText(target.textContent).then(function() {
            btn.textContent = "Copied!";
            btn.classList.add("copied");
            setTimeout(function() { btn.textContent = "Copy"; btn.classList.remove("copied"); }, 1500);
          }).catch(function() {});
        }
      });
    });
  } catch (err) {
    $credsBody.innerHTML = '<p class="creds-empty">Could not load credentials.</p>';
  }
}

function closeCredsModal() { if ($credsModal) $credsModal.classList.remove("open"); }

// ── Tech Support modal ────────────────────────────────────────────

async function openSupportModal() {
  if (!$supportModal) return;
  $supportModal.classList.add("open");
  $supportBody.innerHTML = '<p class="creds-loading">Checking support status…</p>';
  try {
    var status = await apiFetch("/api/support/status");
    if (status.active) { _supportEnabledAt = status.enabled_at; renderSupportActive(); }
    else { renderSupportInactive(); }
  } catch (err) {
    $supportBody.innerHTML = '<p class="creds-empty">Could not check support status.</p>';
  }
}

function renderSupportInactive() {
  stopSupportTimer();
  var ip = _cachedExternalIp || "loading…";
  $supportBody.innerHTML = '<div class="support-section"><div class="support-icon-big">🛟</div><h3 class="support-heading">Need help from Sovran Systems?</h3><p class="support-desc">This will temporarily give Sovran Systems secure SSH access to your machine so we can diagnose and fix issues for you.</p><div class="support-info-box"><div class="support-info-row"><span class="support-info-label">Your External IP</span><span class="support-info-value" id="support-ext-ip">' + escHtml(ip) + '</span></div><p class="support-info-hint">Give this IP to your Sovran Systems technician when asked.</p></div><div class="support-steps"><p class="support-steps-title">What happens when you click Enable:</p><ol><li>A Sovran Systems SSH key is added to this machine</li><li>You give us your External IP shown above</li><li>We connect and help you remotely</li><li>When done, you click <strong>End Support Session</strong> to remove the key</li></ol></div><button class="btn support-btn-enable" id="btn-support-enable">Enable Support Access</button><p class="support-fine-print">You can end the session at any time. The access key will be completely removed.</p></div>';
  document.getElementById("btn-support-enable").addEventListener("click", enableSupport);
}

function renderSupportActive() {
  var ip = _cachedExternalIp || "loading…";
  $supportBody.innerHTML = '<div class="support-section"><div class="support-icon-big support-active-icon">🔓</div><h3 class="support-heading support-active-heading">Support Access is Active</h3><p class="support-desc">Sovran Systems can currently connect to your machine via SSH.</p><div class="support-info-box support-active-box"><div class="support-info-row"><span class="support-info-label">Your External IP</span><span class="support-info-value">' + escHtml(ip) + '</span></div><div class="support-info-row"><span class="support-info-label">Session Duration</span><span class="support-info-value" id="support-timer">—</span></div></div><p class="support-active-note">When your support session is complete, click the button below to <strong>immediately remove</strong> the access key.</p><button class="btn support-btn-disable" id="btn-support-disable">End Support Session</button></div>';
  document.getElementById("btn-support-disable").addEventListener("click", disableSupport);
  startSupportTimer();
}

function renderSupportRemoved(verified) {
  stopSupportTimer();
  var icon = verified ? "✅" : "⚠️";
  var msg = verified ? "The Sovran Systems SSH key has been completely removed from your machine. We no longer have any access." : "The key removal was requested but could not be fully verified. Please reboot your machine to be sure.";
  var vclass = verified ? "verified-gone" : "verify-warning";
  var vlabel = verified ? "✓ Removed — No access" : "⚠ Verify by rebooting";
  $supportBody.innerHTML = '<div class="support-section"><div class="support-icon-big">' + icon + '</div><h3 class="support-heading">Support Session Ended</h3><p class="support-desc">' + escHtml(msg) + '</p><div class="support-verify-box"><span class="support-verify-label">SSH Key Status:</span><span class="support-verify-value ' + vclass + '">' + vlabel + '</span></div><button class="btn support-btn-done" id="btn-support-done">Done</button></div>';
  document.getElementById("btn-support-done").addEventListener("click", closeSupportModal);
}

async function enableSupport() {
  var btn = document.getElementById("btn-support-enable");
  if (btn) { btn.disabled = true; btn.textContent = "Enabling…"; }
  try {
    await apiFetch("/api/support/enable", { method: "POST" });
    var status = await apiFetch("/api/support/status");