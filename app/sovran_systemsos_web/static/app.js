/* Sovran_SystemsOS Hub — Vanilla JS Frontend
   v7 — Status-only dashboard + Tech Support + Feature Manager */
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
  "feature-manager",
];

const FEATURE_SUBCATEGORY_LABELS = {
  "infrastructure": "🔧 Infrastructure",
  "bitcoin":        "₿ Bitcoin",
  "communication":  "💬 Communication",
  "nostr":          "📡 Nostr",
};

const FEATURE_SUBCATEGORY_ORDER = ["infrastructure", "bitcoin", "communication", "nostr"];

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

// Feature Manager state
let _featuresData       = null;
let _rebuildLog         = "";
let _rebuildLogOffset   = 0;
let _rebuildPollTimer   = null;
let _rebuildFinished    = false;
let _rebuildServerDown  = false;
let _pendingToggle      = null; // {feature, extra} waiting for domain/confirm

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

// Feature Manager — rebuild modal
const $rebuildModal    = document.getElementById("rebuild-modal");
const $rebuildSpinner  = document.getElementById("rebuild-spinner");
const $rebuildStatus   = document.getElementById("rebuild-status");
const $rebuildLog      = document.getElementById("rebuild-log");
const $rebuildReboot   = document.getElementById("rebuild-reboot-btn");
const $rebuildSave     = document.getElementById("rebuild-save-report");
const $rebuildClose    = document.getElementById("rebuild-close-btn");

// Feature Manager — domain setup modal
const $domainSetupModal = document.getElementById("domain-setup-modal");
const $domainSetupTitle = document.getElementById("domain-setup-title");
const $domainSetupBody  = document.getElementById("domain-setup-body");
const $domainSetupClose = document.getElementById("domain-setup-close-btn");

// Feature Manager — SSL email modal
const $sslEmailModal  = document.getElementById("ssl-email-modal");
const $sslEmailInput  = document.getElementById("ssl-email-input");
const $sslEmailSave   = document.getElementById("ssl-email-save-btn");
const $sslEmailCancel = document.getElementById("ssl-email-cancel-btn");
const $sslEmailClose  = document.getElementById("ssl-email-close-btn");

// Feature Manager — confirm modal
const $featureConfirmModal   = document.getElementById("feature-confirm-modal");
const $featureConfirmMsg     = document.getElementById("feature-confirm-message");
const $featureConfirmOk      = document.getElementById("feature-confirm-ok-btn");
const $featureConfirmCancel  = document.getElementById("feature-confirm-cancel-btn");
const $featureConfirmClose   = document.getElementById("feature-confirm-close-btn");

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

// ── Rebuild modal ─────────────────────────────────────────────────

function openRebuildModal() {
  if (!$rebuildModal) return;
  _rebuildLog = "";
  _rebuildLogOffset = 0;
  _rebuildServerDown = false;
  _rebuildFinished = false;
  if ($rebuildLog) $rebuildLog.textContent = "";
  if ($rebuildStatus) $rebuildStatus.textContent = "Rebuilding…";
  if ($rebuildSpinner) $rebuildSpinner.classList.add("spinning");
  if ($rebuildReboot) $rebuildReboot.style.display = "none";
  if ($rebuildSave) $rebuildSave.style.display = "none";
  if ($rebuildClose) $rebuildClose.disabled = true;
  $rebuildModal.classList.add("open");
  startRebuildPoll();
}

function closeRebuildModal() {
  if ($rebuildModal) $rebuildModal.classList.remove("open");
  stopRebuildPoll();
}

function appendRebuildLog(text) {
  if (!text) return;
  _rebuildLog += text;
  if ($rebuildLog) { $rebuildLog.textContent += text; $rebuildLog.scrollTop = $rebuildLog.scrollHeight; }
}

function startRebuildPoll() {
  pollRebuildStatus();
  _rebuildPollTimer = setInterval(pollRebuildStatus, UPDATE_POLL_INTERVAL);
}

function stopRebuildPoll() {
  if (_rebuildPollTimer) { clearInterval(_rebuildPollTimer); _rebuildPollTimer = null; }
}

