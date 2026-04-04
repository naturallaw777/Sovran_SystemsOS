"use strict";

// ── Tech Support modal ────────────────────────────────────────────

async function openSupportModal() {
  if (!$supportModal) return;
  $supportModal.classList.add("open");
  $supportBody.innerHTML = '<p class="creds-loading">Checking support status…</p>';
  try {
    var status = await apiFetch("/api/support/status");
    _supportStatus = status;
    if (status.active) { _supportEnabledAt = status.enabled_at; renderSupportActive(status); }
    else { renderSupportInactive(); }
  } catch (err) {
    $supportBody.innerHTML = '<p class="creds-empty">Could not check support status.</p>';
  }
}

function renderSupportInactive() {
  stopSupportTimer();
  var ip = _cachedExternalIp || "loading…";
  $supportBody.innerHTML = [
    '<div class="support-section">',
    '<div class="support-icon-big">🛟</div>',
    '<h3 class="support-heading">Need help from Sovran Systems?</h3>',
    '<p class="support-desc">This will temporarily grant our support team SSH access to your machine so we can help diagnose and fix issues.</p>',
    '<div class="support-info-box">',
      '<div class="support-info-row"><span class="support-info-label">Your IP</span><span class="support-info-value">' + escHtml(ip) + '</span></div>',
      '<div class="support-info-hint">This IP will be shared with Sovran Systems support</div>',
    '</div>',
    '<div class="support-wallet-box support-wallet-protected">',
      '<div class="support-wallet-header"><span class="support-wallet-icon">🔒</span><span class="support-wallet-title">Wallet Protection</span></div>',
      '<p class="support-wallet-desc">Wallet files (LND, Sparrow, Bisq) are <strong>protected by default</strong>. Support staff cannot access your private keys unless you explicitly grant access.</p>',
    '</div>',
    '<div class="support-steps"><div class="support-steps-title">What happens:</div><ol>',
      '<li>A restricted <code>sovran-support</code> user is created with limited access</li>',
      '<li>Our SSH key is added only to that restricted account</li>',
      '<li>Wallet files are locked via access controls — not visible to support</li>',
      '<li>You control if and when wallet access is granted (time-limited)</li>',
      '<li>All session events are logged for your audit</li>',
    '</ol></div>',
    '<button class="btn support-btn-enable" id="btn-support-enable">Enable Support Access</button>',
    '<p class="support-fine-print">You can revoke access at any time. Wallet files are protected unless you unlock them.</p>',
    '</div>',
  ].join("");
  document.getElementById("btn-support-enable").addEventListener("click", enableSupport);
}

