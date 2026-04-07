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

    // Section: Desktop Launch (only for services with desktop apps)
    if (data.desktop_links && data.desktop_links.length > 0) {
      var launchBtns = '';
      data.desktop_links.forEach(function(link) {
        launchBtns += '<button class="btn btn-primary svc-detail-launch-btn" data-desktop="' + escHtml(link.desktop_file) + '">' +
          '🖥️ ' + escHtml(link.label) +
          '</button>';
      });
      html += '<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">Open on Desktop</div>' +
        '<p class="svc-detail-desc" style="margin-bottom:12px">If you are accessing this machine locally on the GNOME desktop, click below to launch the app directly.</p>' +
        '<div class="svc-detail-launch-row">' + launchBtns + '</div>' +
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

    // Section C: Ports (only if service has port_requirements)
    if (data.port_statuses && data.port_statuses.length > 0) {
      var anyPortClosed = data.port_statuses.some(function(p) { return p.status === "closed"; });
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
        var desc = p.description;
        var portNum = parseInt(p.port, 10);
        if (portNum === 80 || portNum === 443) {
          desc += " (shared — all services)";
        }
        portTableRows += '<tr>' +
          '<td class="svc-detail-port-table-port">' + escHtml(p.port) + '</td>' +
          '<td class="svc-detail-port-table-proto">' + escHtml(p.protocol) + '</td>' +
          '<td class="svc-detail-port-table-desc">' + escHtml(desc) + '</td>' +
          '<td class="svc-detail-port-table-status ' + statusClass2 + '">' + statusIcon + '</td>' +
          '</tr>';
      });

      var troubleshootHtml = "";
      if (anyPortClosed) {
        var sharedPorts = [];
        var specificPorts = [];
        data.port_statuses.forEach(function(p) {
          if (p.status === "closed") {
            var portNum = parseInt(p.port, 10);
            if (portNum === 80 || portNum === 443) {
              sharedPorts.push(p);
            } else {
              specificPorts.push(p);
            }
          }
        });

        var troubleParts = [];

        if (sharedPorts.length > 0) {
          troubleParts.push(
            '<strong>⚠️ Ports 80 and 443 need to be forwarded on your router.</strong>' +
            '<p style="margin-top:8px">These are <strong>shared system ports</strong> — you only need to set them up once and they cover all your domain-based services ' +
            '(BTCPayServer, Nextcloud, Matrix, WordPress, etc.).</p>' +
            '<p style="margin-top:8px">If you already forwarded these ports during onboarding, you don\'t need to do it again. Otherwise:</p>' +
            '<ol>' +
              '<li>Log into your router\'s admin panel (usually <code>http://192.168.1.1</code>)</li>' +
              '<li>Find the <strong>Port Forwarding</strong> section</li>' +
              '<li>Forward port <strong>80 (TCP)</strong> and port <strong>443 (TCP)</strong> to your machine\'s internal IP: <code>' + escHtml(data.internal_ip || "—") + '</code></li>' +
              '<li>Save your router settings</li>' +
            '</ol>' +
            '<p style="margin-top:8px">💡 Once these two ports are forwarded, you won\'t see this warning on any service again.</p>'
          );
        }

        if (specificPorts.length > 0) {
          var portList = specificPorts.map(function(p) {
            return '<strong>' + escHtml(p.port) + ' (' + escHtml(p.protocol) + ')</strong> — ' + escHtml(p.description);
          }).join('<br>');

          troubleParts.push(
            '<strong>⚠️ This service requires additional ports to be forwarded:</strong>' +
            '<p style="margin-top:8px">' + portList + '</p>' +
            '<ol>' +
              '<li>Log into your router\'s admin panel</li>' +
              '<li>Forward each port listed above to your machine\'s internal IP: <code>' + escHtml(data.internal_ip || "—") + '</code></li>' +
              '<li>Save your router settings</li>' +
            '</ol>'
          );
        }

        troubleshootHtml = '<div class="svc-detail-troubleshoot">' + troubleParts.join('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.1);margin:16px 0">') + '</div>';
      }

      html += '<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">Port Status</div>' +
        '<table class="svc-detail-port-table">' +
          '<thead><tr>' +
            '<th>Port</th><th>Protocol</th><th>Description</th><th>Status</th>' +
          '</tr></thead>' +
          '<tbody>' + portTableRows + '</tbody>' +
        '</table>' +
        troubleshootHtml +
        '</div>';
    }

    // Section D: Domain (only if service needs_domain)
    if (data.needs_domain) {
      var domainStatusHtml = "";
      var ds = data.domain_status || {};
      var domainBadge = "";

      if (data.domain) {
        if (ds.status === "connected") {
          domainBadge = '<span class="svc-detail-domain-value"><span class="tile-domain-label--ok">✓ ' + escHtml(data.domain) + '</span></span>';
        } else if (ds.status === "dns_mismatch") {
          domainBadge = '<span class="svc-detail-domain-value"><span class="tile-domain-label--warn">⚠ ' + escHtml(data.domain) + ' (IP mismatch)</span></span>';
          domainStatusHtml = '<div class="svc-detail-troubleshoot">' +
            '<strong>⚠️ Your domain resolves to ' + escHtml(ds.resolved_ip || "unknown") + ' but your external IP is ' + escHtml(ds.expected_ip || "unknown") + '.</strong>' +
            '<p style="margin-top:8px">This usually means the DNS record needs to be updated:</p>' +
            '<ol>' +
              '<li>Go to <a href="https://njal.la" target="_blank">njal.la</a> and log into your account</li>' +
              '<li>Find your domain and check the Dynamic DNS record</li>' +
              '<li>Make sure it points to your current external IP: <code>' + escHtml(ds.expected_ip || "—") + '</code></li>' +
              '<li>If you set up a DDNS curl command during onboarding, verify it\'s running correctly</li>' +
            '</ol>' +
            '</div>';
        } else if (ds.status === "unresolvable") {
          domainBadge = '<span class="svc-detail-domain-value"><span class="tile-domain-label--error">✗ ' + escHtml(data.domain) + ' (DNS error)</span></span>';
          domainStatusHtml = '<div class="svc-detail-troubleshoot">' +
            '<strong>⚠️ This domain cannot be resolved. DNS is not configured yet.</strong>' +
            '<p style="margin-top:8px">Let\'s get it set up:</p>' +
            '<ol>' +
              '<li>Go to <a href="https://njal.la" target="_blank">njal.la</a> and log into your account</li>' +
              '<li>Find the domain you purchased for this service</li>' +
              '<li>Create a Dynamic DNS record pointing to your external IP: <code>' + escHtml(ds.expected_ip || "—") + '</code></li>' +
              '<li>Copy the DDNS curl command from Njal.la\'s dashboard</li>' +
              '<li>You can re-enter it in the Feature Manager to update your configuration</li>' +
            '</ol>' +
            '</div>';
        } else {
          domainBadge = '<span class="svc-detail-domain-value">' + escHtml(data.domain) + '</span>';
        }
      } else {
        domainBadge = '<span class="svc-detail-domain-value"><span class="tile-domain-label--warn">Not configured</span></span>';
        domainStatusHtml = '<div class="svc-detail-troubleshoot">' +
          '<strong>⚠️ No domain has been configured for this service yet.</strong>' +
          '<p style="margin-top:8px">To get this service working:</p>' +
          '<ol>' +
            '<li>Purchase a subdomain at <a href="https://njal.la" target="_blank">njal.la</a> (if you haven\'t already)</li>' +
            '<li>Go to the <strong>Feature Manager</strong> in the sidebar</li>' +
            '<li>Find this service and configure your domain through the setup wizard</li>' +
          '</ol>' +
          '</div>';
      }

      html += '<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">Domain</div>' +
        domainBadge +
        domainStatusHtml +
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
            '<button class="matrix-action-btn" id="sys-change-pw-btn">🔑 Change Password</button>' +
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

    $credsBody.innerHTML = html;
    _attachCopyHandlers($credsBody);

    // Desktop launch button handlers
    $credsBody.querySelectorAll(".svc-detail-launch-btn").forEach(function(btn) {
      btn.addEventListener("click", async function() {
        var desktopFile = btn.dataset.desktop;
        btn.disabled = true;
        btn.textContent = "Launching…";
        try {
          await apiFetch("/api/desktop/launch/" + encodeURIComponent(desktopFile), {
            method: "POST"
          });
          btn.textContent = "✓ Launched!";
          setTimeout(function() { btn.textContent = "🖥️ " + btn.textContent; btn.disabled = false; }, 2000);
        } catch (err) {
          btn.textContent = "❌ Failed";
          btn.disabled = false;
        }
      });
    });

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
    '<div class="matrix-form-group"><label class="matrix-form-label" for="sys-chpw-new">New Password</label>' +
    '<input class="matrix-form-input" type="password" id="sys-chpw-new" placeholder="New strong password" autocomplete="new-password"></div>' +
    '<div class="matrix-form-group"><label class="matrix-form-label" for="sys-chpw-confirm">Confirm Password</label>' +
    '<input class="matrix-form-input" type="password" id="sys-chpw-confirm" placeholder="Confirm new password" autocomplete="new-password"></div>' +
    '<div class="matrix-form-actions">' +
    '<button class="matrix-form-back" id="sys-chpw-back-btn">← Back</button>' +
    '<button class="matrix-form-submit" id="sys-chpw-submit-btn">Change Password</button>' +
    '</div>' +
    '<div class="matrix-form-result" id="sys-chpw-result"></div>';

  document.getElementById("sys-chpw-back-btn").addEventListener("click", function() {
    openServiceDetailModal(unit, name, icon);
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
      resultEl.textContent = "✅ System password changed successfully.";
      submitBtn.textContent = "Change Password";
      submitBtn.disabled = false;
      // Hide the legacy security banner if it's visible
      if (typeof _securityIsLegacy !== "undefined" && _securityIsLegacy) {
        _securityIsLegacy = false;
        var banner = document.querySelector(".security-inline-banner");
        if (banner) banner.remove();
      }
    } catch (err) {
      resultEl.className = "matrix-form-result error";
      resultEl.textContent = "❌ " + (err.message || "Failed to change password.");
      submitBtn.textContent = "Change Password";
      submitBtn.disabled = false;
    }
  });
}

function closeCredsModal() { if ($credsModal) $credsModal.classList.remove("open"); }
