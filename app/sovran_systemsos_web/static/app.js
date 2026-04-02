/* Sovran_SystemsOS Hub — Vanilla JS Frontend */
"use strict";

const POLL_INTERVAL_SERVICES = 5000;   // 5 s
const POLL_INTERVAL_UPDATES  = 1800000; // 30 min
const ACTION_REFRESH_DELAY   = 1500;   // 1.5 s after start/stop/restart
const UPDATE_POLL_INTERVAL   = 2000;   // 2 s while update is running
const REBOOT_CHECK_INTERVAL  = 5000;   // 5 s between reconnect attempts

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

let _servicesCache   = [];
let _categoryLabels  = {};
let _updateLog       = "";
let _updatePollTimer = null;
let _updateLogOffset = 0;
let _serverWasDown   = false;
let _updateFinished  = false;

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

// ── Helpers ───────────────────────────────────────────────────────

function tileId(svc) {
  return svc.unit + "::" + svc.name;
}

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
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function linkify(str) {
  const escaped = escHtml(str);
  return escaped.replace(
    /(https?:\/\/[^\s<]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer" class="creds-link">$1</a>'
  );
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
  const hasCreds = svc.has_credentials;

  const tile = document.createElement("div");
  tile.className = "service-tile" + (dis ? " disabled" : "");
  tile.dataset.unit = svc.unit;
  tile.dataset.tileId = tileId(svc);
  if (dis) tile.title = `${svc.name} is not enabled in custom.nix`;

  // Info button (only if service has credentials)
  const infoBtn = hasCreds
    ? `<button class="tile-info-btn" data-unit="${escHtml(svc.unit)}" title="Connection info">i</button>`
    : "";

  tile.innerHTML = `
    ${infoBtn}
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

  // Info button click handler
  const infoBtnEl = tile.querySelector(".tile-info-btn");
  if (infoBtnEl) {
    infoBtnEl.addEventListener("click", (e) => {
      e.stopPropagation();
      openCredsModal(svc.unit, svc.name);
    });
  }

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
    const id = CSS.escape(tileId(svc));
    const tile = $tilesArea.querySelector(`.service-tile[data-tile-id="${id}"]`);
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

// ── Network IPs ──────────────────────────────────��────────────────

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
    const hasUpdates = !!data.available;
    if ($updateBadge) {
      $updateBadge.classList.toggle("visible", hasUpdates);
    }
    if ($updateBtn) {
      $updateBtn.classList.toggle("has-updates", hasUpdates);
    }
  } catch (_) {}
}

// ── Credentials info modal ────────────────────────────────────────

async function openCredsModal(unit, name) {
  if (!$credsModal) return;

  if ($credsTitle) $credsTitle.textContent = name + " — Connection Info";
  if ($credsBody)  $credsBody.innerHTML = '<p class="creds-loading">Loading…</p>';

  $credsModal.classList.add("open");

  try {
    const data = await apiFetch(`/api/credentials/${encodeURIComponent(unit)}`);

    if (!data.credentials || data.credentials.length === 0) {
      $credsBody.innerHTML = '<p class="creds-empty">No connection info available yet.</p>';
      return;
    }

    let html = "";
    for (const cred of data.credentials) {
      const id = "cred-" + Math.random().toString(36).substring(2, 8);
      const displayValue = linkify(cred.value);

      // QR code block (if present)
      let qrBlock = "";
      if (cred.qrcode) {
        qrBlock = `
          <div class="creds-qr-wrap">
            <img class="creds-qr-img" src="${cred.qrcode}" alt="QR Code for ${escHtml(cred.label)}">
            <div class="creds-qr-hint">Scan with Zeus app on your phone</div>
          </div>
        `;
      }

      html += `
        <div class="creds-row">
          <div class="creds-label">${escHtml(cred.label)}</div>
          ${qrBlock}
          <div class="creds-value-wrap">
            <div class="creds-value" id="${id}">${displayValue}</div>
            <button class="creds-copy-btn" data-target="${id}">Copy</button>
          </div>
        </div>
      `;
    }
    $credsBody.innerHTML = html;

    // Attach copy handlers
    $credsBody.querySelectorAll(".creds-copy-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const target = document.getElementById(btn.dataset.target);
        if (target) {
          navigator.clipboard.writeText(target.textContent).then(() => {
            btn.textContent = "Copied!";
            btn.classList.add("copied");
            setTimeout(() => {
              btn.textContent = "Copy";
              btn.classList.remove("copied");
            }, 1500);
          }).catch(() => {});
        }
      });
    });

  } catch (err) {
    $credsBody.innerHTML = '<p class="creds-empty">Could not load credentials.</p>';
  }
}

function closeCredsModal() {
  if ($credsModal) $credsModal.classList.remove("open");
}

// ── Update modal ──────────────────────────────────────────────────

function openUpdateModal() {
  if (!$modal) return;
  _updateLog = "";
  _updateLogOffset = 0;
  _serverWasDown = false;
  _updateFinished = false;
  if ($modalLog)      $modalLog.textContent = "";
  if ($modalStatus)   $modalStatus.textContent = "Starting update…";
  if ($modalSpinner)  $modalSpinner.classList.add("spinning");
  if ($btnReboot)     { $btnReboot.style.display   = "none"; }
  if ($btnSave)       { $btnSave.style.display      = "none"; }
  if ($btnCloseModal) { $btnCloseModal.disabled     = true;   }

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
  if ($modalLog) {
    $modalLog.textContent += text;
    $modalLog.scrollTop = $modalLog.scrollHeight;
  }
}

function startUpdate() {
  fetch("/api/updates/run", { method: "POST" })
    .then(response => {
      if (!response.ok) {
        return response.text().then(t => { throw new Error(t); });
      }
      return response.json();
    })
    .then(data => {
      if (data.status === "already_running") {
        appendLog("[Update already in progress, attaching…]\n\n");
      }
      if ($modalStatus) $modalStatus.textContent = "Updating…";
      startUpdatePoll();
    })
    .catch(err => {
      appendLog(`[Error: failed to start update — ${err}]\n`);
      onUpdateDone(false);
    });
}

function startUpdatePoll() {
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
  if (_updateFinished) return;

  try {
    const data = await apiFetch(`/api/updates/status?offset=${_updateLogOffset}`);

    if (_serverWasDown) {
      _serverWasDown = false;
      appendLog("[Server reconnected]\n");
      if ($modalStatus) $modalStatus.textContent = "Updating…";
    }

    if (data.log) {
      appendLog(data.log);
    }
    _updateLogOffset = data.offset;

    if (data.running) {
      return;
    }

    _updateFinished = true;
    stopUpdatePoll();

    if (data.result === "success") {
      onUpdateDone(true);
    } else {
      onUpdateDone(false);
    }
  } catch (err) {
    if (!_serverWasDown) {
      _serverWasDown = true;
      appendLog("\n[Server restarting — waiting for it to come back…]\n");
      if ($modalStatus) $modalStatus.textContent = "Server restarting…";
    }
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

// ── Reboot with confirmation overlay ──────────────────────────────

function doReboot() {
  if ($modal) $modal.classList.remove("open");
  stopUpdatePoll();
  if ($rebootOverlay) $rebootOverlay.classList.add("visible");
  fetch("/api/reboot", { method: "POST" }).catch(() => {});
  setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
}

function waitForServerReboot() {
  fetch("/api/config", { cache: "no-store" })
    .then(res => {
      if (res.ok) {
        window.location.reload();
      } else {
        setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
      }
    })
    .catch(() => {
      setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
    });
}

// ── Event listeners ───────────────────────────────────────────────

if ($updateBtn)      $updateBtn.addEventListener("click", openUpdateModal);
if ($refreshBtn)     $refreshBtn.addEventListener("click", () => refreshServices());
if ($btnCloseModal)  $btnCloseModal.addEventListener("click", closeUpdateModal);
if ($btnReboot)      $btnReboot.addEventListener("click", doReboot);
if ($btnSave)        $btnSave.addEventListener("click", saveErrorReport);
if ($credsCloseBtn)  $credsCloseBtn.addEventListener("click", closeCredsModal);

if ($modal) {
  $modal.addEventListener("click", (e) => {
    if (e.target === $modal) closeUpdateModal();
  });
}

if ($credsModal) {
  $credsModal.addEventListener("click", (e) => {
    if (e.target === $credsModal) closeCredsModal();
  });
}

// ── Init ──────────────────────────────────────────────────────────

async function init() {
  try {
    const cfg = await apiFetch("/api/config");
    if (cfg.category_order) {
      for (const [key, label] of cfg.category_order) {
        _categoryLabels[key] = label;
      }
    }
    const badge = document.getElementById("role-badge");
    if (badge && cfg.role_label) badge.textContent = cfg.role_label;
  } catch (_) {}

  await refreshServices();
  loadNetwork();
  checkUpdates();

  setInterval(refreshServices, POLL_INTERVAL_SERVICES);
  setInterval(checkUpdates,    POLL_INTERVAL_UPDATES);
}

document.addEventListener("DOMContentLoaded", init);