function renderSupportActive(status) {
  var ip = _cachedExternalIp || "loading…";
  var walletProtected = status && status.wallet_protected;
  var walletUnlocked  = status && status.wallet_unlocked;
  var unlockUntil     = status && status.wallet_unlocked_until_human ? status.wallet_unlocked_until_human : "";
  var protectedPaths  = (status && status.protected_paths && status.protected_paths.length)
    ? status.protected_paths : [];

  var walletSection;
  if (walletProtected) {
    if (walletUnlocked) {
      walletSection = [
        '<div class="support-wallet-box support-wallet-unlocked">',
          '<div class="support-wallet-header"><span class="support-wallet-icon">🔓</span><span class="support-wallet-title">Wallet Access: UNLOCKED</span></div>',
          '<p class="support-wallet-desc">You have granted support temporary access to wallet files' + (unlockUntil ? ' until <strong>' + escHtml(unlockUntil) + '</strong>' : '') + '.</p>',
          '<button class="btn support-btn-wallet-lock" id="btn-wallet-lock">Re-lock Wallet Now</button>',
        '</div>',
      ].join("");
    } else {
      var pathList = protectedPaths.length
        ? '<ul class="support-wallet-paths">' + protectedPaths.map(function(p){ return '<li>' + escHtml(p) + '</li>'; }).join("") + '</ul>'
        : '';
      walletSection = [
        '<div class="support-wallet-box support-wallet-protected">',
          '<div class="support-wallet-header"><span class="support-wallet-icon">🔒</span><span class="support-wallet-title">Wallet Files: Protected</span></div>',
          '<p class="support-wallet-desc">Support cannot access your wallet files. Grant temporary access only if needed for wallet troubleshooting.</p>',
          pathList,
          '<div class="support-wallet-unlock-row">',
            '<select id="wallet-unlock-duration" class="support-unlock-select">',
              '<option value="3600">1 hour</option>',
              '<option value="1800">30 minutes</option>',
              '<option value="7200">2 hours</option>',
            '</select>',
            '<button class="btn support-btn-wallet-unlock" id="btn-wallet-unlock">Grant Wallet Access</button>',
          '</div>',
        '</div>',
      ].join("");
    }
  } else {
    walletSection = [
      '<div class="support-wallet-box support-wallet-warning">',
        '<div class="support-wallet-header"><span class="support-wallet-icon">⚠️</span><span class="support-wallet-title">Wallet Protection Unavailable</span></div>',
        '<p class="support-wallet-desc">The restricted support user could not be created. Support is running with root access — wallet files may be accessible. End the session if you are concerned.</p>',
      '</div>',
    ].join("");
  }

  $supportBody.innerHTML = [
    '<div class="support-section">',
    '<div class="support-icon-big support-active-icon">🔓</div>',
    '<h3 class="support-heading support-active-heading">Support Access is Active</h3>',
    '<p class="support-active-note">Sovran Systems can currently connect to your machine via SSH.</p>',
    '<div class="support-info-box support-active-box">',
      '<div class="support-info-row"><span class="support-info-label">Your IP</span><span class="support-info-value">' + escHtml(ip) + '</span></div>',
      '<div class="support-info-row"><span class="support-info-label">Duration</span><span class="support-info-value" id="support-timer">…</span></div>',
    '</div>',
    walletSection,
    '<button class="btn support-btn-disable" id="btn-support-disable">End Support Session</button>',
    '<p class="support-fine-print">This will remove the SSH key and revoke all wallet access immediately.</p>',
    '<button class="btn support-btn-auditlog" id="btn-support-audit">View Audit Log</button>',
    '</div>',
    '<div id="support-audit-container" class="support-audit-container" style="display:none;"></div>',
  ].join("");

  document.getElementById("btn-support-disable").addEventListener("click", disableSupport);
  document.getElementById("btn-support-audit").addEventListener("click", toggleAuditLog);
  if (walletProtected && !walletUnlocked) {
    document.getElementById("btn-wallet-unlock").addEventListener("click", walletUnlock);
  }
  if (walletProtected && walletUnlocked) {
    document.getElementById("btn-wallet-lock").addEventListener("click", walletLock);
  }
  startSupportTimer();
  if (walletUnlocked && status.wallet_unlocked_until) {
    startWalletUnlockTimer(status.wallet_unlocked_until);
  }
}

function renderSupportRemoved(verified) {
  stopSupportTimer();
  stopWalletUnlockTimer();
  var icon = verified ? "✅" : "⚠️";
  var msg = verified ? "The Sovran Systems SSH key has been completely removed from your machine. We no longer have any access." : "The key removal was requested but could not be fully verified. Please reboot to ensure it is gone.";
  var vclass = verified ? "verified-gone" : "verify-warning";
  var vlabel = verified ? "✓ Removed — No access" : "⚠ Verify by rebooting";
  $supportBody.innerHTML = '<div class="support-section"><div class="support-icon-big">' + icon + '</div><h3 class="support-heading">Support Session Ended</h3><p class="support-desc">' + escHtml(msg) + '</p><div class="support-verify-box"><span class="support-verify-label">SSH Key Status:</span><span class="support-verify-value ' + vclass + '">' + vlabel + '</span></div><button class="btn support-btn-done" id="btn-support-done">Done</button></div>';
  document.getElementById("btn-support-done").addEventListener("click", closeSupportModal);
}

