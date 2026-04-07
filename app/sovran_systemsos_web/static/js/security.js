"use strict";

// ── Legacy security warning ───────────────────────────────────────

async function checkLegacySecurity() {
  try {
    var data = await apiFetch("/api/security/status");
    if (data && (data.status === "legacy" || data.status === "unsealed")) {
      _securityIsLegacy       = true;
      _securityStatus         = data.status;
      _securityWarningMessage = data.warning || "This machine may have a security issue. Please review your system security.";
    }
  } catch (_) {
    // Non-fatal — silently ignore if the endpoint is unreachable
  }
}
