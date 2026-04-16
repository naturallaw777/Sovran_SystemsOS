"use strict";

// ── Service detail modal ──────────────────────────────────────────

function _renderCredsHtml(credentials, unit) {
  var html = "";
  for (var i = 0; i < credentials.length; i++) {
    var cred = credentials[i];
    var id = "cred-" + Math.random().toString(36).substring(2, 8);
    var displayValue = linkify(cred.value);
    var qrBlock = "";
    if (cred.qrcode) {
      qrBlock = '<div class="creds-qr-wrap"><img class="creds-qr-img" src="' + cred.qrcode + '" alt="QR Code for ' + escHtml(cred.label) + '"><div class="creds-qr-hint">Scan with Zeus app on your phone</div></div>';
    }
    html += '<div class="creds-row"><div class="creds-label">' + escHtml(cred.label) + '</div>' + qrBlock + '<div class="creds-value-wrap"><div class="creds-value" id="' + id + '">' + displayValue + '</div><button class="creds-copy-btn" data-target="' + id + '">Copy</button></div></div>';
  }
  return html;
}

function _attachCopyHandlers(container) {
  container.querySelectorAll(".creds-copy-btn").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var target = document.getElementById(btn.dataset.target);
      if (!target) return;
      var text = target.textContent;

      function onSuccess() {
        btn.textContent = "Copied!";
        btn.classList.add("copied");
        setTimeout(function() { btn.textContent = "Copy"; btn.classList.remove("copied"); }, 1500);
      }

      function fallbackCopy() {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        try {
          document.execCommand("copy");
          onSuccess();
        } catch (e) {}
        document.body.removeChild(ta);
      }

      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(onSuccess).catch(fallbackCopy);
      } else {
        fallbackCopy();
      }
    });
  });
}

