"use strict";

// ── Event listeners ───────────────────────────────────────────────

if ($updateBtn) $updateBtn.addEventListener("click", openUpdateModal);
if ($refreshBtn) $refreshBtn.addEventListener("click", function() { refreshServices(); });
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
