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
    else if (!status.sshd_enabled) { renderSupportSshdOff(); }
    else { renderSupportInactive(); }
  } catch (err) {
    $supportBody.innerHTML = '<p class="creds-empty">Could not check support status.</p>';
  }
}

function renderSupportSshdOff() {
  stopSupportTimer();
  $supportBody.innerHTML = [
    '<div class="support-section">',
    '<div class="support-icon-big">🛟</div>',
    '<h3 class="support-heading">Need help from Sovran Systems?</h3>',
    '<p class="support-desc">To get Tech Support, SSH must be enabled first. SSH is <strong>off by default</strong> for maximum security — it only needs to be on during a support session.</p>',
    '<div class="support-wallet-box support-wallet-protected">',
      '<div class="support-wallet-header"><span class="support-wallet-icon">🔐</span><span class="support-wallet-title">SSH is Off</span></div>',
      '<p class="support-wallet-desc">SSH (remote login) is <strong>disabled by default</strong> on your Sovran Pro. Clicking the button below will enable SSH and trigger a system rebuild. Once complete, you can then grant support access.</p>',
      '<p class="support-wallet-desc">When you end the support session, you\'ll be able to disable SSH to return to the default secure state.</p>',
    '</div>',
    '<div class="support-steps"><div class="support-steps-title">Steps:</div><ol>',
      '<li>Enable SSH (triggers a system rebuild — takes a few minutes)</li>',
      '<li>Grant Sovran Systems temporary support access</li>',
      '<li>End the session when done — you\'ll be prompted to disable SSH</li>',
    '</ol></div>',
    '<button class="btn support-btn-enable" id="btn-sshd-enable">Enable SSH</button>',
    '<p class="support-fine-print">This will trigger a NixOS rebuild. Your machine will remain operational during the rebuild.</p>',
    '</div>',
  ].join("");
  document.getElementById("btn-sshd-enable").addEventListener("click", enableSshd);
}

async function enableSshd() {
  var btn = document.getElementById("btn-sshd-enable");
  if (btn) { btn.disabled = true; btn.textContent = "Enabling SSH…"; }
  try {
    await apiFetch("/api/features/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature: "sshd", enabled: true }),
    });
    // Poll until rebuild completes and sshd_enabled is true
    $supportBody.innerHTML = [
      '<div class="support-section">',
      '<div class="support-icon-big">⚙️</div>',
      '<h3 class="support-heading">Enabling SSH…</h3>',
      '<p class="support-desc">A system rebuild is in progress. This may take a few minutes. The page will update automatically when SSH is ready.</p>',
      '<p class="creds-loading" id="sshd-rebuild-status">Rebuilding system…</p>',
      '</div>',
    ].join("");
    pollForSshdReady();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = "Enable SSH"; }
    alert("Failed to enable SSH. Please try again.");
  }
}

function pollForSshdReady() {
  var attempts = 0;
  var maxAttempts = 60; // 5 minutes (5s interval)
  var interval = setInterval(async function() {
    attempts++;
    try {
      var status = await apiFetch("/api/support/status");
      var el = document.getElementById("sshd-rebuild-status");
      if (status.sshd_enabled) {
        clearInterval(interval);
        _supportStatus = status;
        renderSupportInactive();
      } else if (attempts >= maxAttempts) {
        clearInterval(interval);
        if (el) el.textContent = "Rebuild is taking longer than expected. Please close this dialog and try again.";
      } else {
        if (el) el.textContent = "Rebuilding system… (" + attempts * 5 + "s)";
      }
    } catch (_) {}
  }, 5000);
}