async function enableSupport() {
  var btn = document.getElementById("btn-support-enable");
  if (btn) { btn.disabled = true; btn.textContent = "Enabling…"; }
  try {
    await apiFetch("/api/support/enable", { method: "POST" });
    var status = await apiFetch("/api/support/status");
    _supportStatus = status;
    _supportEnabledAt = status.enabled_at;
    renderSupportActive(status);
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = "Enable Support Access"; }
    alert("Failed to enable support access. Please try again.");
  }
}

async function disableSupport() {
  var btn = document.getElementById("btn-support-disable");
  if (btn) { btn.disabled = true; btn.textContent = "Removing key…"; }
  try {
    var result = await apiFetch("/api/support/disable", { method: "POST" });
    renderSupportRemoved(result.verified);
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = "End Support Session"; }
    alert("Failed to disable support access. Please try again.");
  }
}

async function walletUnlock() {
  var btn = document.getElementById("btn-wallet-unlock");
  var sel = document.getElementById("wallet-unlock-duration");
  var duration = sel ? parseInt(sel.value, 10) : 3600;
  if (btn) { btn.disabled = true; btn.textContent = "Unlocking…"; }
  try {
    var result = await apiFetch("/api/support/wallet-unlock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration: duration }),
    });
    var status = await apiFetch("/api/support/status");
    _supportStatus = status;
    renderSupportActive(status);
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = "Grant Wallet Access"; }
    alert("Failed to unlock wallet access: " + (err.message || "Unknown error"));
  }
}

async function walletLock() {
  var btn = document.getElementById("btn-wallet-lock");
  if (btn) { btn.disabled = true; btn.textContent = "Locking…"; }
  try {
    await apiFetch("/api/support/wallet-lock", { method: "POST" });
    var status = await apiFetch("/api/support/status");
    _supportStatus = status;
    renderSupportActive(status);
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = "Re-lock Wallet Now"; }
    alert("Failed to re-lock wallet: " + (err.message || "Unknown error"));
  }
}

async function toggleAuditLog() {
  var container = document.getElementById("support-audit-container");
  if (!container) return;
  if (container.style.display !== "none") {
    container.style.display = "none";
    return;
  }
  container.style.display = "block";
  container.innerHTML = '<p class="creds-loading">Loading audit log…</p>';
  try {
    var data = await apiFetch("/api/support/audit-log");
    if (!data.entries || data.entries.length === 0) {
      container.innerHTML = '<p class="support-audit-empty">No audit events recorded yet.</p>';
    } else {
      container.innerHTML = '<div class="support-audit-log">' +
        data.entries.map(function(e) { return '<div class="support-audit-entry">' + escHtml(e) + '</div>'; }).join("") +
        '</div>';
    }
  } catch (err) {
    container.innerHTML = '<p class="creds-empty">Could not load audit log.</p>';
  }
}

function startSupportTimer() {
  stopSupportTimer();
  updateSupportTimer();
  _supportTimerInt = setInterval(updateSupportTimer, SUPPORT_TIMER_INTERVAL);
}

function stopSupportTimer() {
  if (_supportTimerInt) { clearInterval(_supportTimerInt); _supportTimerInt = null; }
}

function updateSupportTimer() {
  var el = document.getElementById("support-timer");
  if (!el || !_supportEnabledAt) return;
  var elapsed = (Date.now() / 1000) - _supportEnabledAt;
  el.textContent = formatDuration(Math.max(0, elapsed));
}

function startWalletUnlockTimer(expiresAt) {
  stopWalletUnlockTimer();
  _walletUnlockTimerInt = setInterval(function() {
    if (Date.now() / 1000 >= expiresAt) {
      stopWalletUnlockTimer();
      // Refresh the support modal to show re-locked state
      apiFetch("/api/support/status").then(function(status) {
        _supportStatus = status;
        renderSupportActive(status);
      }).catch(function() {});
    }
  }, 10000);
}

function stopWalletUnlockTimer() {
  if (_walletUnlockTimerInt) { clearInterval(_walletUnlockTimerInt); _walletUnlockTimerInt = null; }
}

function closeSupportModal() {
  if ($supportModal) $supportModal.classList.remove("open");
  stopSupportTimer();
  stopWalletUnlockTimer();
}
