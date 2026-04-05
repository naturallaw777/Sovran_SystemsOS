"use strict";

// ── Helpers ───────────────────────────────────────────────────────

function tileId(svc) { return svc.unit + "::" + svc.name; }

function statusClass(health) {
  if (!health) return "unknown";
  if (health === "healthy")         return "active";
  if (health === "needs_attention") return "needs-attention";
  if (health === "active")          return "active";   // backwards compat
  if (health === "inactive")        return "inactive";
  if (health === "failed")          return "failed";
  if (health === "disabled")        return "disabled";
  if (health === "syncing")         return "syncing";
  if (STATUS_LOADING_STATES.has(health)) return "loading";
  return "unknown";
}

function statusText(health, enabled) {
  if (!enabled) return "Disabled";
  if (health === "healthy")         return "Active";
  if (health === "needs_attention") return "Needs Attention";
  if (health === "active")          return "Active";
  if (health === "inactive")        return "Inactive";
  if (health === "failed")          return "Failed";
  if (health === "syncing")         return "Syncing\u2026";
  if (!health || health === "unknown") return "Unknown";
  if (STATUS_LOADING_STATES.has(health)) return health;
  return health;
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
  if (!res.ok) {
    let detail = res.status + " " + res.statusText;
    try { const body = await res.json(); if (body && body.detail) detail = body.detail; } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}