async function openServiceDetailModal(unit, name, icon) {
  if (!$credsModal) return;
  if ($credsTitle) {
    $credsTitle.innerHTML = '';
    if (icon) {
      var iconImg = document.createElement("img");
      iconImg.className = "creds-title-icon";
      iconImg.src = "/static/icons/" + escHtml(icon) + ".svg";
      iconImg.alt = name;
      iconImg.onerror = function() { this.style.display = "none"; };
      $credsTitle.appendChild(iconImg);
    }
    var nameSpan = document.createElement("span");
    nameSpan.textContent = name;
    $credsTitle.appendChild(nameSpan);
  }
  if ($credsBody) $credsBody.innerHTML = '<p class="creds-loading">Loading…</p>';
  $credsModal.classList.add("open");

  try {
    var url = "/api/service-detail/" + encodeURIComponent(unit);
    if (icon) url += "?icon=" + encodeURIComponent(icon);
    var data = await apiFetch(url);
    var html = "";

    // Section A: Description
    if (data.description) {
      html += '<div class="svc-detail-section">' +
        '<p class="svc-detail-desc">' + escHtml(data.description) + '</p>' +
        '</div>';
    }

    // Section B: Status
    // When a feature override is present, use the feature's enabled state so the
    // modal matches what the dashboard tile shows (feature toggle is authoritative).
    var effectiveEnabled = data.feature ? data.feature.enabled : data.enabled;
    var effectiveHealth  = data.feature && !data.feature.enabled
      ? "disabled"
      : (data.health || data.status);
    var sc = statusClass(effectiveHealth);
    var st = statusText(effectiveHealth, effectiveEnabled);
    html += '<div class="svc-detail-section">' +
      '<div class="svc-detail-section-title">Status</div>' +
      '<div class="svc-detail-status">' +
        '<span class="status-dot ' + sc + '"></span>' +
        '<span>' + escHtml(st) + '</span>' +
      '</div>' +
      '</div>';

    // Section C: Domain diagnostics (domain services)
    if (data.needs_domain) {
      var steps = data.domain_check_steps || [];
      var stepsHtml = "";
      steps.forEach(function(step) {
        var iconLabel = "—";
        if (step.status === "ok") iconLabel = "✅";
        else if (step.status === "error") iconLabel = "❌";
        else if (step.status === "warning") iconLabel = "⚠️";
        else if (step.status === "skipped") iconLabel = "⏭️";
        var detail = escHtml(step.detail || "").replace(/\n/g, "<br>");
        stepsHtml += '<div class="svc-detail-troubleshoot" style="margin-bottom:10px">' +
          '<strong>' + iconLabel + ' Step ' + escHtml(String(step.step)) + ': ' + escHtml(step.label || "") + '</strong>' +
          (detail ? '<div style="margin-top:6px">' + detail + '</div>' : '') +
          '</div>';
      });

      var domainActionHtml = "";
      var ds = data.domain_status || {};
      if (!data.domain && data.domain_name) {
        domainActionHtml = '<button class="btn btn-primary svc-detail-domain-btn" id="svc-detail-config-domain-btn">🌐 Configure Domain</button>';
      } else if (data.domain && (ds.status === "dns_mismatch" || ds.status === "unresolvable")) {
        domainActionHtml = '<button class="btn btn-primary svc-detail-domain-btn" id="svc-detail-reconfig-domain-btn">🔄 Reconfigure Domain</button>';
      }

      html += '<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">Domain Diagnostic Checklist</div>' +
        stepsHtml +
        domainActionHtml +
        '</div>';

      if (unit === "livekit.service" && data.extra_ports && data.extra_ports.length > 0) {
        var extraRows = "";
        data.extra_ports.forEach(function(p) {
          var statusIcon, statusClass2;
          if (p.status === "listening") {
            statusIcon = "✅ Open";
            statusClass2 = "port-status-listening";
          } else if (p.status === "firewall_open") {
            statusIcon = "🟡 Firewall open";
            statusClass2 = "port-status-open";
          } else if (p.status === "closed") {
            statusIcon = "❌ Closed";
            statusClass2 = "port-status-closed";
          } else {
            statusIcon = "— Unknown";
            statusClass2 = "port-status-unknown";
          }
          extraRows += '<tr>' +
            '<td class="svc-detail-port-table-port">' + escHtml(p.port) + '</td>' +
            '<td class="svc-detail-port-table-proto">' + escHtml(p.protocol) + '</td>' +
            '<td class="svc-detail-port-table-desc">' + escHtml(p.description || "") + '</td>' +
            '<td class="svc-detail-port-table-status ' + statusClass2 + '">' + statusIcon + '</td>' +
            '</tr>';
        });
        html += '<div class="svc-detail-section">' +
          '<div class="svc-detail-section-title">Step 4: Additional Ports</div>' +
          '<table class="svc-detail-port-table">' +
            '<thead><tr><th>Port</th><th>Protocol</th><th>Description</th><th>Status</th></tr></thead>' +
            '<tbody>' + extraRows + '</tbody>' +
          '</table>' +
          '</div>';
      }
    } else if (data.port_statuses && data.port_statuses.length > 0) {
      // Non-domain services (SSH) keep local single-port checks.
      var portTableRows = "";
      data.port_statuses.forEach(function(p) {
        var statusIcon, statusClass2;
        if (p.status === "listening") {
          statusIcon = "✅ Open";
          statusClass2 = "port-status-listening";
        } else if (p.status === "firewall_open") {
          statusIcon = "🟡 Firewall open";
          statusClass2 = "port-status-open";
        } else if (p.status === "closed") {
          statusIcon = "🔴 Closed";
          statusClass2 = "port-status-closed";
        } else {
          statusIcon = "— Unknown";
          statusClass2 = "port-status-unknown";
        }
        portTableRows += '<tr>' +
          '<td class="svc-detail-port-table-port">' + escHtml(p.port) + '</td>' +
          '<td class="svc-detail-port-table-proto">' + escHtml(p.protocol) + '</td>' +
          '<td class="svc-detail-port-table-desc">' + escHtml(p.description || "") + '</td>' +
          '<td class="svc-detail-port-table-status ' + statusClass2 + '">' + statusIcon + '</td>' +
          '</tr>';
      });
      html += '<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">Port Status</div>' +
        '<table class="svc-detail-port-table">' +
          '<thead><tr><th>Port</th><th>Protocol</th><th>Description</th><th>Status</th></tr></thead>' +
          '<tbody>' + portTableRows + '</tbody>' +
        '</table>' +
        '</div>';
    }

    // Section E: Credentials & Links
    if (data.has_credentials && data.credentials && data.credentials.length > 0) {
      html += '<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">Credentials &amp; Access</div>' +
        _renderCredsHtml(data.credentials, unit) +
        (unit === "matrix-synapse.service" ?
          '<hr class="matrix-actions-divider"><div class="matrix-actions-row">' +
            '<button class="matrix-action-btn" id="matrix-add-user-btn">➕ Add New User</button>' +
            '<button class="matrix-action-btn" id="matrix-change-pw-btn">🔑 Change Password</button>' +
          '</div>' : "") +
        (unit === "root-password-setup.service" ?
          '<hr class="matrix-actions-divider"><div class="matrix-actions-row">' +
            '<button class="matrix-action-btn" id="sys-change-pw-btn">🔑 Change Free Account Password</button>' +
          '</div>' : "") +
        '</div>';
    } else if (!data.enabled && !data.feature) {
      html += '<div class="svc-detail-section">' +
        '<p class="creds-empty">This service is not enabled in your configuration.</p>' +
        '</div>';
    }

    // Section F: Addon Feature toggle
    if (data.feature) {
      var feat = data.feature;
      // Sync this feature into _featuresData so handleFeatureToggle can look up conflicts / ssl state
      if (!_featuresData) {
        _featuresData = { features: [feat], ssl_email_configured: false };
      } else {
        var fidx = _featuresData.features.findIndex(function(f) { return f.id === feat.id; });
        if (fidx >= 0) { _featuresData.features[fidx] = feat; }
        else { _featuresData.features.push(feat); }
      }
      var addonStatusLabel = feat.enabled ? "Enabled \u2713" : "Disabled";
      var addonStatusCls   = feat.enabled ? "addon-status--on" : "addon-status--off";
      var addonBtnLabel    = feat.enabled ? "Disable Feature" : "Enable Feature";
      var addonBtnCls      = feat.enabled ? "btn btn-close-modal" : "btn btn-primary";

      // Section title: use a more specific label for mutually-exclusive Bitcoin node features
      var addonSectionTitle = (feat.id === "bip110" || feat.id === "bitcoin-core")
        ? "\u20BF Bitcoin Node Selection"
        : "\uD83D\uDD27 Addon Feature";

      // Description: prefer the feature's own description over a generic fallback
      var addonDesc = feat.description
        ? feat.description
        : "This is an optional addon feature. You can enable or disable it at any time.";

      // Conflicts warning: list mutually-exclusive feature names when present
      var conflictsHtml = "";
      if (feat.conflicts_with && feat.conflicts_with.length > 0) {
        var conflictNames = feat.conflicts_with.map(function(cid) {
          if (_featuresData && Array.isArray(_featuresData.features)) {
            var cf = _featuresData.features.find(function(f) { return f.id === cid; });
            if (cf) return cf.name;
          }
          return cid;
        });
        conflictsHtml = '<div class="feature-conflict-warning">\u26A0 Mutually exclusive with: ' + escHtml(conflictNames.join(", ")) + '</div>';
      }

      html += '<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">' + addonSectionTitle + '</div>' +
        '<p class="svc-detail-desc">' + escHtml(addonDesc) + '</p>' +
        conflictsHtml +
        '<div class="svc-detail-addon-row">' +
          '<span class="svc-detail-addon-status ' + addonStatusCls + '">' + addonStatusLabel + '</span>' +
          '<button class="' + addonBtnCls + '" id="svc-detail-addon-btn">' + escHtml(addonBtnLabel) + '</button>' +
        '</div>' +
        '</div>';
    }

    if (effectiveEnabled || data.enabled) {
      html += '<div class="svc-detail-section svc-detail-restart-section">' +
        '<div class="svc-detail-section-title">Troubleshooting</div>' +
        '<p class="svc-detail-desc">If you\'re experiencing issues with this service, try restarting it.</p>' +
        '<button class="btn btn-warning svc-detail-restart-btn" id="svc-detail-restart-btn">🔄 Restart Service</button>' +
        '<div class="svc-detail-restart-result" id="svc-detail-restart-result"></div>' +
        '</div>';
    }

    $credsBody.innerHTML = html;
    _attachCopyHandlers($credsBody);

    if (unit === "matrix-synapse.service") {
      var addBtn = document.getElementById("matrix-add-user-btn");
      var changePwBtn = document.getElementById("matrix-change-pw-btn");
      if (addBtn) addBtn.addEventListener("click", function() { openMatrixCreateUserModal(unit, name, icon); });
      if (changePwBtn) changePwBtn.addEventListener("click", function() { openMatrixChangePasswordModal(unit, name, icon); });
    }

    if (unit === "root-password-setup.service") {
      var sysPwBtn = document.getElementById("sys-change-pw-btn");
      if (sysPwBtn) sysPwBtn.addEventListener("click", function() { openSystemChangePasswordModal(unit, name, icon); });
    }

    if (data.feature) {
      var addonBtn = document.getElementById("svc-detail-addon-btn");
      if (addonBtn) {
        var addonFeat = data.feature;
        addonBtn.addEventListener("click", function() {
          closeCredsModal();
          handleFeatureToggle(addonFeat, !addonFeat.enabled);
        });
      }
    }

    var restartBtn = document.getElementById("svc-detail-restart-btn");
    var restartResult = document.getElementById("svc-detail-restart-result");
    if (restartBtn && restartResult) {
      var RESTART_REFRESH_DELAY_MS = 3000;
      restartBtn.addEventListener("click", async function() {
        restartBtn.disabled = true;
        restartBtn.textContent = "Restarting…";
        restartResult.className = "svc-detail-restart-result";
        restartResult.textContent = "";

        try {
          await apiFetch("/api/service/" + encodeURIComponent(unit) + "/restart", { method: "POST" });
          restartResult.classList.add("success");
          restartResult.textContent = "✅ Service restarted successfully.";
          restartBtn.disabled = false;
          restartBtn.textContent = "🔄 Restart Service";
          setTimeout(function() {
            openServiceDetailModal(unit, name, icon);
          }, RESTART_REFRESH_DELAY_MS);
        } catch (e) {
          restartResult.classList.add("error");
          restartResult.textContent = e && e.message ? e.message : "Failed to restart service.";
          restartBtn.disabled = false;
          restartBtn.textContent = "🔄 Restart Service";
        }
      });
    }

    // Configure / Reconfigure Domain buttons (for non-feature services that need a domain)
    var configDomainBtn = document.getElementById("svc-detail-config-domain-btn");
    var reconfigDomainBtn = document.getElementById("svc-detail-reconfig-domain-btn");
    if ((configDomainBtn || reconfigDomainBtn) && data.needs_domain && data.domain_name) {
      var pseudoFeat = {
        id: data.domain_name,
        name: name,
        domain_name: data.domain_name,
        needs_ddns: true,
        extra_fields: []
      };
      if (configDomainBtn) configDomainBtn.addEventListener("click", function() {
        closeCredsModal();
        openDomainSetupModal(pseudoFeat, function() {
          openServiceDetailModal(unit, name, icon);
        });
      });
      if (reconfigDomainBtn) reconfigDomainBtn.addEventListener("click", function() {
        closeCredsModal();
        openDomainReconfigureModal(pseudoFeat, data.domain || "", function() {
          openServiceDetailModal(unit, name, icon);
        });
      });
    }
  } catch (err) {
    if ($credsBody) $credsBody.innerHTML = '<p class="creds-empty">Could not load service details.</p>';
  }
}

