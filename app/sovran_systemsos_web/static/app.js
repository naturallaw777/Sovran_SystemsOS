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
    section.dataset.category