function renderSupportInactive() {
  stopSupportTimer();
  var ip = _cachedExternalIp || "loading…";
  $supportBody.innerHTML = [
    '<div class="support-section">',
    '<div class="support-icon-big">🛟</div>',
    '<h3 class="support-heading">Need help from Sovran Systems?</h3>',
    '<p class="support-desc">This will temporarily grant our support team SSH access to your machine so we can help diagnose and fix issues.</p>',
    '<div class="support-wallet-box support-wallet-protected">',
      '<div class="support-wallet-header"><span class="support-wallet-icon">✅</span><span class="support-wallet-title">SSH is Active</span></div>',
      '<p class="support-wallet-desc">SSH is enabled on your machine. You can now grant Sovran Systems temporary access below.</p>',
    '</div>',
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
    '<p class="support-fine-print">You can revoke access at any time. When you end the session, you\'ll be able to disable SSH to return to the default secure state.</p>',
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
  $supportBody.innerHTML = [
    '<div class="support-section">',
    '<div class="support-icon-big">' + icon + '</div>',
    '<h3 class="support-heading">Support Session Ended</h3>',
    '<p class="support-desc">' + escHtml(msg) + '</p>',
    '<div class="support-verify-box"><span class="support-verify-label">SSH Key Status:</span><span class="support-verify-value ' + vclass + '">' + vlabel + '</span></div>',
    '<div class="support-wallet-box support-wallet-protected" style="margin-top:12px;">',
      '<div class="support-wallet-header"><span class="support-wallet-icon">🔐</span><span class="support-wallet-title">Disable SSH When Done</span></div>',
      '<p class="support-wallet-desc">SSH is still enabled on your machine. Click below to turn it off and return to the default secure state.</p>',
      '<button class="btn support-btn-enable" id="btn-sshd-disable">Disable SSH</button>',
    '</div>',
    '<button class="btn support-btn-done" id="btn-support-done">Done</button>',
    '</div>',
  ].join("");
  document.getElementById("btn-support-done").addEventListener("click", closeSupportModal);
  document.getElementById("btn-sshd-disable").addEventListener("click", disableSshd);
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

async function disableSshd() {
  var btn = document.getElementById("btn-sshd-disable");
  if (btn) { btn.disabled = true; btn.textContent = "Disabling SSH…"; }
  try {
    await apiFetch("/api/features/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature: "sshd", enabled: false }),
    });
    $supportBody.innerHTML = [
      '<div class="support-section">',
      '<div class="support-icon-big">⚙️</div>',
      '<h3 class="support-heading">Disabling SSH…</h3>',
      '<p class="support-desc">A system rebuild is in progress to turn off SSH. This may take a few minutes.</p>',
      '<p class="creds-loading" id="sshd-disable-status">Rebuilding system…</p>',
      '</div>',
    ].join("");
    pollForSshdDisabled();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = "Disable SSH"; }
    alert("Failed to disable SSH. Please try again.");
  }
}