async function pollRebuildStatus() {
  if (_rebuildFinished) return;
  try {
    var data = await apiFetch("/api/rebuild/status?offset=" + _rebuildLogOffset);
    if (_rebuildServerDown) { _rebuildServerDown = false; appendRebuildLog("[Server reconnected]\n"); if ($rebuildStatus) $rebuildStatus.textContent = "Rebuilding…"; }
    if (data.log) appendRebuildLog(data.log);
    _rebuildLogOffset = data.offset;
    if (data.running) return;
    _rebuildFinished = true;
    stopRebuildPoll();
    onRebuildDone(data.result === "success");
  } catch (err) {
    if (!_rebuildServerDown) { _rebuildServerDown = true; appendRebuildLog("\n[Server restarting — waiting for it to come back…]\n"); if ($rebuildStatus) $rebuildStatus.textContent = "Server restarting…"; }
  }
}

function onRebuildDone(success) {
  if ($rebuildSpinner) $rebuildSpinner.classList.remove("spinning");
  if ($rebuildClose) $rebuildClose.disabled = false;
  if (success) {
    if ($rebuildStatus) $rebuildStatus.textContent = "✓ Rebuild complete";
    if ($rebuildReboot) $rebuildReboot.style.display = "inline-flex";
    // Refresh feature states
    loadFeatureManager();
  } else {
    if ($rebuildStatus) $rebuildStatus.textContent = "✗ Rebuild failed";
    if ($rebuildSave) $rebuildSave.style.display = "inline-flex";
    if ($rebuildReboot) $rebuildReboot.style.display = "inline-flex";
  }
}

function saveRebuildErrorReport() {
  var blob = new Blob([_rebuildLog], { type: "text/plain" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = "sovran-rebuild-error-" + new Date().toISOString().split(".")[0].replace(/:/g, "-") + ".txt";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Feature confirm modal ─────────────────────────────────────────

function openFeatureConfirm(message, onConfirm) {
  if (!$featureConfirmModal) return;
  if ($featureConfirmMsg) $featureConfirmMsg.textContent = message;
  $featureConfirmModal.classList.add("open");
  // Replace ok handler
  var newOk = $featureConfirmOk.cloneNode(true);
  $featureConfirmOk.parentNode.replaceChild(newOk, $featureConfirmOk);
  newOk.addEventListener("click", function() {
    closeFeatureConfirm();
    onConfirm();
  });
}

function closeFeatureConfirm() {
  if ($featureConfirmModal) $featureConfirmModal.classList.remove("open");
}

// ── SSL Email modal ───────────────────────────────────────────────

function openSslEmailModal(onSaved) {
  if (!$sslEmailModal) return;
  if ($sslEmailInput) $sslEmailInput.value = "";
  $sslEmailModal.classList.add("open");
  // Replace save handler
  var newSave = $sslEmailSave.cloneNode(true);
  $sslEmailSave.parentNode.replaceChild(newSave, $sslEmailSave);
  newSave.addEventListener("click", async function() {
    var email = $sslEmailInput ? $sslEmailInput.value.trim() : "";
    if (!email) { alert("Please enter an email address."); return; }
    newSave.disabled = true;
    newSave.textContent = "Saving…";
    try {
      await apiFetch("/api/domains/set-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email }),
      });
      closeSslEmailModal();
      onSaved();
    } catch (err) {
      newSave.disabled = false;
      newSave.textContent = "Save";
      alert("Failed to save email. Please try again.");
    }
  });
}

function closeSslEmailModal() {
  if ($sslEmailModal) $sslEmailModal.classList.remove("open");
}

// ── Domain Setup modal ────────────────────────────────────────────

function openDomainSetupModal(feat, onSaved) {
  if (!$domainSetupModal) return;
  if ($domainSetupTitle) $domainSetupTitle.textContent = "🌐 Domain Setup — " + feat.name;

  var npubField = "";
  if (feat.id === "haven") {
    var currentNpub = "";
    if (feat.extra_fields && feat.extra_fields.length > 0) {
      for (var i = 0; i < feat.extra_fields.length; i++) {
        if (feat.extra_fields[i].id === "nostr_npub") {
          currentNpub = feat.extra_fields[i].current_value || "";
          break;
        }
      }
    }
    npubField = '<div class="domain-field-group"><label class="domain-field-label" for="domain-npub-input">Nostr Public Key (npub1...):</label><input class="domain-field-input" type="text" id="domain-npub-input" placeholder="npub1…" value="' + escHtml(currentNpub) + '" /></div>';
  }

  $domainSetupBody.innerHTML =
    '<div class="domain-setup-intro"><p>Before continuing, you need:</p><ol><li>A subdomain purchased on njal.la</li><li>A Dynamic DNS record for it</li></ol></div>' +
    '<div class="domain-field-group"><label class="domain-field-label" for="domain-subdomain-input">Subdomain:</label><input class="domain-field-input" type="text" id="domain-subdomain-input" placeholder="relay.mydomain.com" /></div>' +
    '<div class="domain-field-group"><label class="domain-field-label" for="domain-ddns-input">Njal.la DDNS URL:</label><input class="domain-field-input" type="text" id="domain-ddns-input" placeholder="https://njal.la/update/?h=..." /><p class="domain-field-hint">ℹ Paste the curl URL from your Njal.la dashboard\'s Dynamic record</p></div>' +
    npubField +
    '<div class="domain-field-actions"><button class="btn btn-close-modal" id="domain-setup-cancel-btn">Cancel</button><button class="btn btn-primary" id="domain-setup-save-btn">Save &amp; Enable</button></div>';

  document.getElementById("domain-setup-cancel-btn").addEventListener("click", closeDomainSetupModal);

  document.getElementById("domain-setup-save-btn").addEventListener("click", async function() {
    var subdomain = (document.getElementById("domain-subdomain-input") || {}).value || "";
    var ddnsUrl   = (document.getElementById("domain-ddns-input")     || {}).value || "";
    var npub      = document.getElementById("domain-npub-input") ? (document.getElementById("domain-npub-input").value || "") : "";
    subdomain = subdomain.trim();
    ddnsUrl   = ddnsUrl.trim();
    npub      = npub.trim();

    if (!subdomain) { alert("Please enter a subdomain."); return; }
    if (feat.id === "haven" && !npub) { alert("Please enter your Nostr public key."); return; }

    var saveBtn = document.getElementById("domain-setup-save-btn");
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving…";

    try {
      await apiFetch("/api/domains/set", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain_name: feat.domain_name,
          domain: subdomain,
          ddns_url: ddnsUrl,
        }),
      });
      closeDomainSetupModal();
      onSaved(npub);
    } catch (err) {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save & Enable";
      alert("Failed to save domain. Please try again.");
    }
  });

  $domainSetupModal.classList.add("open");
}