// ── Credentials info modal ────────────────────────────────────────

async function openCredsModal(unit, name, icon) {
  if (!$credsModal) return;
  if ($credsTitle) {
    $credsTitle.innerHTML = '';
    if (icon) {
      var iconImg = document.createElement("img");
      iconImg.className = "creds-title-icon";
      iconImg.src = "/static/icons/" + escHtml(icon) + ".svg";
      iconImg.alt = name;
      iconImg.onerror = function() { this.style.display = "none"; };
      $credsTitle.appendChild(iconImg);
    }
    var nameSpan = document.createElement("span");
    nameSpan.textContent = name + " — Connection Info";
    $credsTitle.appendChild(nameSpan);
  }
  if ($credsBody) $credsBody.innerHTML = '<p class="creds-loading">Loading…</p>';
  $credsModal.classList.add("open");
  try {
    var data = await apiFetch("/api/credentials/" + encodeURIComponent(unit));
    if (!data.credentials || data.credentials.length === 0) {
      $credsBody.innerHTML = '<p class="creds-empty">No connection info available yet.</p>';
      return;
    }
    var html = _renderCredsHtml(data.credentials, unit);
    if (unit === "matrix-synapse.service") {
      html += '<hr class="matrix-actions-divider"><div class="matrix-actions-row">' +
        '<button class="matrix-action-btn" id="matrix-add-user-btn">➕ Add New User</button>' +
        '<button class="matrix-action-btn" id="matrix-change-pw-btn">🔑 Change Password</button>' +
        '</div>';
    }
    $credsBody.innerHTML = html;
    _attachCopyHandlers($credsBody);
    if (unit === "matrix-synapse.service") {
      var addBtn = document.getElementById("matrix-add-user-btn");
      var changePwBtn = document.getElementById("matrix-change-pw-btn");
      if (addBtn) addBtn.addEventListener("click", function() { openMatrixCreateUserModal(unit, name); });
      if (changePwBtn) changePwBtn.addEventListener("click", function() { openMatrixChangePasswordModal(unit, name); });
    }
  } catch (err) {
    $credsBody.innerHTML = '<p class="creds-empty">Could not load credentials.</p>';
  }
}

