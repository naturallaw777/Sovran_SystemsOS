"use strict";

// ── Event listeners ───────────────────────────────────────────────

// if ($updateBtn) $updateBtn.addEventListener("click", openUpdateModal); // moved to sidebar in tiles.js
if ($btnCloseModal) $btnCloseModal.addEventListener("click", closeUpdateModal);
if ($btnReboot) $btnReboot.addEventListener("click", doReboot);
if ($btnSave) $btnSave.addEventListener("click", saveErrorReport);
if ($credsCloseBtn) $credsCloseBtn.addEventListener("click", closeCredsModal);
if ($supportCloseBtn) $supportCloseBtn.addEventListener("click", closeSupportModal);

// Logout button
if ($logoutBtn) $logoutBtn.addEventListener("click", function () {
  fetch("/api/logout", { method: "POST", credentials: "same-origin" })
    .finally(function () { window.location.replace("/login"); });
});

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

// Upgrade modal
if ($upgradeCloseBtn) $upgradeCloseBtn.addEventListener("click", closeUpgradeModal);
if ($upgradeCancelBtn) $upgradeCancelBtn.addEventListener("click", closeUpgradeModal);
if ($upgradeModal) $upgradeModal.addEventListener("click", function(e) { if (e.target === $upgradeModal) closeUpgradeModal(); });

// Restart confirm dialog
if ($restartConfirmCancel) $restartConfirmCancel.addEventListener("click", closeRestartConfirmDialog);
if ($restartConfirmModal) $restartConfirmModal.addEventListener("click", function(e) { if (e.target === $restartConfirmModal) closeRestartConfirmDialog(); });
if ($restartConfirmModal) $restartConfirmModal.addEventListener("keydown", function(e) { if (e.key === "Escape") closeRestartConfirmDialog(); });
if ($restartConfirmOk) $restartConfirmOk.addEventListener("click", function() {
  if ($restartConfirmOk.disabled) return;
  $restartConfirmOk.disabled = true;
  closeRestartConfirmDialog();
  doReboot();
});

// Reboot error card buttons
var $rebootErrorCloseBtn = document.getElementById("reboot-error-close-btn");
var $rebootErrorRetryBtn = document.getElementById("reboot-error-retry-btn");
if ($rebootErrorCloseBtn) $rebootErrorCloseBtn.addEventListener("click", function() {
  if ($rebootOverlay) $rebootOverlay.classList.remove("visible");
});
if ($rebootErrorRetryBtn) $rebootErrorRetryBtn.addEventListener("click", doReboot);

// ── Upgrade modal functions ───────────────────────────────────────

function openUpgradeModal() {
  if ($upgradeModal) $upgradeModal.classList.add("open");
}

function closeUpgradeModal() {
  if ($upgradeModal) $upgradeModal.classList.remove("open");
}

// ── Restart confirm dialog functions ─────────────────────────────

var _restartDialogOpener = null;

function openRestartConfirmDialog() {
  if (!$restartConfirmModal) return;
  _restartDialogOpener = document.activeElement;

  // Detect conflicting operations
  var isOperationInProgress = !!_updatePollTimer || !!_rebuildPollTimer;
  if ($restartConflictBox) $restartConflictBox.style.display = isOperationInProgress ? "" : "none";
  if ($restartConfirmOk) $restartConfirmOk.disabled = isOperationInProgress;

  $restartConfirmModal.classList.add("open");

  // Focus Cancel initially for safety
  var cancelBtn = document.getElementById("restart-confirm-cancel-btn");
  if (cancelBtn) setTimeout(function() { cancelBtn.focus(); }, 50);
}

function closeRestartConfirmDialog() {
  if ($restartConfirmModal) $restartConfirmModal.classList.remove("open");
  // Re-enable confirm button for next open
  if ($restartConfirmOk) $restartConfirmOk.disabled = false;
  // Return focus to the element that opened the dialog
  if (_restartDialogOpener && _restartDialogOpener.focus) {
    try { _restartDialogOpener.focus(); } catch (_) {}
    _restartDialogOpener = null;
  }
}

