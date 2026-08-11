/* Sovran_SystemsOS Hub — Vanilla JS Frontend
   v7 — Status-only dashboard + Tech Support + Feature Manager */
"use strict";

const POLL_INTERVAL_SERVICES    = 5000;
const POLL_INTERVAL_UPDATES     = 1800000;
const UPDATE_POLL_INTERVAL      = 2000;
// Max consecutive failed rebuild/update status polls before the page gives up
// waiting and reloads to re-sync (2s interval → ~2 minutes of failures).
// A brief Hub restart during activation only causes a handful of failures.
const STATUS_POLL_MAX_FAILURES  = 60;
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