function closeDomainSetupModal() {
  if ($domainSetupModal) $domainSetupModal.classList.remove("open");
}

// ── Feature toggle logic ──────────────────────────────────────────

async function performFeatureToggle(featId, enabled, extra) {
  try {
    var res = await fetch("/api/features/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature: featId, enabled: enabled, extra: extra || {} }),
    });
    var body = await res.json();
    if (!res.ok) {
      if (body && body.error === "domain_required") {
        alert("Domain not configured for this feature. Please configure it first.");
      } else {
        alert("Error: " + (body.detail || body.error || "Unknown error"));
      }
      loadFeatureManager();
      return;
    }
    openRebuildModal();
  } catch (err) {
    alert("Failed to toggle feature: " + err);
    loadFeatureManager();
  }
}

function handleFeatureToggle(feat, newEnabled) {
  if (!newEnabled) {
    // Disable: ask confirmation
    openFeatureConfirm(
      "This will disable " + feat.name + ". The system will rebuild. Continue?",
      function() { performFeatureToggle(feat.id, false, {}); }
    );
    return;
  }

  // Enabling
  var conflictNames = [];
  if (feat.conflicts_with && feat.conflicts_with.length > 0 && _featuresData) {
    feat.conflicts_with.forEach(function(cid) {
      var cf = _featuresData.features.find(function(f) { return f.id === cid; });
      if (cf && cf.enabled) conflictNames.push(cf.name);
    });
  }

  function proceedAfterConflictCheck() {
    // Check SSL email first
    if (!_featuresData || !_featuresData.ssl_email_configured) {
      if (feat.needs_domain) {
        openSslEmailModal(function() {
          // After ssl email saved, check domain
          checkDomainAndEnable(feat, {});
        });
        return;
      }
    }
    if (feat.needs_domain && !feat.domain_configured) {
      checkDomainAndEnable(feat, {});
      return;
    }
    if (feat.id === "haven") {
      var npub = "";
      if (feat.extra_fields) {
        var ef = feat.extra_fields.find(function(e) { return e.id === "nostr_npub"; });
        if (ef) npub = ef.current_value || "";
      }
      if (!npub) {
        // Need to collect npub via domain modal
        openDomainSetupModal(feat, function(collectedNpub) {
          performFeatureToggle(feat.id, true, { nostr_npub: collectedNpub });
        });
        return;
      }
    }
    performFeatureToggle(feat.id, true, {});
  }

  if (conflictNames.length > 0) {
    openFeatureConfirm(
      "This will disable " + conflictNames.join(", ") + ". Continue?",
      proceedAfterConflictCheck
    );
  } else {
    proceedAfterConflictCheck();
  }
}