function openMatrixCreateUserModal(unit, name, icon) {
  if (!$credsBody) return;
  $credsBody.innerHTML =
    '<div class="matrix-form-group"><label class="matrix-form-label" for="matrix-new-username">Username</label>' +
    '<input class="matrix-form-input" type="text" id="matrix-new-username" placeholder="alice" autocomplete="off"></div>' +
    '<div class="matrix-form-group"><label class="matrix-form-label" for="matrix-new-password">Password</label>' +
    '<input class="matrix-form-input" type="password" id="matrix-new-password" placeholder="Strong password" autocomplete="new-password"></div>' +
    '<div class="matrix-form-checkbox-row"><input type="checkbox" id="matrix-new-admin"><label class="matrix-form-label" for="matrix-new-admin" style="margin:0">Make admin</label></div>' +
    '<div class="matrix-form-actions">' +
    '<button class="matrix-form-back" id="matrix-create-back-btn">← Back</button>' +
    '<button class="matrix-form-submit" id="matrix-create-submit-btn">Create User</button>' +
    '</div>' +
    '<div class="matrix-form-result" id="matrix-create-result"></div>';

  document.getElementById("matrix-create-back-btn").addEventListener("click", function() {
    openServiceDetailModal(unit, name, icon);
  });

  document.getElementById("matrix-create-submit-btn").addEventListener("click", async function() {
    var submitBtn = document.getElementById("matrix-create-submit-btn");
    var resultEl = document.getElementById("matrix-create-result");
    var username = (document.getElementById("matrix-new-username").value || "").trim();
    var password = document.getElementById("matrix-new-password").value || "";
    var isAdmin = document.getElementById("matrix-new-admin").checked;

    if (!username || !password) {
      resultEl.className = "matrix-form-result error";
      resultEl.textContent = "Username and password are required.";
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Creating…";
    resultEl.className = "matrix-form-result";
    resultEl.textContent = "";

    try {
      var resp = await apiFetch("/api/matrix/create-user", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username, password: password, admin: isAdmin })
      });
      resultEl.className = "matrix-form-result success";
      resultEl.textContent = "✅ User @" + escHtml(resp.username) + " created successfully.";
      submitBtn.textContent = "Create User";
      submitBtn.disabled = false;
    } catch (err) {
      resultEl.className = "matrix-form-result error";
      resultEl.textContent = "❌ " + (err.message || "Failed to create user.");
      submitBtn.textContent = "Create User";
      submitBtn.disabled = false;
    }
  });
}

