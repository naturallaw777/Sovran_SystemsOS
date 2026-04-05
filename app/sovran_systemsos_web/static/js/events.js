"use strict";

// ── Event listeners ───────────────────────────────────────────────

// if ($updateBtn) $updateBtn.addEventListener("click", openUpdateModal); // moved to sidebar in tiles.js
if ($btnCloseModal) $btnCloseModal.addEventListener("click", closeUpdateModal);
if ($btnReboot) $btnReboot.addEventListener("click", doReboot);
if ($btnSave) $btnSave.addEventListener("click", saveErrorReport);
if ($credsCloseBtn) $credsCloseBtn.addEventListener("click", closeCredsModal);
if ($supportCloseBtn) $supportCloseBtn.addEventListener("click", closeSupportModal);

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

// ── Upgrade modal functions ───────────────────────────────────────

function openUpgradeModal() {
  if ($upgradeModal) $upgradeModal.classList.add("open");
}

function closeUpgradeModal() {
  if ($upgradeModal) $upgradeModal.classList.remove("open");
}

async function doUpgradeToServer() {
  var confirmBtn = $upgradeConfirmBtn;
  if (confirmBtn) { confirmBtn.disabled = true; confirmBtn.textContent = "Upgrading…"; }
  closeUpgradeModal();

  // Reuse the rebuild modal to show progress
  _rebuildFeatureName = "Server + Desktop";
  _rebuildIsEnabling = true;
  openRebuildModal();

  try {
    await apiFetch("/api/role/upgrade-to-server", { method: "POST" });
  } catch (err) {
    if ($rebuildStatus) $rebuildStatus.textContent = "✗ Upgrade failed: " + err.message;
    if ($rebuildSpinner) $rebuildSpinner.classList.remove("spinning");
    if ($rebuildClose) $rebuildClose.disabled = false;
    if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = "Yes, Upgrade"; }
  }
}

if ($upgradeConfirmBtn) $upgradeConfirmBtn.addEventListener("click", doUpgradeToServer);

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
  } catch (_) {
    await refreshServices();
    loadNetwork();
    checkUpdates();
    setInterval(refreshServices, POLL_INTERVAL_SERVICES);
    setInterval(checkUpdates, POLL_INTERVAL_UPDATES);
  }
}

document.addEventListener("DOMContentLoaded", init);