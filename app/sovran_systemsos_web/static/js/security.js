"use strict";

// ── Legacy security warning ───────────────────────────────────────

function openSecurityWarningModal(message) {
  if ($securityWarningMessage) $securityWarningMessage.textContent = message;
  if ($securityWarningModal) $securityWarningModal.classList.add("open");
}

function closeSecurityWarningModal() {
  if ($securityWarningModal) $securityWarningModal.classList.remove("open");
}

async function checkLegacySecurity() {
  try {
    var data = await apiFetch("/api/security/status");
    if (data && data.status === "legacy") {
      openSecurityWarningModal(data.warning || "This machine may have a known factory password. Please change your passwords immediately.");
    }
  } catch (_) {
    // Non-fatal — silently ignore if the endpoint is unreachable
  }
}