function checkDomainAndEnable(feat, extra) {
  openDomainSetupModal(feat, function(collectedNpub) {
    var extraData = {};
    if (collectedNpub) extraData.nostr_npub = collectedNpub;
    performFeatureToggle(feat.id, true, extraData);
  });
}

// ── Feature Manager rendering ─────────────────────────────────────

async function loadFeatureManager() {
  try {
    var data = await apiFetch("/api/features");
    _featuresData = data;
    renderFeatureManager(data);
  } catch (err) {
    console.warn("Failed to load features:", err);
  }
}

function renderFeatureManager(data) {
  // Remove old feature manager section if it exists
  var old = $tilesArea.querySelector(".feature-manager-section");
  if (old) old.parentNode.removeChild(old);

  var section = document.createElement("div");
  section.className = "category-section feature-manager-section";
  section.dataset.category = "feature-manager";
  section.innerHTML = '<div class="section-header">Feature Manager</div><hr class="section-divider" />';

  // Group by sub-category
  var grouped = {};
  for (var i = 0; i < data.features.length; i++) {
    var f = data.features[i];
    var cat = f.category || "other";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(f);
  }

  var orderedCats = FEATURE_SUBCATEGORY_ORDER.filter(function(k) { return grouped[k]; });
  Object.keys(grouped).forEach(function(k) {
    if (orderedCats.indexOf(k) === -1) orderedCats.push(k);
  });

  for (var j = 0; j < orderedCats.length; j++) {
    var catKey = orderedCats[j];
    var feats = grouped[catKey];
    if (!feats || feats.length === 0) continue;

    var subcat = document.createElement("div");
    subcat.className = "feature-subcategory";
    var subcatLabel = FEATURE_SUBCATEGORY_LABELS[catKey] || catKey;
    subcat.innerHTML = '<div class="feature-subcategory-header">' + escHtml(subcatLabel) + '</div>';

    var cardsWrap = document.createElement("div");
    cardsWrap.className = "feature-cards-wrap";

    for (var k = 0; k < feats.length; k++) {
      cardsWrap.appendChild(buildFeatureCard(feats[k]));
    }
    subcat.appendChild(cardsWrap);
    section.appendChild(subcat);
  }

  $tilesArea.appendChild(section);
}

