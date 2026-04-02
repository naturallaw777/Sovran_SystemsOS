/* Sovran_SystemsOS Hub — Vanilla JS Frontend
   v7 — Status-only dashboard + Tech Support */
"use strict";

const POLL_INTERVAL_SERVICES = 5000;
const POLL_INTERVAL_UPDATES  = 1800000;
const UPDATE_POLL_INTERVAL   = 2000;
const REBOOT_CHECK_INTERVAL  = 5000;
const SUPPORT_TIMER_INTERVAL = 1000;

const CATEGORY_ORDER = [
  "infrastructure",
  "bitcoin-base",
  "bitcoin-apps",
  "communication",
  "apps",
  "nostr",
  "support",
];

const STATUS_LOADING_STATES = new Set([
  "reloading", "activating", "deactivating", "maintenance",
]);

// ── State ─────────────────────────────────────────────────────────

let _servicesCache    = [];
let _categoryLabels   = {};
let _updateLog        = "";
let _updatePollTimer  = null;
let _updateLogOffset  = 0;
let _serverWasDown    = false;
let _updateFinished   = false;
let _supportTimerInt  = null;
let _supportEnabledAt = null;
let _cachedExternalIp = null;

// ── DOM refs ──────────────────────────────────────────────────────

const $tilesArea      = document.getElementById("tiles-area");
const $updateBtn      = document.getElementById("btn-update");
const $updateBadge    = document.getElementById("update-badge");
const $refreshBtn     = document.getElementById("btn-refresh");
const $internalIp     = document.getElementById("ip-internal");
const $externalIp     = document.getElementById("ip-external");

const $modal          = document.getElementById("update-modal");
const $modalSpinner   = document.getElementById("modal-spinner");
const $modalStatus    = document.getElementById("modal-status");
const $modalLog       = document.getElementById("modal-log");
const $btnReboot      = document.getElementById("btn-reboot");
const $btnSave        = document.getElementById("btn-save-report");
const $btnCloseModal  = document.getElementById("btn-close-modal");

const $rebootOverlay  = document.getElementById("reboot-overlay");

const $credsModal     = document.getElementById("creds-modal");
const $credsTitle     = document.getElementById("creds-modal-title");
const $credsBody      = document.getElementById("creds-body");
const $credsCloseBtn  = document.getElementById("creds-close-btn");

const $supportModal     = document.getElementById("support-modal");
const $supportBody      = document.getElementById("support-body");
const $supportCloseBtn  = document.getElementById("support-close-btn");

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
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return h + "h " + m + "m " + s + "s";
  if (m > 0) return m + "m " + s + "s";
  return s + "s";
}

// ── Fetch wrappers ────────────────────────────────────────────────

async function apiFetch(path, options) {
  const res = await fetch(path, options || {});
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

// ── Credentials info modal ────────────────────────────────────────

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
    _supportEnabledAt = status.enabled_at;
    renderSupportActive();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = "Enable Support Access"; }
    alert("Failed to enable support access. Please try again.");
  }
}

async function disableSupport() {
  var btn = document.getElementById("btn-support-disable");
  if (btn) { btn.disabled = true; btn.textContent = "Removing key…"; }
  try {
    var result = await apiFetch("/api/support/disable", { method: "POST" });
    renderSupportRemoved(result.verified);
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = "End Support Session"; }
    alert("Failed to disable support access. Please try again.");
  }
}

function startSupportTimer() {
  stopSupportTimer();
  updateSupportTimer();
  _supportTimerInt = setInterval(updateSupportTimer, SUPPORT_TIMER_INTERVAL);
}

function stopSupportTimer() {
  if (_supportTimerInt) { clearInterval(_supportTimerInt); _supportTimerInt = null; }
}

function updateSupportTimer() {
  var el = document.getElementById("support-timer");
  if (!el || !_supportEnabledAt) return;
  var elapsed = (Date.now() / 1000) - _supportEnabledAt;
  el.textContent = formatDuration(Math.max(0, elapsed));
}

function closeSupportModal() {
  if ($supportModal) $supportModal.classList.remove("open");
  stopSupportTimer();
}

// ── Update modal ──────────────────────────────────────────────────

function openUpdateModal() {
  if (!$modal) return;
  _updateLog = "";
  _updateLogOffset = 0;
  _serverWasDown = false;
  _updateFinished = false;
  if ($modalLog) $modalLog.textContent = "";
  if ($modalStatus) $modalStatus.textContent = "Starting update…";
  if ($modalSpinner) $modalSpinner.classList.add("spinning");
  if ($btnReboot) $btnReboot.style.display = "none";
  if ($btnSave) $btnSave.style.display = "none";
  if ($btnCloseModal) $btnCloseModal.disabled = true;
  $modal.classList.add("open");
  startUpdate();
}

function closeUpdateModal() {
  if (!$modal) return;
  $modal.classList.remove("open");
  stopUpdatePoll();
}

