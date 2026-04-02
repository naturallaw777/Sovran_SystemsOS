/* Sovran_SystemsOS Hub — Vanilla JS Frontend */
"use strict";

const POLL_INTERVAL_SERVICES = 5000;   // 5 s
const POLL_INTERVAL_UPDATES  = 1800000; // 30 min
const ACTION_REFRESH_DELAY   = 1500;   // 1.5 s after start/stop/restart
const UPDATE_POLL_INTERVAL   = 2000;   // 2 s while update is running

const CATEGORY_ORDER = [
  "infrastructure",
  "bitcoin-base",
  "bitcoin-apps",
  "communication",
  "apps",
  "nostr",
];

const STATUS_LOADING_STATES = new Set([
  "reloading", "activating", "deactivating", "maintenance",
]);

// ── State ─────────────────────────────────────────────────────────

let _servicesCache  = [];
let _categoryLabels = {};
let _updateSource   = null;
let _updateLog      = "";
let _updatePollTimer = null;
let _updateCursor    = "";
let _serverDownSince = 0;

// ── DOM refs ──────────────────────────────────────────────────────

const $tilesArea    = document.getElementById("tiles-area");
const $updateBtn    = document.getElementById("btn-update");
const $updateBadge  = document.getElementById("update-badge");
const $refreshBtn   = document.getElementById("btn-refresh");
const $internalIp   = document.getElementById("ip-internal");
const $externalIp   = document.getElementById("ip-external");

const $modal        = document.getElementById("update-modal");
const $modalSpinner = document.getElementById("modal-spinner");
const $modalStatus  = document.getElementById("modal-status");
const $modalLog     = document.getElementById("modal-log");
const $btnReboot    = document.getElementById("btn-reboot");
const $btnSave      = document.getElementById("btn-save-report");
const $btnCloseModal = document.getElementById("btn-close-modal");

// ── Helpers ───────────────────────────────────────────────────────

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

// ── Fetch wrappers ────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// ── Render: initial build ─────────────────────────────────────────

function buildTiles(services, categoryLabels) {
  _servicesCache = services;

  // Group by category
  const grouped = {};
  for (const svc of services) {
    const cat = svc.category || "other";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(svc);
  }

  $tilesArea.innerHTML = "";

  const orderedKeys = [
    ...CATEGORY_ORDER.filter(k => grouped[k]),
    ...Object.keys(grouped).filter(k => !CATEGORY_ORDER.includes(k)),
  ];

  for (const catKey of orderedKeys) {
    const entries = grouped[catKey];
    if (!entries || entries.length === 0) continue;

    const label = categoryLabels[catKey] || catKey;

    const section = document.createElement("div");
    section.className = "category-section";
    section.dataset.category = catKey;

    section.innerHTML = `
      <div class="section-header">${escHtml(label)}</div>
      <hr class="section-divider" />
      <div class="tiles-grid" data-cat="${escHtml(catKey)}"></div>
    `;

    const grid = section.querySelector(".tiles-grid");
    for (const svc of entries) {
      grid.appendChild(buildTile(svc));
    }

    $tilesArea.appendChild(section);
  }

  if ($tilesArea.children.length === 0) {
    $tilesArea.innerHTML = `<div class="empty-state"><p>No services configured.</p></div>`;
  }
}