function buildFeatureCard(feat) {
  var card = document.createElement("div");
  card.className = "feature-card";

  var conflictHtml = "";
  if (feat.conflicts_with && feat.conflicts_with.length > 0) {
    var conflictNames = feat.conflicts_with.map(function(cid) {
      if (!_featuresData) return cid;
      var cf = _featuresData.features.find(function(f) { return f.id === cid; });
      return cf ? cf.name : cid;
    });
    conflictHtml = '<div class="feature-conflict-warning">⚠ Conflicts with: ' + escHtml(conflictNames.join(", ")) + '</div>';
  }

  var domainHtml = "";
  if (feat.needs_domain) {
    if (feat.domain_configured) {
      domainHtml = '<div class="feature-domain-badge configured">🌐 Domain: Configured</div>';
    } else {
      domainHtml = '<div class="feature-domain-badge not-configured">🌐 Domain: Not configured</div>';
    }
  }

  var statusText = feat.enabled ? "Enabled" : "Disabled";

  card.innerHTML =
    '<div class="feature-card-top">' +
    '<div class="feature-card-info">' +
    '<div class="feature-card-name">' + escHtml(feat.name) + '</div>' +
    '<div class="feature-card-desc">' + escHtml(feat.description) + '</div>' +
    '</div>' +
    '<label class="feature-toggle' + (feat.enabled ? " active" : "") + '" title="Toggle ' + escHtml(feat.name) + '">' +
    '<input type="checkbox" class="feature-toggle-input"' + (feat.enabled ? " checked" : "") + ' />' +
    '<span class="feature-toggle-slider"></span>' +
    '</label>' +
    '</div>' +
    domainHtml +
    conflictHtml +
    '<div class="feature-card-status">Status: ' + escHtml(statusText) + '</div>';

  var toggle = card.querySelector(".feature-toggle-input");
  var toggleLabel = card.querySelector(".feature-toggle");
  toggle.addEventListener("change", function() {
    var newEnabled = toggle.checked;
    // Revert visually until confirmed
    toggle.checked = feat.enabled;
    if (newEnabled) { toggleLabel.classList.remove("active"); } else { toggleLabel.classList.add("active"); }
    handleFeatureToggle(feat, newEnabled);
  });

  return card;
}

// ── Event listeners ───────────────────────────────────────────────

if ($updateBtn) $updateBtn.addEventListener("click", openUpdateModal);
if ($refreshBtn) $refreshBtn.addEventListener("click", function() { refreshServices(); });
if ($btnCloseModal) $btnCloseModal.addEventListener("click", closeUpdateModal);
if ($btnReboot) $btnReboot.addEventListener("click", doReboot);
if ($btnSave) $btnSave.addEventListener("click", saveErrorReport);
if ($credsCloseBtn) $credsCloseBtn.addEventListener("click", closeCredsModal);
if ($supportCloseBtn) $supportCloseBtn.addEventListener("click", closeSupportModal);

// Rebuild modal
if ($rebuildClose) $rebuildClose.addEventListener("click", closeRebuildModal);
if ($rebuildReboot) $rebuildReboot.addEventListener("click", doReboot);
if ($rebuildSave) $rebuildSave.addEventListener("click", saveRebuildErrorReport);
if ($rebuildModal) $rebuildModal.addEventListener("click", function(e) { if (e.target === $rebuildModal) closeRebuildModal(); });

// Domain setup modal
if ($domainSetupClose) $domainSetupClose.addEventListener("click", closeDomainSetupModal);
if ($domainSetupModal) $domainSetupModal.addEventListener("click", function(e) { if (e.target === $domainSetupModal) closeDomainSetupModal(); });

// SSL Email modal
if ($sslEmailClose) $sslEmailClose.addEventListener("click", closeSslEmailModal);
if ($sslEmailCancel) $sslEmailCancel.addEventListener("click", closeSslEmailModal);
if ($sslEmailModal) $sslEmailModal.addEventListener("click", function(e) { if (e.target === $sslEmailModal) closeSslEmailModal(); });

// Feature confirm modal
if ($featureConfirmClose) $featureConfirmClose.addEventListener("click", closeFeatureConfirm);
if ($featureConfirmCancel) $featureConfirmCancel.addEventListener("click", closeFeatureConfirm);
if ($featureConfirmModal) $featureConfirmModal.addEventListener("click", function(e) { if (e.target === $featureConfirmModal) closeFeatureConfirm(); });

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

    await refreshServices();
    loadNetwork();
    checkUpdates();

    setInterval(refreshServices, POLL_INTERVAL_SERVICES);
    setInterval(checkUpdates, POLL_INTERVAL_UPDATES);

    if (cfg.feature_manager) {
      loadFeatureManager();
    }
  } catch (_) {
    await refreshServices();
    loadNetwork();
    checkUpdates();
    setInterval(refreshServices, POLL_INTERVAL_SERVICES);
    setInterval(checkUpdates, POLL_INTERVAL_UPDATES);
  }
}

document.addEventListener("DOMContentLoaded", init);