async function doUpgradeToServer() {
  var confirmBtn = $upgradeConfirmBtn;
  if (confirmBtn) { confirmBtn.disabled = true; confirmBtn.textContent = "Upgrading…"; }
  closeUpgradeModal();

  // Reuse the rebuild modal to show reboot progress
  _rebuildFeatureName = "Server + Desktop";
  _rebuildIsEnabling = true;
  openRebuildModal();

  try {
    await apiFetch("/api/role/upgrade-to-server", { method: "POST" });
    // Server is rebooting — show message and wait for it to come back
    if ($rebuildStatus) $rebuildStatus.textContent = "Rebooting — the setup wizard will guide you through domain and port configuration…";
    if ($rebuildSpinner) $rebuildSpinner.classList.add("spinning");

    // Poll until server comes back, then redirect to onboarding
    var pollInterval = setInterval(async function() {
      try {
        await apiFetch("/api/ping");
        clearInterval(pollInterval);
        window.location.href = "/onboarding";
      } catch (_) {
        // Server still down — keep polling
      }
    }, 3000);
  } catch (err) {
    if ($rebuildStatus) $rebuildStatus.textContent = "✗ Upgrade failed: " + err.message;
    if ($rebuildSpinner) $rebuildSpinner.classList.remove("spinning");
    if ($rebuildClose) $rebuildClose.disabled = false;
    if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = "Yes, Upgrade"; }
  }
}

if ($upgradeConfirmBtn) $upgradeConfirmBtn.addEventListener("click", doUpgradeToServer);

// ── First-login security banner ───────────────────────────────────

function showSecurityBanner() {
  var existing = document.getElementById("security-first-login-banner");
  if (existing) return;

  var banner = document.createElement("div");
  banner.id = "security-first-login-banner";
  banner.className = "security-first-login-banner";
  banner.innerHTML =
    '<div class="security-banner-content">' +
      '<span class="security-banner-icon">\uD83D\uDEE1</span>' +
      '<span class="security-banner-text">' +
        '<strong>Did someone else set up this machine?</strong> ' +
        'If this computer was pre-configured by another person, go to ' +
        '<strong>Menu \u2192 Security</strong> to reset all passwords and keys. ' +
        'This ensures only you have access.' +
      '</span>' +
    '</div>' +
    '<button class="security-banner-dismiss" id="security-banner-dismiss-btn" title="Dismiss">\u2715</button>';

  var mainContent = document.querySelector(".main-content");
  if (mainContent) {
    mainContent.insertAdjacentElement("beforebegin", banner);
  } else {
    document.body.insertAdjacentElement("afterbegin", banner);
  }

  var dismissBtn = document.getElementById("security-banner-dismiss-btn");
  if (dismissBtn) {
    dismissBtn.addEventListener("click", async function() {
      banner.remove();
      try {
        await apiFetch("/api/security/banner-dismiss", { method: "POST" });
      } catch (_) {
        // Non-fatal
      }
    });
  }
}

// ── Init ──────────────────────────────────────────────────────────

async function init() {
  // Check onboarding status first — redirect to wizard if not complete
  try {
    var onboardingStatus = await apiFetch("/api/onboarding/status");
    if (!onboardingStatus.complete) {
      window.location.href = "/onboarding";
      return;
    }
  } catch (_) {
    // If we can't reach the endpoint, continue to normal dashboard
  }

  // Show first-login security banner only for machines that went through onboarding
  // (legacy machines without the onboarding flag will never see this)
  try {
    var bannerData = await apiFetch("/api/security/banner-status");
    if (bannerData && bannerData.show) {
      showSecurityBanner();
    }
  } catch (_) {
    // Non-fatal — silently ignore
  }

  try {
    var cfg = await apiFetch("/api/config");
    _currentRole = cfg.role || "server_plus_desktop";
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
    loadAutolaunchToggle();
  } catch (_) {
    await refreshServices();
    loadNetwork();
    checkUpdates();
    setInterval(refreshServices, POLL_INTERVAL_SERVICES);
    setInterval(checkUpdates, POLL_INTERVAL_UPDATES);
    loadAutolaunchToggle();
  }
}

document.addEventListener("DOMContentLoaded", init);