function buildTile(svc) {
  const sc   = statusClass(svc.status);
  const st   = statusText(svc.status, svc.enabled);
  const dis  = !svc.enabled;
  const isOn = svc.status === "active";

  const tile = document.createElement("div");
  tile.className = "service-tile" + (dis ? " disabled" : "");
  tile.dataset.unit = svc.unit;
  if (dis) tile.title = `${svc.name} is not enabled in custom.nix`;

  tile.innerHTML = `
    <img class="tile-icon"
         src="/static/icons/${escHtml(svc.icon)}.svg"
         alt="${escHtml(svc.name)}"
         onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
    <div class="tile-icon-fallback" style="display:none">⚙</div>
    <div class="tile-name">${escHtml(svc.name)}</div>
    <div class="tile-status">
      <span class="status-dot ${sc}"></span>
      <span class="status-text">${escHtml(st)}</span>
    </div>
    <div class="tile-spacer"></div>
    <div class="tile-controls">
      <label class="toggle-label${dis ? " disabled-toggle" : ""}" title="${dis ? "Not enabled in custom.nix" : (isOn ? "Stop" : "Start")}">
        <input type="checkbox" class="tile-toggle" data-unit="${escHtml(svc.unit)}"
               ${isOn ? "checked" : ""} ${dis ? "disabled" : ""}>
        <span class="toggle-track"><span class="toggle-thumb"></span></span>
      </label>
      <button class="tile-restart-btn" data-unit="${escHtml(svc.unit)}"
              title="Restart" ${dis ? "disabled" : ""}>↺</button>
    </div>
  `;

  // Toggle handler
  const chk = tile.querySelector(".tile-toggle");
  if (!dis) {
    chk.addEventListener("change", async (e) => {
      const action = e.target.checked ? "start" : "stop";
      chk.disabled = true;
      try {
        await apiFetch(`/api/services/${encodeURIComponent(svc.unit)}/${action}`, { method: "POST" });
      } catch (_) {}
      setTimeout(() => refreshServices(), ACTION_REFRESH_DELAY);
    });
  }

  // Restart handler
  const restartBtn = tile.querySelector(".tile-restart-btn");
  if (!dis) {
    restartBtn.addEventListener("click", async () => {
      restartBtn.disabled = true;
      try {
        await apiFetch(`/api/services/${encodeURIComponent(svc.unit)}/restart`, { method: "POST" });
      } catch (_) {}
      setTimeout(() => refreshServices(), ACTION_REFRESH_DELAY);
    });
  }

  return tile;
}

// ── Render: live update (no DOM rebuild) ──────────────────────────

function updateTiles(services) {
  _servicesCache = services;

  for (const svc of services) {
    const tile = $tilesArea.querySelector(`.service-tile[data-unit="${CSS.escape(svc.unit)}"]`);
    if (!tile) continue;

    const sc = statusClass(svc.status);
    const st = statusText(svc.status, svc.enabled);

    const dot  = tile.querySelector(".status-dot");
    const text = tile.querySelector(".status-text");
    const chk  = tile.querySelector(".tile-toggle");

    if (dot)  { dot.className  = `status-dot ${sc}`; }
    if (text) { text.textContent = st; }
    if (chk && !chk.disabled) {
      chk.checked = svc.status === "active";
    }
  }
}

// ── HTML escape ───────────────────────────────────────────────────

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── Service polling ───────────────────────────────────────────────

let _firstLoad = true;

async function refreshServices() {
  try {
    const services = await apiFetch("/api/services");
    if (_firstLoad) {
      buildTiles(services, _categoryLabels);
      _firstLoad = false;
    } else {
      updateTiles(services);
    }
  } catch (err) {
    console.warn("Failed to fetch services:", err);
  }
}

// ── Network IPs ───────────────────────────────────────────────────

async function loadNetwork() {
  try {
    const data = await apiFetch("/api/network");
    if ($internalIp) $internalIp.textContent = data.internal_ip || "—";
    if ($externalIp) $externalIp.textContent = data.external_ip || "—";
  } catch (_) {
    if ($internalIp) $internalIp.textContent = "—";
    if ($externalIp) $externalIp.textContent = "—";
  }
}

// ── Update check ──────────────────────────────────────────────────

async function checkUpdates() {
  try {
    const data = await apiFetch("/api/updates/check");
    if ($updateBadge) {
      $updateBadge.classList.toggle("visible", !!data.available);
    }
  } catch (_) {}
}

// ── Update modal ──────────────────────────────────────────────────

function openUpdateModal() {
  if (!$modal) return;
  _updateLog = "";
  _updateCursor = "";
  _serverDownSince = 0;
  if ($modalLog)    $modalLog.textContent = "";
  if ($modalStatus) $modalStatus.textContent = "Updating…";
  if ($modalSpinner) $modalSpinner.classList.add("spinning");
  if ($btnReboot)   { $btnReboot.style.display   = "none"; }
  if ($btnSave)     { $btnSave.style.display      = "none"; }
  if ($btnCloseModal) { $btnCloseModal.disabled   = true;   }

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
  _updateLog += text + "\n";
  if ($modalLog) {
    $modalLog.textContent += text + "\n";
    $modalLog.scrollTop = $modalLog.scrollHeight;
  }
}

