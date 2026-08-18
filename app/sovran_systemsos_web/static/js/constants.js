/* Sovran_SystemsOS Hub — Vanilla JS Frontend
   v7 — Status-only dashboard + Tech Support + Feature Manager */
"use strict";

const POLL_INTERVAL_SERVICES    = 5000;
const POLL_INTERVAL_UPDATES     = 1800000;
const UPDATE_POLL_INTERVAL          = 2000;
// A pending fetch never rejects by itself. Bound every status request so a
// wedged browser connection cannot leave the modal spinning forever.
const STATUS_POLL_FETCH_TIMEOUT      = 15000;
// Eight timed-out requests plus the poll interval is a little over two minutes.
// A brief Hub restart or a heavily loaded Nix build remains well inside this.
const STATUS_POLL_MAX_FAILURES       = 8;
// Keep verbose Nix output from making textContent updates quadratic and
// freezing the Hub renderer (especially noticeable over RDP).
const UPDATE_VISIBLE_LOG_MAX_CHARS   = 250000;
const UPDATE_VISIBLE_LOG_TRIM_CHARS  = 200000;
const REBOOT_CHECK_INTERVAL     = 5000;
const REBOOT_FETCH_TIMEOUT      = 12000;
const REBOOT_REQUEST_TIMEOUT    = 4000;
const REBOOT_INITIAL_DELAY      = 25000;
const SUPPORT_TIMER_INTERVAL    = 1000;

const CATEGORY_ORDER = [
  "infrastructure",
  "bitcoin-base",
  "bitcoin-apps",
  "communication",
  "apps",
  "nostr",
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