function pollForSshdDisabled() {
  var attempts = 0;
  var maxAttempts = 60; // 5 minutes (5s interval)
  var interval = setInterval(async function() {
    attempts++;
    try {
      var status = await apiFetch("/api/support/status");
      var el = document.getElementById("sshd-disable-status");
      if (!status.sshd_enabled) {
        clearInterval(interval);
        $supportBody.innerHTML = [
          '<div class="support-section">',
          '<div class="support-icon-big">🔐</div>',
          '<h3 class="support-heading">SSH is Off</h3>',
          '<p class="support-desc">SSH has been disabled. Your machine is back to its default secure state.</p>',
          '<button class="btn support-btn-done" id="btn-support-done">Done</button>',
          '</div>',
        ].join("");
        document.getElementById("btn-support-done").addEventListener("click", closeSupportModal);
      } else if (attempts >= maxAttempts) {
        clearInterval(interval);
        if (el) el.textContent = "Rebuild is taking longer than expected. Please close this dialog and try again.";
      } else {
        if (el) el.textContent = "Rebuilding system… (" + attempts * 5 + "s)";
      }
    } catch (_) {}
  }, 5000);
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

// ── Manual Backup modal ───────────────────────────────────────────

var _backupPollTimer = null;
var _backupLogOffset = 0;

function openBackupModal() {
  if (!$supportModal) return;
  $supportModal.classList.add("open");
  $supportBody.innerHTML = '<p class="creds-loading">Detecting external drives\u2026</p>';
  detectDrivesAndRender();
}

async function detectDrivesAndRender() {
  try {
    // Check whether a backup is already in progress
    var status = await apiFetch("/api/backup/status?offset=0");
    if (status.running) {
      renderBackupRunning();
      _backupLogOffset = status.offset || 0;
      if (status.log) {
        var logDiv = document.getElementById("backup-log");
        if (logDiv) { logDiv.insertAdjacentText("beforeend", status.log); logDiv.scrollTop = logDiv.scrollHeight; }
      }
      startBackupPoll();
      return;
    }
  } catch (_) {}

  try {
    var data = await apiFetch("/api/backup/drives");
    renderBackupReady(data.drives || []);
  } catch (err) {
    $supportBody.innerHTML = '<p class="creds-empty">Could not detect drives. Please try again.</p>';
  }
}

function renderBackupReady(drives) {
  var driveSelector = "";
  if (drives.length > 0) {
    driveSelector = [
      '<label class="support-info-label" style="display:block;margin-bottom:6px;">Select drive:</label>',
      '<div style="display:flex;gap:8px;align-items:center;margin-bottom:14px;">',
        '<select id="backup-drive-select" class="support-unlock-select" style="flex:1;">',
    ].join("");
    for (var i = 0; i < drives.length; i++) {
      var d = drives[i];
      driveSelector += '<option value="' + escHtml(d.path) + '">' +
        escHtml(d.name) + ' \u2014 ' + d.free_gb + ' GB free / ' + d.total_gb + ' GB total' +
        '</option>';
    }
    driveSelector += '</select>';
    driveSelector += '<button class="btn support-btn-auditlog" id="btn-backup-refresh" style="white-space:nowrap;">&#x21bb; Refresh</button>';
    driveSelector += '</div>';
    driveSelector += '<button class="btn support-btn-enable" id="btn-start-backup">Start Backup</button>';
  } else {
    driveSelector = [
      '<div class="support-wallet-box support-wallet-warning">',
        '<div class="support-wallet-header">',
          '<span class="support-wallet-icon">\u26a0\ufe0f</span>',
          '<span class="support-wallet-title">No External Drive Detected</span>',
        '</div>',
        '<p class="support-wallet-desc">',
          'No USB drive was found under /run/media/. ',
          'Make sure the drive is plugged in and mounted, then click Refresh.',
        '</p>',
      '</div>',
      '<button class="btn support-btn-auditlog" id="btn-backup-refresh">&#x21bb; Refresh</button>',
    ].join("");
  }

  $supportBody.innerHTML = [
    '<div class="support-section">',
    '<div class="support-icon-big">\ud83d\udcbe</div>',
    '<h3 class="support-heading">Manual Backup</h3>',

    '<div class="support-wallet-box support-wallet-protected" style="margin-bottom:16px;">',
      '<p class="support-wallet-desc">',
        'Your Sovran Pro already backs up your data automatically to its internal second drive. ',
        'This manual backup lets you create an additional copy on an external USB drive \u2014 ',
        'storing your data in a third location, outside the computer, for maximum protection ',
        'against hardware failure or physical damage.',
      '</p>',
    '</div>',

    '<div class="support-steps">',
      '<div class="support-steps-title">Requirements</div>',
      '<ol class="support-backup-steps">',
        '<li>USB hard drive plugged into one of the open USB ports on your Sovran Pro</li>',
        '<li>Enough free space for your selected backup data (the backup checks this before starting)</li>',
        '<li>Drive must be formatted as <strong>exFAT</strong></li>',
      '</ol>',
    '</div>',

    '<div class="support-steps">',
      '<div class="support-steps-title">What gets backed up</div>',
      '<ol class="support-backup-steps">',
        '<li>NixOS configuration (<code>/etc/nixos</code>)</li>',
        '<li>nix-bitcoin secrets (<code>/etc/nix-bitcoin-secrets</code>)</li>',
        '<li>System service data (<code>/var/lib</code>) including Vaultwarden, bitcoind, LND, sovran-hub, domains, and secrets</li>',
        '<li>Home directory (<code>/home</code>)</li>',
      '</ol>',
    '</div>',

    '<div class="support-wallet-box support-wallet-warning">',
      '<div class="support-wallet-header">',
        '<span class="support-wallet-icon">\u23f1\ufe0f</span>',
        '<span class="support-wallet-title">Time Estimate</span>',
      '</div>',
      '<p class="support-wallet-desc">This backup can take <strong>up to 4 hours</strong> depending on the amount of data stored on your Sovran Pro and the speed of your external hard drive. Be patient\u2026</p>',
    '</div>',

    driveSelector,
    '</div>',
  ].join("");

  if (drives.length > 0) {
    document.getElementById("btn-start-backup").addEventListener("click", startBackup);
    document.getElementById("btn-backup-refresh").addEventListener("click", function() {
      $supportBody.innerHTML = '<p class="creds-loading">Scanning for external drives\u2026</p>';
      detectDrivesAndRender();
    });
  } else {
    document.getElementById("btn-backup-refresh").addEventListener("click", function() {
      $supportBody.innerHTML = '<p class="creds-loading">Scanning for external drives\u2026</p>';
      detectDrivesAndRender();
    });
  }
}

async function startBackup() {
  var btn = document.getElementById("btn-start-backup");
  if (btn) { btn.disabled = true; btn.textContent = "Starting\u2026"; }
  var sel = document.getElementById("backup-drive-select");
  var target = sel ? sel.value : "";
  try {
    _backupLogOffset = 0;
    await apiFetch("/api/backup/run" + (target ? "?target=" + encodeURIComponent(target) : ""), { method: "POST" });
    renderBackupRunning();
    startBackupPoll();
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = "Start Backup"; }
    alert("Failed to start backup: " + (err.message || "Unknown error"));
  }
}