function appendLog(text) {
  if (!text) return;
  _updateLog += text;
  if ($modalLog) { $modalLog.textContent += text; $modalLog.scrollTop = $modalLog.scrollHeight; }
}

function startUpdate() {
  fetch("/api/updates/run", { method: "POST" })
    .then(function(response) {
      if (!response.ok) return response.text().then(function(t) { throw new Error(t); });
      return response.json();
    })
    .then(function(data) {
      if (data.status === "already_running") appendLog("[Update already in progress, attaching…]\n\n");
      if ($modalStatus) $modalStatus.textContent = "Updating…";
      startUpdatePoll();
    })
    .catch(function(err) {
      appendLog("[Error: failed to start update — " + err + "]\n");
      onUpdateDone(false);
    });
}

function startUpdatePoll() {
  pollUpdateStatus();
  _updatePollTimer = setInterval(pollUpdateStatus, UPDATE_POLL_INTERVAL);
}

function stopUpdatePoll() {
  if (_updatePollTimer) { clearInterval(_updatePollTimer); _updatePollTimer = null; }
}

async function pollUpdateStatus() {
  if (_updateFinished) return;
  try {
    var data = await apiFetch("/api/updates/status?offset=" + _updateLogOffset);
    if (_serverWasDown) { _serverWasDown = false; appendLog("[Server reconnected]\n"); if ($modalStatus) $modalStatus.textContent = "Updating…"; }
    if (data.log) appendLog(data.log);
    _updateLogOffset = data.offset;
    if (data.running) return;
    _updateFinished = true;
    stopUpdatePoll();
    if (data.result === "success") onUpdateDone(true);
    else onUpdateDone(false);
  } catch (err) {
    if (!_serverWasDown) { _serverWasDown = true; appendLog("\n[Server restarting — waiting for it to come back…]\n"); if ($modalStatus) $modalStatus.textContent = "Server restarting…"; }
  }
}

function onUpdateDone(success) {
  if ($modalSpinner) $modalSpinner.classList.remove("spinning");
  if ($btnCloseModal) $btnCloseModal.disabled = false;
  if (success) {
    if ($modalStatus) $modalStatus.textContent = "✓ Update complete";
    if ($btnReboot) $btnReboot.style.display = "inline-flex";
  } else {
    if ($modalStatus) $modalStatus.textContent = "✗ Update failed";
    if ($btnSave) $btnSave.style.display = "inline-flex";
    if ($btnReboot) $btnReboot.style.display = "inline-flex";
  }
}

function saveErrorReport() {
  var blob = new Blob([_updateLog], { type: "text/plain" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = "sovran-update-error-" + new Date().toISOString().split(".")[0].replace(/:/g, "-") + ".txt";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Reboot ────────────────────────────────────────────────────────

function doReboot() {
  if ($modal) $modal.classList.remove("open");
  stopUpdatePoll();
  if ($rebootOverlay) $rebootOverlay.classList.add("visible");
  fetch("/api/reboot", { method: "POST" }).catch(function() {});
  setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
}

function waitForServerReboot() {
  fetch("/api/config", { cache: "no-store" })
    .then(function(res) {
      if (res.ok) window.location.reload();
      else setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
    })
    .catch(function() { setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL); });
}

// ── Event listeners ───────────────────────────────────────────────

if ($updateBtn) $updateBtn.addEventListener("click", openUpdateModal);
if ($refreshBtn) $refreshBtn.addEventListener("click", function() { refreshServices(); });
if ($btnCloseModal) $btnCloseModal.addEventListener("click", closeUpdateModal);
if ($btnReboot) $btnReboot.addEventListener("click", doReboot);
if ($btnSave) $btnSave.addEventListener("click", saveErrorReport);
if ($credsCloseBtn) $credsCloseBtn.addEventListener("click", closeCredsModal);
if ($supportCloseBtn) $supportCloseBtn.addEventListener("click", closeSupportModal);

if ($modal) $modal.addEventListener("click", function(e) { if (e.target === $modal) closeUpdateModal(); });
if ($credsModal) $credsModal.addEventListener("click", function(e) { if (e.target === $credsModal) closeCredsModal(); });
if ($supportModal) $supportModal.addEventListener("click", function(e) { if (e.target === $supportModal) closeSupportModal(); });

// ── Init ──────────────────────────────────────────────────────────

async function init() {
  try {
    var cfg = await apiFetch("/api/config");
    if (cfg.category_order) {
      for (var i = 0; i < cfg.category_order.length; i++) {
        _categoryLabels[cfg.category_order[i][0]] = cfg.category_order[i][1];
      }
    }
    var badge = document.getElementById("role-badge");
    if (badge && cfg.role_label) badge.textContent = cfg.role_label;
  } catch (_) {}

  await refreshServices();
  loadNetwork();
  checkUpdates();

  setInterval(refreshServices, POLL_INTERVAL_SERVICES);
  setInterval(checkUpdates, POLL_INTERVAL_UPDATES);
}

document.addEventListener("DOMContentLoaded", init);