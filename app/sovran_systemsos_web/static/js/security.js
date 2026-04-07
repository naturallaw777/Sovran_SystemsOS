"use strict";

// ── Legacy security warning ───────────────────────────────────────

async function checkLegacySecurity() {
  try {
    var data = await apiFetch("/api/security/status");
    if (data && data.status === "legacy") {
      _securityIsLegacy       = true;
      _securityWarningMessage = data.warning || "This machine may have a known factory password. Please change your passwords immediately.";
    }
  } catch (_) {
    // Non-fatal — silently ignore if the endpoint is unreachable
  }
}