function renderBackupRunning() {
  $supportBody.innerHTML = [
    '<div class="support-section">',
    '<div class="support-icon-big support-active-icon">\ud83d\udcbe</div>',
    '<h3 class="support-heading support-active-heading">Backup In Progress</h3>',
    '<div class="support-wallet-box support-wallet-warning">',
      '<div class="support-wallet-header">',
        '<span class="support-wallet-icon">\u26a0\ufe0f</span>',
        '<span class="support-wallet-title">Do Not Unplug</span>',
      '</div>',
      '<p class="support-wallet-desc">Do not remove the USB drive while the backup is running. This could corrupt the backup and your drive.</p>',
    '</div>',
    '<div class="modal-log" id="backup-log" style="text-align:left;"></div>',
    '</div>',
  ].join("");
}

function startBackupPoll() {
  stopBackupPoll();
  _backupPollTimer = setInterval(pollBackupStatus, 2000);
  pollBackupStatus();
}

function stopBackupPoll() {
  if (_backupPollTimer) { clearInterval(_backupPollTimer); _backupPollTimer = null; }
}

async function pollBackupStatus() {
  try {
    var data = await apiFetch("/api/backup/status?offset=" + _backupLogOffset);
    var logDiv = document.getElementById("backup-log");
    if (logDiv && data.log) {
      logDiv.insertAdjacentText("beforeend", data.log);
      logDiv.scrollTop = logDiv.scrollHeight;
    }
    _backupLogOffset = data.offset;
    const result = (data.result || "").toLowerCase();
    if (result === "success" || result === "failed") {
      stopBackupPoll();
      renderBackupDone(result === "success");
    }
  } catch (_) {}
}

function renderBackupDone(success) {
  var logDiv = document.getElementById("backup-log");
  var logContent = logDiv ? logDiv.textContent : "";

  if (success) {
    $supportBody.innerHTML = [
      '<div class="support-section">',
      '<div class="support-icon-big">\u2705</div>',
      '<h3 class="support-heading">All Finished!</h3>',
      '<div class="support-wallet-box support-wallet-protected">',
        '<div class="support-wallet-header">',
          '<span class="support-wallet-icon">\u23cf\ufe0f</span>',
          '<span class="support-wallet-title">Eject Your Drive</span>',
        '</div>',
        '<p class="support-wallet-desc">Please eject the drive before removing it from your Sovran Pro.</p>',
      '</div>',
      '<div class="modal-log" id="backup-log-done" style="text-align:left;"></div>',
      '<button class="btn support-btn-done" id="btn-backup-close">Close</button>',
      '</div>',
    ].join("");
    var doneLog = document.getElementById("backup-log-done");
    if (doneLog) { doneLog.textContent = logContent; doneLog.scrollTop = doneLog.scrollHeight; }
  } else {
    $supportBody.innerHTML = [
      '<div class="support-section">',
      '<div class="support-icon-big">\u26a0\ufe0f</div>',
      '<h3 class="support-heading">Backup Failed</h3>',
      '<p class="support-desc">The backup did not complete successfully. Please check that the USB drive is still connected, has enough free space, and is formatted as exFAT. Then try again.</p>',
      '<div class="modal-log" id="backup-log-fail" style="text-align:left;"></div>',
      '<button class="btn support-btn-done" id="btn-backup-close">Close</button>',
      '</div>',
    ].join("");
    var failLog = document.getElementById("backup-log-fail");
    if (failLog) { failLog.textContent = logContent; failLog.scrollTop = failLog.scrollHeight; }
  }
  document.getElementById("btn-backup-close").addEventListener("click", closeSupportModal);
}
