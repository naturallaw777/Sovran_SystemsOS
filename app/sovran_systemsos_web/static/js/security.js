"use strict";

// ── Security Modal ────────────────────────────────────────────────

function openSecurityModal() {
  if ($supportModal) $supportModal.classList.add("open");
  var title = document.getElementById("support-modal-title");
  if (title) title.textContent = "\uD83D\uDEE1 Security";

  if ($supportBody) {
    $supportBody.innerHTML =
      // ── Section A: Security Reset ──────────────────────────────
      '<div class="security-section">' +
        '<h3 class="security-section-title">Security Reset</h3>' +
        '<p class="security-section-desc">' +
          'Run this if you are using this physical computer for the first time <strong>AND</strong> ' +
          'it was not set up by you. This will complete the security setup by resetting all passwords ' +
          'and your Bitcoin Lightning Node\u2019s private keys.' +
        '</p>' +
        '<p class="security-section-desc">' +
          'You can also run this if you wish to reset all your passwords and your Bitcoin Lightning ' +
          'Node\u2019s private keys. If you have not transferred the Bitcoin out of this node and did ' +
          'not back up the private keys, <strong>you will lose your Bitcoin.</strong>' +
        '</p>' +
        '<button class="btn btn-primary" id="security-reset-open-btn">Proceed with Security Reset</button>' +
        '<div id="security-reset-confirm" style="display:none;margin-top:16px;">' +
          '<div class="security-warning-box">' +
            '<p class="security-warning-text">' +
              '<strong>\u26A0\uFE0F This will permanently delete:</strong>' +
            '</p>' +
            '<ul class="security-warning-list">' +
              '<li>All generated passwords and SSH keys</li>' +
              '<li>LND wallet data (seed words, channels, macaroons)</li>' +
              '<li>Application databases</li>' +
              '<li>Vaultwarden data</li>' +
            '</ul>' +
            '<p class="security-warning-text">You will go through onboarding again. <strong>This cannot be undone.</strong></p>' +
          '</div>' +
          '<div class="security-erase-group">' +
            '<label class="security-erase-label" for="security-erase-input">Type <strong>ERASE</strong> to confirm:</label>' +
            '<input class="security-erase-input" type="text" id="security-erase-input" autocomplete="off" placeholder="ERASE" />' +
          '</div>' +
          '<div class="security-reset-actions">' +
            '<button class="btn btn-close-modal" id="security-reset-cancel-btn">Cancel</button>' +
            '<button class="btn btn-danger" id="security-reset-confirm-btn" disabled>Erase &amp; Reset</button>' +
          '</div>' +
          '<div id="security-reset-status" class="security-status-msg"></div>' +
        '</div>' +
      '</div>' +

      '<hr class="security-divider" />' +

      // ── Section B: Verify System Integrity ────────────────────
      '<div class="security-section">' +
        '<h3 class="security-section-title">Verify System Integrity</h3>' +
        '<p class="security-section-desc">' +
          'Your Sovran_SystemsOS is built with NixOS \u2014 a system designed for complete transparency ' +
          'and reproducibility. Every piece of software on this machine is built from publicly auditable ' +
          'source code and verified using cryptographic hashes.' +
        '</p>' +
        '<p class="security-section-desc">This verification confirms three things:</p>' +
        '<ol class="security-verify-list">' +
          '<li>' +
            '<strong>Source Code Match</strong> \u2014 The system configuration on this machine matches ' +
            'the exact commit published in the public repository. No hidden changes were added.' +
          '</li>' +
          '<li>' +
            '<strong>Binary Integrity</strong> \u2014 Every installed package in the system store is ' +
            'verified against its expected cryptographic hash. If any binary, library, or config file ' +
            'was tampered with, it will be detected.' +
          '</li>' +
          '<li>' +
            '<strong>Running System Match</strong> \u2014 The currently running system matches what the ' +
            'configuration says it should be. No unauthorized modifications are active.' +
          '</li>' +
        '</ol>' +
        '<p class="security-section-desc">' +
          'In short: if this verification passes, you can be confident that the software running on ' +
          'your machine is exactly what is published \u2014 nothing more, nothing less.' +
        '</p>' +
        '<button class="btn btn-primary" id="security-verify-btn">Verify Now</button>' +
        '<div id="security-verify-results" style="display:none;margin-top:16px;"></div>' +
      '</div>';

    // ── Wire Security Reset flow
    var resetOpenBtn = document.getElementById("security-reset-open-btn");
    var resetConfirmDiv = document.getElementById("security-reset-confirm");
    var eraseInput = document.getElementById("security-erase-input");
    var resetConfirmBtn = document.getElementById("security-reset-confirm-btn");
    var resetCancelBtn = document.getElementById("security-reset-cancel-btn");
    var resetStatus = document.getElementById("security-reset-status");

    if (resetOpenBtn) {
      resetOpenBtn.addEventListener("click", function() {
        resetOpenBtn.style.display = "none";
        if (resetConfirmDiv) resetConfirmDiv.style.display = "";
        if (eraseInput) eraseInput.focus();
      });
    }

    if (eraseInput && resetConfirmBtn) {
      eraseInput.addEventListener("input", function() {
        resetConfirmBtn.disabled = eraseInput.value.trim() !== "ERASE";
      });
    }

    if (resetCancelBtn) {
      resetCancelBtn.addEventListener("click", function() {
        if (resetConfirmDiv) resetConfirmDiv.style.display = "none";
        if (resetOpenBtn) resetOpenBtn.style.display = "";
        if (eraseInput) eraseInput.value = "";
        if (resetConfirmBtn) resetConfirmBtn.disabled = true;
        if (resetStatus) { resetStatus.textContent = ""; resetStatus.className = "security-status-msg"; }
      });
    }

    if (resetConfirmBtn) {
      resetConfirmBtn.addEventListener("click", async function() {
        if (!eraseInput || eraseInput.value.trim() !== "ERASE") return;
        resetConfirmBtn.disabled = true;
        resetConfirmBtn.textContent = "Erasing\u2026";

        // Show the full-screen blocking overlay immediately so the user knows
        // the wipe is in progress even while the API call runs synchronously.
        var $secResetOverlay = document.getElementById("security-reset-overlay");
        var $secResetStep = document.getElementById("security-reset-overlay-step");
        if ($secResetOverlay) $secResetOverlay.classList.add("visible");
        // Close the support modal so its content doesn't bleed through the overlay
        if ($supportModal) $supportModal.classList.remove("open");

        if (resetStatus) { resetStatus.textContent = "Running security reset\u2026"; resetStatus.className = "security-status-msg security-status-info"; }
        try {
          var data = await apiFetch("/api/security/reset", { method: "POST" });

          // Switch to Phase 2: show the new password and wait for user confirmation
          var phase1 = document.getElementById("security-reset-phase1");
          var phase2 = document.getElementById("security-reset-phase2");
          var passwordBox = document.getElementById("security-reset-new-password");
          var rebootBtn = document.getElementById("security-reset-reboot-btn");

          if (phase1) phase1.style.display = "none";
          if (phase2) phase2.style.display = "";
          if (passwordBox && data.new_password) passwordBox.textContent = data.new_password;

          if (rebootBtn) {
            // Keep button disabled for 5 seconds to prevent accidental clicks
            var countdown = 5;
            rebootBtn.textContent = "I have written down my new password \u2014 Reboot now (" + countdown + ")";
            var timer = setInterval(function() {
              countdown--;
              if (countdown <= 0) {
                clearInterval(timer);
                rebootBtn.disabled = false;
                rebootBtn.textContent = "I have written down my new password \u2014 Reboot now";
              } else {
                rebootBtn.textContent = "I have written down my new password \u2014 Reboot now (" + countdown + ")";
              }
            }, 1000);

            rebootBtn.addEventListener("click", function() {
              rebootBtn.disabled = true;
              rebootBtn.textContent = "Rebooting\u2026";
              if ($rebootOverlay) $rebootOverlay.classList.add("visible");
              setTimeout(waitForServerReboot, REBOOT_INITIAL_DELAY);
              var rebootCtrl = new AbortController();
              setTimeout(function() { rebootCtrl.abort(); }, REBOOT_REQUEST_TIMEOUT);
              fetch("/api/reboot", { method: "POST", signal: rebootCtrl.signal }).catch(function() {});
            }, { once: true });
          }
        } catch (err) {
          if ($secResetOverlay) $secResetOverlay.classList.remove("visible");
          if (resetStatus) { resetStatus.textContent = "\u2717 Error: " + (err.message || "Reset failed."); resetStatus.className = "security-status-msg security-status-error"; }
          resetConfirmBtn.disabled = false;
          resetConfirmBtn.textContent = "Erase & Reset";
        }
      });
    }

    // ── Wire Verify System Integrity
    var verifyBtn = document.getElementById("security-verify-btn");
    var verifyResults = document.getElementById("security-verify-results");

    if (verifyBtn && verifyResults) {
      verifyBtn.addEventListener("click", async function() {
        verifyBtn.disabled = true;
        verifyBtn.textContent = "Verifying\u2026";
        verifyResults.style.display = "";
        verifyResults.innerHTML = '<p class="security-verify-loading">\u231B Running verification checks\u2026 This may take a few minutes.</p>';

        try {
          var data = await apiFetch("/api/security/verify-integrity", { method: "POST" });
          var html = '<div class="security-verify-result-card">';

          // Flake commit
          html += '<div class="security-verify-row">';
          html += '<span class="security-verify-label">Source Commit:</span>';
          html += '<span class="security-verify-value security-verify-mono">' + escHtml(data.flake_commit || "unknown") + '</span>';
          if (data.repo_url) {
            html += '<a class="security-verify-link" href="' + escHtml(data.repo_url) + '" target="_blank" rel="noopener noreferrer">View on Gitea \u2197</a>';
          }
          html += '</div>';

          // Store verification
          var storeOk = data.store_verified === true;
          html += '<div class="security-verify-row">';
          html += '<span class="security-verify-label">Binary Integrity:</span>';
          html += '<span class="security-verify-badge ' + (storeOk ? "security-verify-pass" : "security-verify-fail") + '">';
          html += storeOk ? "\u2705 PASS" : "\u274C FAIL";
          html += '</span>';
          html += '</div>';
          if (!storeOk && data.store_errors && data.store_errors.length > 0) {
            html += '<details class="security-verify-errors"><summary>Show errors (' + data.store_errors.length + ')</summary>';
            html += '<pre class="security-verify-pre">' + escHtml(data.store_errors.join("\n")) + '</pre>';
            html += '</details>';
          }

          // System match
          var sysOk = data.system_matches === true;
          html += '<div class="security-verify-row">';
          html += '<span class="security-verify-label">Running System Match:</span>';
          html += '<span class="security-verify-badge ' + (sysOk ? "security-verify-pass" : "security-verify-fail") + '">';
          html += sysOk ? "\u2705 PASS" : "\u274C FAIL";
          html += '</span>';
          html += '</div>';
          if (!sysOk) {
            html += '<div class="security-verify-path-row">';
            html += '<span class="security-verify-path-label">Current:</span><code class="security-verify-mono">' + escHtml(data.current_system_path || "") + '</code>';
            html += '</div>';
            html += '<div class="security-verify-path-row">';
            html += '<span class="security-verify-path-label">Expected:</span><code class="security-verify-mono">' + escHtml(data.expected_system_path || "") + '</code>';
            html += '</div>';
          }

          html += '</div>';
          verifyResults.innerHTML = html;
        } catch (err) {
          verifyResults.innerHTML = '<p class="security-status-msg security-status-error">\u274C Verification failed: ' + escHtml(err.message || "Unknown error") + '</p>';
        }

        verifyBtn.disabled = false;
        verifyBtn.textContent = "Verify Now";
      });
    }
  }
}