function openMatrixChangePasswordModal(unit, name, icon) {
  if (!$credsBody) return;
  $credsBody.innerHTML =
    '<div class="matrix-form-group"><label class="matrix-form-label" for="matrix-chpw-username">Username (localpart only, e.g. <em>alice</em>)</label>' +
    '<input class="matrix-form-input" type="text" id="matrix-chpw-username" placeholder="alice" autocomplete="off"></div>' +
    '<div class="matrix-form-group"><label class="matrix-form-label" for="matrix-chpw-password">New Password</label>' +
    '<input class="matrix-form-input" type="password" id="matrix-chpw-password" placeholder="New strong password" autocomplete="new-password"></div>' +
    '<div class="matrix-form-actions">' +
    '<button class="matrix-form-back" id="matrix-chpw-back-btn">← Back</button>' +
    '<button class="matrix-form-submit" id="matrix-chpw-submit-btn">Change Password</button>' +
    '</div>' +
    '<div class="matrix-form-result" id="matrix-chpw-result"></div>';

  document.getElementById("matrix-chpw-back-btn").addEventListener("click", function() {
    openServiceDetailModal(unit, name, icon);
  });

  document.getElementById("matrix-chpw-submit-btn").addEventListener("click", async function() {
    var submitBtn = document.getElementById("matrix-chpw-submit-btn");
    var resultEl = document.getElementById("matrix-chpw-result");
    var username = (document.getElementById("matrix-chpw-username").value || "").trim();
    var newPassword = document.getElementById("matrix-chpw-password").value || "";

    if (!username || !newPassword) {
      resultEl.className = "matrix-form-result error";
      resultEl.textContent = "Username and new password are required.";
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Changing…";
    resultEl.className = "matrix-form-result";
    resultEl.textContent = "";

    try {
      var resp = await apiFetch("/api/matrix/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username, new_password: newPassword })
      });
      resultEl.className = "matrix-form-result success";
      resultEl.textContent = "✅ Password for @" + escHtml(resp.username) + " changed successfully.";
      submitBtn.textContent = "Change Password";
      submitBtn.disabled = false;
    } catch (err) {
      resultEl.className = "matrix-form-result error";
      resultEl.textContent = "❌ " + (err.message || "Failed to change password.");
      submitBtn.textContent = "Change Password";
      submitBtn.disabled = false;
    }
  });
}