function startUpdate() {
  appendLog("$ cd /etc/nixos && nix flake update && nixos-rebuild switch && flatpak update -y");
  appendLog("");

  // Trigger the systemd unit via POST
  fetch("/api/updates/run", { method: "POST" })
    .then(response => {
      if (!response.ok) {
        return response.text().then(t => { throw new Error(t); });
      }
      return response.json();
    })
    .then(data => {
      if (data.status === "already_running") {
        appendLog("[Update already in progress, attaching…]");
      }
      // Start polling for journal output
      startUpdatePoll();
    })
    .catch(err => {
      appendLog(`[Error: failed to start update — ${err}]`);
      onUpdateDone(false);
    });
}

function startUpdatePoll() {
  // Poll immediately, then on interval
  pollUpdateStatus();
  _updatePollTimer = setInterval(pollUpdateStatus, UPDATE_POLL_INTERVAL);
}

function stopUpdatePoll() {
  if (_updatePollTimer) {
    clearInterval(_updatePollTimer);
    _updatePollTimer = null;
  }
}

async function pollUpdateStatus() {
  try {
    const data = await apiFetch(
      `/api/updates/status?cursor=${encodeURIComponent(_updateCursor)}`
    );

    // Server is back — reset the down counter
    if (_serverDownSince > 0) {
      appendLog("[Server reconnected, resuming…]");
      _serverDownSince = 0;
    }

    // Append new journal lines
    if (data.lines && data.lines.length > 0) {
      for (const line of data.lines) {
        appendLog(line);
      }
    }
    if (data.cursor) {
      _updateCursor = data.cursor;
    }

    // Update status text while running
    if (data.running) {
      if ($modalStatus) $modalStatus.textContent = "Updating…";
    } else {
      // Finished
      stopUpdatePoll();
      if (data.result === "success") {
        onUpdateDone(true);
      } else {
        onUpdateDone(false);
      }
    }
  } catch (err) {
    // Server is likely restarting during nixos-rebuild switch
    if (_serverDownSince === 0) {
      _serverDownSince = Date.now();
      appendLog("[Server restarting — waiting for it to come back…]");
      if ($modalStatus) $modalStatus.textContent = "Server restarting…";
    }
    console.warn("Update poll failed (server may be restarting):", err);
  }
}

function onUpdateDone(success) {
  if ($modalSpinner)  $modalSpinner.classList.remove("spinning");
  if ($btnCloseModal) $btnCloseModal.disabled = false;

  if (success) {
    if ($modalStatus) $modalStatus.textContent = "✓ Update complete";
    if ($btnReboot)   $btnReboot.style.display  = "inline-flex";
  } else {
    if ($modalStatus) $modalStatus.textContent = "✗ Update failed";
    if ($btnSave)     $btnSave.style.display    = "inline-flex";
    if ($btnReboot)   $btnReboot.style.display  = "inline-flex";
  }
}

function saveErrorReport() {
  const blob = new Blob([_updateLog], { type: "text/plain" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `sovran-update-error-${new Date().toISOString().split('.')[0].replace(/:/g, '-')}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function doReboot() {
  fetch("/api/reboot", { method: "POST" }).catch(() => {});
  if ($modalStatus) $modalStatus.textContent = "Rebooting…";
}

// ── Event listeners ───────────────────────────────────────────────

if ($updateBtn)      $updateBtn.addEventListener("click", openUpdateModal);
if ($refreshBtn)     $refreshBtn.addEventListener("click", () => refreshServices());
if ($btnCloseModal)  $btnCloseModal.addEventListener("click", closeUpdateModal);
if ($btnReboot)      $btnReboot.addEventListener("click", doReboot);
if ($btnSave)        $btnSave.addEventListener("click", saveErrorReport);

// Close modal on overlay click
if ($modal) {
  $modal.addEventListener("click", (e) => {
    if (e.target === $modal) closeUpdateModal();
  });
}

// ── Init ──────────────────────────────────────────────────────────

async function init() {
  // Load config to get category labels
  try {
    const cfg = await apiFetch("/api/config");
    if (cfg.category_order) {
      for (const [key, label] of cfg.category_order) {
        _categoryLabels[key] = label;
      }
    }
    // Update role badge
    const badge = document.getElementById("role-badge");
    if (badge && cfg.role_label) badge.textContent = cfg.role_label;
  } catch (_) {}

  // Initial data loads
  await refreshServices();
  loadNetwork();
  checkUpdates();

  // Polling
  setInterval(refreshServices, POLL_INTERVAL_SERVICES);
  setInterval(checkUpdates,    POLL_INTERVAL_UPDATES);
}

document.addEventListener("DOMContentLoaded", init);