function openSystemChangePasswordModal(unit, name, icon) {
  if (!$credsBody) return;
  $credsBody.innerHTML =
    '<div class="sys-chpw-header">' +
      '<div class="sys-chpw-title">🔑 Change Free Account &amp; Hub Login Password</div>' +
      '<div class="sys-chpw-desc">This updates the password for the <strong>free</strong> user account. <strong>This is also your Sovran Hub login password</strong> — both will change.</div>' +
    '</div>' +
    '<div class="matrix-form-group"><label class="matrix-form-label" for="sys-chpw-new">New Password</label>' +
    '<div class="pw-input-wrap">' +
    '<input class="matrix-form-input" type="password" id="sys-chpw-new" placeholder="New strong password" autocomplete="new-password">' +
    '<button type="button" class="pw-toggle-btn" id="sys-chpw-new-toggle" aria-label="Toggle password visibility">👁</button>' +
    '</div>' +
    '<div class="pw-hint">Password must be at least 8 characters.</div></div>' +
    '<div class="matrix-form-group"><label class="matrix-form-label" for="sys-chpw-confirm">Confirm Password</label>' +
    '<div class="pw-input-wrap">' +
    '<input class="matrix-form-input" type="password" id="sys-chpw-confirm" placeholder="Confirm new password" autocomplete="new-password">' +
    '<button type="button" class="pw-toggle-btn" id="sys-chpw-confirm-toggle" aria-label="Toggle password visibility">👁</button>' +
    '</div></div>' +
    '<div class="pw-credentials-note">⚠ This will change both your desktop login and Hub login password. After changing, your updated password will appear in the System Passwords credentials tile. Make sure to remember it — you will need it to sign back into the Hub.</div>' +
    '<div class="matrix-form-actions">' +
    '<button class="matrix-form-back" id="sys-chpw-back-btn">← Back</button>' +
    '<button class="matrix-form-submit" id="sys-chpw-submit-btn">Change Password</button>' +
    '</div>' +
    '<div class="matrix-form-result" id="sys-chpw-result"></div>';

  document.getElementById("sys-chpw-back-btn").addEventListener("click", function() {
    openServiceDetailModal(unit, name, icon);
  });

  document.getElementById("sys-chpw-new-toggle").addEventListener("click", function() {
    var inp = document.getElementById("sys-chpw-new");
    var isHidden = inp.type === "password";
    inp.type = isHidden ? "text" : "password";
    this.textContent = isHidden ? "👁‍🗨" : "👁";
  });

  document.getElementById("sys-chpw-confirm-toggle").addEventListener("click", function() {
    var inp = document.getElementById("sys-chpw-confirm");
    var isHidden = inp.type === "password";
    inp.type = isHidden ? "text" : "password";
    this.textContent = isHidden ? "👁‍🗨" : "👁";
  });

  document.getElementById("sys-chpw-submit-btn").addEventListener("click", async function() {
    var submitBtn = document.getElementById("sys-chpw-submit-btn");
    var resultEl = document.getElementById("sys-chpw-result");
    var newPassword = document.getElementById("sys-chpw-new").value || "";
    var confirmPassword = document.getElementById("sys-chpw-confirm").value || "";

    if (!newPassword || !confirmPassword) {
      resultEl.className = "matrix-form-result error";
      resultEl.textContent = "Both password fields are required.";
      return;
    }

    if (newPassword.length < 8) {
      resultEl.className = "matrix-form-result error";
      resultEl.textContent = "Password must be at least 8 characters.";
      return;
    }

    if (newPassword !== confirmPassword) {
      resultEl.className = "matrix-form-result error";
      resultEl.textContent = "Passwords do not match.";
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Changing…";
    resultEl.className = "matrix-form-result";
    resultEl.textContent = "";

    try {
      await apiFetch("/api/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: newPassword, confirm_password: confirmPassword })
      });
      resultEl.className = "matrix-form-result success";
      resultEl.textContent = "✅ Free account & Hub login password changed successfully.";
      submitBtn.textContent = "Change Password";
      submitBtn.disabled = false;
    } catch (err) {
      resultEl.className = "matrix-form-result error";
      resultEl.textContent = "❌ " + (err.message || "Failed to change password.");
      submitBtn.textContent = "Change Password";
      submitBtn.disabled = false;
    }
  });
}

function closeCredsModal() { if ($credsModal) $credsModal.classList.remove("open"); }
