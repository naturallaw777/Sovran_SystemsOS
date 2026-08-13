"use strict";

// ── Feature confirm modal ─────────────────────────────────────────

function openFeatureConfirm(message, onConfirm) {
  if (!$featureConfirmModal) return;
  if ($featureConfirmMsg) $featureConfirmMsg.textContent = message;
  $featureConfirmModal.classList.add("open");
  // Replace ok handler
  var newOk = $featureConfirmOk.cloneNode(true);
  $featureConfirmOk.parentNode.replaceChild(newOk, $featureConfirmOk);
  newOk.addEventListener("click", function() {
    closeFeatureConfirm();
    onConfirm();
  });
}

function closeFeatureConfirm() {
  if ($featureConfirmModal) $featureConfirmModal.classList.remove("open");
}

// ── SSL Email modal ───────────────────────────────────────────────

function openSslEmailModal(onSaved) {
  if (!$sslEmailModal) return;
  if ($sslEmailInput) $sslEmailInput.value = "";
  $sslEmailModal.classList.add("open");
  // Replace save handler
  var newSave = $sslEmailSave.cloneNode(true);
  $sslEmailSave.parentNode.replaceChild(newSave, $sslEmailSave);
  newSave.addEventListener("click", async function() {
    var email = $sslEmailInput ? $sslEmailInput.value.trim() : "";
    if (!email) { alert("Please enter an email address."); return; }
    newSave.disabled = true;
    newSave.textContent = "Saving…";
    try {
      await apiFetch("/api/domains/set-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email }),
      });
      closeSslEmailModal();
      onSaved();
    } catch (err) {
      newSave.disabled = false;
      newSave.textContent = "Save";
      alert("Failed to save email. Please try again.");
    }
  });
}

function closeSslEmailModal() {
  if ($sslEmailModal) $sslEmailModal.classList.remove("open");
}

// ── Domain Setup modal ────────────────────────────────────────────

function openDomainSetupModal(feat, onSaved) {
  if (!$domainSetupModal) return;
  if ($domainSetupTitle) $domainSetupTitle.textContent = "🌐 Domain Setup — " + feat.name;

  var isWalletConnections = (feat.id === "nwc-wallets" || feat.domain_name === "lightning");

  var npubField = "";
  if (feat.id === "haven") {
    var currentNpub = "";
    if (feat.extra_fields && feat.extra_fields.length > 0) {
      for (var i = 0; i < feat.extra_fields.length; i++) {
        if (feat.extra_fields[i].id === "nostr_npub") {
          currentNpub = feat.extra_fields[i].current_value || "";
          break;
        }
      }
    }
    npubField = '<div class="domain-field-group"><label class="domain-field-label" for="domain-npub-input">Nostr Public Key (npub1...):</label><input class="domain-field-input" type="text" id="domain-npub-input" placeholder="npub1..." value="' + escHtml(currentNpub) + '" /></div>';
  }

  var nwcWarning = isWalletConnections
    ? '<div class="domain-nwc-warning">' +
      '<strong>⚠ Lightning Wallet Connections requires its own unique hostname.</strong> ' +
      'Use a new subdomain such as <code>lightning.yourdomain.com</code>, or a separate domain. ' +
      'Do not reuse a domain already assigned to Matrix, Nextcloud, WordPress, BTCPay Server, Vaultwarden, Haven, or another Caddy site.' +
      '</div>'
    : '';

  var domainPlaceholder = isWalletConnections ? "lightning.yourdomain.com" : "myservice.example.com";
  var domainLabelExample = isWalletConnections ? "lightning.yourdomain.com" : "call.yourdomain.com";

  // Shared instructions (single source of truth: static/js/domain-prereqs.js) —
  // identical wording to the Server + Desktop onboarding wizard and every other
  // domain-based feature, regardless of role (Node / Desktop / Server+Desktop).
  var hostExample = isWalletConnections ? "lightning" : "call";

  $domainSetupBody.innerHTML =
    '<div class="domain-setup-intro">' +
    nwcWarning +
    renderDomainNeedsHtml({ serviceName: feat.name, hostExample: hostExample }) +
    renderNjallaStepsHtml({ hostExample: hostExample, pasteHint: "below" }) +
    '<div class="onboarding-port-warn" id="domain-router-box" style="margin-top:12px;"></div>' +
    '<p style="margin-top:10px;">Below, enter the full domain for this service — a subdomain (e.g. ' + domainLabelExample + ') or a separate domain — and paste its curl command.</p>' +
    '</div>' +
    '<div class="domain-field-group"><label class="domain-field-label" for="domain-subdomain-input">Service domain (e.g. ' + domainLabelExample + '):</label><input class="domain-field-input" type="text" id="domain-subdomain-input" placeholder="' + domainPlaceholder + '" /></div>' +
    '<div class="domain-field-group"><label class="domain-field-label" for="domain-ddns-input">Njal.la Dynamic DNS Update Command:</label><input class="domain-field-input" type="text" id="domain-ddns-input" placeholder="curl &quot;https://njal.la/update/?h=' + domainPlaceholder + '&amp;k=abc123&amp;auto&quot;" /><p class="domain-field-hint">ℹ Paste the full curl command from your Njal.la dashboard\'s Dynamic record</p></div>' +
    npubField +
    '<div class="domain-field-actions"><button class="btn btn-close-modal" id="domain-setup-cancel-btn">Cancel</button><button class="btn btn-primary" id="domain-setup-save-btn">Save &amp; Enable</button></div>';

  document.getElementById("domain-setup-cancel-btn").addEventListener("click", closeDomainSetupModal);

  document.getElementById("domain-setup-save-btn").addEventListener("click", async function() {
    var subdomain = (document.getElementById("domain-subdomain-input") || {}).value || "";
    var ddnsUrl   = (document.getElementById("domain-ddns-input")     || {}).value || "";
    var npub      = document.getElementById("domain-npub-input") ? (document.getElementById("domain-npub-input").value || "") : "";
    subdomain = subdomain.trim();
    ddnsUrl   = ddnsUrl.trim();
    npub      = npub.trim();

    if (!subdomain) { alert("Please enter a domain."); return; }
    if (feat.id === "haven" && !npub) { alert("Please enter your Nostr public key."); return; }

    var saveBtn = document.getElementById("domain-setup-save-btn");
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving…";

    try {
      await apiFetch("/api/domains/set", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain_name: feat.domain_name,
          domain: subdomain,
          ddns_url: ddnsUrl,
        }),
      });
      closeDomainSetupModal();
      onSaved(npub);
    } catch (err) {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save & Enable";
      var msg = (err && err.message) ? err.message : "Failed to save domain. Please try again.";
      alert(msg);
    }
  });

  $domainSetupModal.classList.add("open");

  // Fill the router port-forwarding box with this computer's LAN IP (best-effort)
  renderRouterPortsBox("domain-router-box");
}

function openDomainReconfigureModal(feat, existingDomain, onSaved) {
  if (!$domainSetupModal) return;
  if ($domainSetupTitle) $domainSetupTitle.textContent = "🔄 Reconfigure Domain — " + feat.name;

  var isWalletConnections = (feat.id === "nwc-wallets" || feat.domain_name === "lightning");

  var npubField = "";
  if (feat.id === "haven") {
    var currentNpub = "";
    if (feat.extra_fields && feat.extra_fields.length > 0) {
      for (var i = 0; i < feat.extra_fields.length; i++) {
        if (feat.extra_fields[i].id === "nostr_npub") {
          currentNpub = feat.extra_fields[i].current_value || "";
          break;
        }
      }
    }
    npubField = '<div class="domain-field-group"><label class="domain-field-label" for="domain-npub-input">Nostr Public Key (npub1...):</label><input class="domain-field-input" type="text" id="domain-npub-input" placeholder="npub1..." value="' + escHtml(currentNpub) + '" /></div>';
  }

  var nwcWarning = isWalletConnections
    ? '<div class="domain-nwc-warning">' +
      '<strong>⚠ Lightning Wallet Connections requires its own unique hostname.</strong> ' +
      'Use a new subdomain such as <code>lightning.yourdomain.com</code>, or a separate domain. ' +
      'Do not reuse a domain already assigned to Matrix, Nextcloud, WordPress, BTCPay Server, Vaultwarden, Haven, or another Caddy site.' +
      '</div>'
    : '';

  var domainPlaceholder = isWalletConnections ? "lightning.yourdomain.com" : "myservice.example.com";
  var domainLabelExample = isWalletConnections ? "lightning.yourdomain.com" : "call.yourdomain.com";

  var externalIp = _cachedExternalIp || "your external IP";
  var currentDomain = existingDomain || "";

  $domainSetupBody.innerHTML =
    '<div class="domain-setup-intro">' +
    nwcWarning +
    '<p>Your domain <strong>' + escHtml(currentDomain || "this domain") + '</strong> is configured but isn\'t resolving correctly.</p>' +
    '<p><strong>Troubleshooting steps:</strong></p>' +
    '<ol>' +
    '<li>Log into your Njal.la dashboard at <a href="https://njal.la" target="_blank" rel="noopener noreferrer" style="color:var(--accent-color);">https://njal.la</a></li>' +
    '<li>Find the DNS record for <strong>' + escHtml(currentDomain || "your domain") + '</strong>. In Njal.la\'s Name field, note that only the host part is stored (the word before the domain) — not the full domain.</li>' +
    '<li>Verify it has a <strong>Dynamic</strong> record pointing to your current external IP:<br>' +
    '<span style="display:inline-block;margin-top:4px;padding:4px 10px;background:var(--card-color);border:1px solid var(--border-color);border-radius:6px;font-family:monospace;font-size:1em;font-weight:700;">' + escHtml(externalIp) + '</span></li>' +
    '<li>If the IP is wrong or the record is missing, update it</li>' +
    '<li>If you changed the DDNS curl command, paste the updated one below</li>' +
    '<li>Confirm ports <strong>80</strong> and <strong>443</strong> (TCP) are still forwarded on your router to this computer — see the reminder below:</li>' +
    '</ol>' +
    '<div class="onboarding-port-warn" id="domain-router-box" style="margin-top:12px;"></div>' +
    '</div>' +
    '<div class="domain-field-group"><label class="domain-field-label" for="domain-subdomain-input">Service domain (e.g. ' + domainLabelExample + '):</label><input class="domain-field-input" type="text" id="domain-subdomain-input" placeholder="' + domainPlaceholder + '" value="' + escHtml(currentDomain) + '" /></div>' +
    '<div class="domain-field-group"><label class="domain-field-label" for="domain-ddns-input">Njal.la Dynamic DNS Update Command:</label><input class="domain-field-input" type="text" id="domain-ddns-input" placeholder="curl &quot;https://njal.la/update/?h=' + domainPlaceholder + '&amp;k=abc123&amp;auto&quot;" /><p class="domain-field-hint">ℹ Paste the full curl command from your Njal.la dashboard\'s Dynamic record</p></div>' +
    npubField +
    '<div class="domain-field-actions"><button class="btn btn-close-modal" id="domain-setup-cancel-btn">Cancel</button><button class="btn btn-primary" id="domain-setup-save-btn">Save &amp; Update</button></div>';

  document.getElementById("domain-setup-cancel-btn").addEventListener("click", closeDomainSetupModal);

  document.getElementById("domain-setup-save-btn").addEventListener("click", async function() {
    var subdomain = (document.getElementById("domain-subdomain-input") || {}).value || "";
    var ddnsUrl   = (document.getElementById("domain-ddns-input")     || {}).value || "";
    var npub      = document.getElementById("domain-npub-input") ? (document.getElementById("domain-npub-input").value || "") : "";
    subdomain = subdomain.trim();
    ddnsUrl   = ddnsUrl.trim();
    npub      = npub.trim();

    if (!subdomain) { alert("Please enter a subdomain."); return; }
    if (feat.id === "haven" && !npub) { alert("Please enter your Nostr public key."); return; }

    var saveBtn = document.getElementById("domain-setup-save-btn");
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving…";

    try {
      await apiFetch("/api/domains/set", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain_name: feat.domain_name,
          domain: subdomain,
          ddns_url: ddnsUrl,
        }),
      });
      closeDomainSetupModal();
      onSaved(npub);
    } catch (err) {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save & Update";
      var msg = (err && err.message) ? err.message : "Failed to save domain. Please try again.";
      alert(msg);
    }
  });

  $domainSetupModal.classList.add("open");

  // Fill the router port-forwarding box with this computer's LAN IP (best-effort)
  renderRouterPortsBox("domain-router-box");
}

function closeDomainSetupModal() {
  if ($domainSetupModal) $domainSetupModal.classList.remove("open");
}

// ── Port Requirements modal ───────────────────────────────────────

function openPortRequirementsModal(featureName, ports, onContinue) {
  if (!$portReqModal || !$portReqBody) return;

  var continueBtn = onContinue
    ? '<button class="btn btn-primary" id="port-req-continue-btn">I Understand — Continue</button>'
    : '';

  function renderPortRequirements(internalIp) {
    $portReqBody.innerHTML =
      renderPortForwardGuideHtml(ports, {
        internalIp: internalIp,
        serviceName: featureName,
      }) +
      '<p class="port-req-hint">💡 This list is always available again on the <strong>' + escHtml(featureName) + '</strong> tile.</p>' +
      '<div class="domain-field-actions">' +
      '<button class="btn btn-close-modal" id="port-req-dismiss-btn">Dismiss</button>' +
      continueBtn +
      '</div>';

    document.getElementById("port-req-dismiss-btn").onclick = function() {
      closePortRequirementsModal();
    };

    if (onContinue) {
      document.getElementById("port-req-continue-btn").onclick = function() {
        closePortRequirementsModal();
        onContinue();
      };
    }
  }

  $portReqModal.classList.add("open");
  renderPortRequirements(null);

  fetch("/api/network")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!$portReqModal.classList.contains("open")) return;
      var internalIp = (data.internal_ip && data.internal_ip !== "unavailable")
        ? data.internal_ip : null;
      renderPortRequirements(internalIp);
    })
    .catch(function(err) {
      console.warn("Failed to fetch network info for port requirements modal:", err);
    });
}

function closePortRequirementsModal() {
  if ($portReqModal) $portReqModal.classList.remove("open");
}

if ($portReqClose) {
  $portReqClose.addEventListener("click", closePortRequirementsModal);
}

// ── Feature toggle logic ──────────────────────────────────────────

async function performFeatureToggle(featId, enabled, extra) {
  // Look up feature name for the rebuild modal
  _rebuildIsEnabling = enabled;
  _rebuildFeatureName = featId;
  if (_featuresData) {
    var found = _featuresData.features.find(function(f) { return f.id === featId; });
    if (found) _rebuildFeatureName = found.name;
  }
  try {
    var res = await fetch("/api/features/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature: featId, enabled: enabled, extra: extra || {} }),
    });
    var body = await res.json();
    if (!res.ok) {
      if (body && body.error === "domain_required") {
        alert("Domain not configured for this feature. Please configure it first.");
      } else {
        alert("Error: " + (body.detail || body.error || "Unknown error"));
      }
      loadFeatureManager();
      return;
    }
    openRebuildModal();
  } catch (err) {
    alert("Failed to toggle feature: " + err);
    loadFeatureManager();
  }
}

function handleFeatureToggle(feat, newEnabled) {
  if (!newEnabled) {
    // Disable: ask confirmation
    openFeatureConfirm(
      "This will disable " + feat.name + ". The system will rebuild. Continue?",
      function() { performFeatureToggle(feat.id, false, {}); }
    );
    return;
  }

  // Enabling
  var conflictNames = [];
  if (feat.conflicts_with && feat.conflicts_with.length > 0 && _featuresData) {
    feat.conflicts_with.forEach(function(cid) {
      var cf = _featuresData.features.find(function(f) { return f.id === cid; });
      if (cf && cf.enabled) conflictNames.push(cf.name);
    });
  }

  function proceedAfterPortCheck() {
    // Check SSL email first
    if (!_featuresData || !_featuresData.ssl_email_configured) {
      if (feat.needs_domain) {
        openSslEmailModal(function() {
          // After ssl email saved, check domain
          checkDomainAndEnable(feat, {});
        });
        return;
      }
    }
    if (feat.needs_domain && !feat.domain_configured) {
      checkDomainAndEnable(feat, {});
      return;
    }
    if (feat.id === "haven") {
      var npub = "";
      if (feat.extra_fields) {
        var ef = feat.extra_fields.find(function(e) { return e.id === "nostr_npub"; });
        if (ef) npub = ef.current_value || "";
      }
      if (!npub) {
        // Need to collect npub via domain modal
        openDomainSetupModal(feat, function(collectedNpub) {
          performFeatureToggle(feat.id, true, { nostr_npub: collectedNpub });
        });
        return;
      }
    }
    performFeatureToggle(feat.id, true, {});
  }

  function proceedAfterConflictCheck() {
    var ports = feat.port_requirements || [];
    if (ports.length === 0) {
      proceedAfterPortCheck();
      return;
    }

    // Always show the full list of ports to forward. Port forwarding happens on
    // the router, which this computer cannot inspect — a local check would only
    // hide ports the user still has to open.
    openPortRequirementsModal(feat.name, ports, proceedAfterPortCheck);
  }

  if (conflictNames.length > 0) {
    openFeatureConfirm("This will disable " + conflictNames.join(", ") + ". Continue?", proceedAfterConflictCheck);
  } else {
    proceedAfterConflictCheck();
  }
}

function checkDomainAndEnable(feat, extra) {
  openDomainSetupModal(feat, function(collectedNpub) {
    var extraData = {};
    if (collectedNpub) extraData.nostr_npub = collectedNpub;
    performFeatureToggle(feat.id, true, extraData);
  });
}

// ── Feature Manager rendering ─────────────────────────────────────

async function loadFeatureManager() {
  try {
    var data = await apiFetch("/api/features");
    _featuresData = data;
    // Feature Manager is now integrated into tile modals; sidebar rendering removed.
  } catch (err) {
    console.warn("Failed to load features:", err);
  }
}

function _checkFeatureManagerDomains(data) {
  // Collect all features with a configured domain
  var featsWithDomain = (data.features || []).filter(function(f) {
    return f.needs_domain && f.domain_configured;
  });
  if (!featsWithDomain.length) return;

  // Get the actual domain values from /api/domains/status, then check them
  fetch("/api/domains/status")
    .then(function(r) { return r.json(); })
    .then(function(statusData) {
      var domainFileMap = statusData.domains || {};
      // Build list of domains to check and a map from domain value → feature id
      var domainsToCheck = [];
      var domainToFeatIds = {};
      featsWithDomain.forEach(function(feat) {
        var domainName = feat.domain_name;
        var domainVal = domainName ? domainFileMap[domainName] : null;
        if (domainVal) {
          domainsToCheck.push(domainVal);
          if (!domainToFeatIds[domainVal]) domainToFeatIds[domainVal] = [];
          domainToFeatIds[domainVal].push(feat.id);
        } else {
          // Domain file missing — update badge to warn
          _updateFeatureDomainBadge(feat.id, null, "unresolvable");
        }
      });

      if (!domainsToCheck.length) return;

      return fetch("/api/domains/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domains: domainsToCheck }),
      })
        .then(function(r) { return r.json(); })
        .then(function(checkData) {
          (checkData.domains || []).forEach(function(d) {
            var featIds = domainToFeatIds[d.domain] || [];
            featIds.forEach(function(featId) {
              _updateFeatureDomainBadge(featId, d.domain, d.status);
            });
          });
        });
    })
    .catch(function() {});
}

function _updateFeatureDomainBadge(featId, domainVal, status) {
  var section = $sidebarFeatures.querySelector(".feature-manager-section");
  if (!section) return;
  // Find the card — cards don't have a data-feat-id, so find via name match
  var badges = section.querySelectorAll(".feature-domain-badge.configured");
  badges.forEach(function(badge) {
    var domainNameAttr = badge.getAttribute("data-domain-name");
    // Match by domain_name attribute — we need to look up the feat's domain_name
    var feat = _featuresData && _featuresData.features
      ? _featuresData.features.find(function(f) { return f.id === featId; })
      : null;
    if (!feat) return;
    if (domainNameAttr !== (feat.domain_name || "")) return;

    var lbl = badge.querySelector(".feature-domain-label");
    if (!lbl) return;
    lbl.classList.remove("feature-domain-label--checking");
    if (status === "connected") {
      lbl.className = "feature-domain-label feature-domain-label--ok";
      lbl.textContent = (domainVal || "Domain") + " ✓";
    } else if (status === "dns_mismatch") {
      lbl.className = "feature-domain-label feature-domain-label--warn";
      lbl.textContent = (domainVal || "Domain") + " (IP mismatch)";
    } else if (status === "unresolvable") {
      lbl.className = "feature-domain-label feature-domain-label--error";
      lbl.textContent = (domainVal || "Domain") + " (DNS error)";
    } else {
      lbl.className = "feature-domain-label feature-domain-label--warn";
      lbl.textContent = (domainVal || "Domain") + " (unknown)";
    }
  });
}

function renderFeatureManager(data) {
  // Remove old feature manager section if it exists
  var old = $sidebarFeatures.querySelector(".feature-manager-section");
  if (old) old.parentNode.removeChild(old);

  var section = document.createElement("div");
  section.className = "category-section feature-manager-section";
  section.dataset.category = "feature-manager";
  section.innerHTML = '<div class="section-header">Feature Manager</div><hr class="section-divider" />';

  // Group by sub-category
  var grouped = {};
  for (var i = 0; i < data.features.length; i++) {
    var f = data.features[i];
    var cat = f.category || "other";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(f);
  }

  var orderedCats = FEATURE_SUBCATEGORY_ORDER.filter(function(k) { return grouped[k]; });
  Object.keys(grouped).forEach(function(k) {
    if (orderedCats.indexOf(k) === -1) orderedCats.push(k);
  });

  for (var j = 0; j < orderedCats.length; j++) {
    var catKey = orderedCats[j];
    var feats = grouped[catKey];
    if (!feats || feats.length === 0) continue;

    var subcat = document.createElement("div");
    subcat.className = "feature-subcategory";
    var subcatLabel = FEATURE_SUBCATEGORY_LABELS[catKey] || catKey;
    subcat.innerHTML = '<div class="feature-subcategory-header">' + escHtml(subcatLabel) + '</div>';

    var cardsWrap = document.createElement("div");
    cardsWrap.className = "feature-cards-wrap";

    for (var k = 0; k < feats.length; k++) {
      cardsWrap.appendChild(buildFeatureCard(feats[k]));
    }
    subcat.appendChild(cardsWrap);
    section.appendChild(subcat);
  }

  $sidebarFeatures.appendChild(section);
}

function buildFeatureCard(feat) {
  var card = document.createElement("div");
  card.className = "feature-card";

  var conflictHtml = "";
  if (feat.conflicts_with && feat.conflicts_with.length > 0) {
    var conflictNames = feat.conflicts_with.map(function(cid) {
      if (!_featuresData) return cid;
      var cf = _featuresData.features.find(function(f) { return f.id === cid; });
      return cf ? cf.name : cid;
    });
    conflictHtml = '<div class="feature-conflict-warning">⚠ Conflicts with: ' + escHtml(conflictNames.join(", ")) + '</div>';
  }

  var domainHtml = "";
  if (feat.needs_domain) {
    if (feat.domain_configured) {
      domainHtml = '<div class="feature-domain-badge configured" data-domain-name="' + escHtml(feat.domain_name || '') + '">'
        + '<span class="feature-domain-icon">🌐</span>'
        + '<span class="feature-domain-label feature-domain-label--checking">Domain: Checking\u2026</span>'
        + '</div>';
    } else {
      domainHtml = '<div class="feature-domain-badge not-configured">'
        + '<span class="feature-domain-icon">🌐</span>'
        + '<span class="feature-domain-label feature-domain-label--warn">Domain: Not configured</span>'
        + '</div>';
    }
  }

  var statusText = feat.enabled ? "Enabled" : "Disabled";

  card.innerHTML =
    '<div class="feature-card-top">' +
    '<div class="feature-card-info">' +
    '<div class="feature-card-name">' + escHtml(feat.name) + '</div>' +
    '<div class="feature-card-desc">' + escHtml(feat.description) + '</div>' +
    '</div>' +
    '<label class="feature-toggle' + (feat.enabled ? " active" : "") + '" title="Toggle ' + escHtml(feat.name) + '">' +
    '<input type="checkbox" class="feature-toggle-input"' + (feat.enabled ? " checked" : "") + ' />' +
    '<span class="feature-toggle-slider"></span>' +
    '</label>' +
    '</div>' +
    domainHtml +
    conflictHtml +
    '<div class="feature-card-status">Status: ' + escHtml(statusText) + '</div>';

  var toggle = card.querySelector(".feature-toggle-input");
  var toggleLabel = card.querySelector(".feature-toggle");
  toggle.addEventListener("change", function() {
    var newEnabled = toggle.checked;
    // Revert visually until confirmed
    toggle.checked = feat.enabled;
    if (newEnabled) { toggleLabel.classList.remove("active"); } else { toggleLabel.classList.add("active"); }
    handleFeatureToggle(feat, newEnabled);
  });

  return card;
}

// ── Auto-launch toggle ────────────────────────────────────────────

async function loadAutolaunchToggle() {
  try {
    var data = await apiFetch("/api/autolaunch/status");
    renderAutolaunchToggle(data.enabled);
  } catch (err) {
    console.warn("Failed to load autolaunch status:", err);
  }
}

function renderAutolaunchToggle(enabled) {
  // Remove existing section if any
  var old = $sidebarFeatures.querySelector(".autolaunch-section");
  if (old) old.parentNode.removeChild(old);

  var section = document.createElement("div");
  section.className = "category-section autolaunch-section";

  section.innerHTML =
    '<div class="section-header">Preferences</div>' +
    '<hr class="section-divider" />' +
    '<div class="feature-card">' +
      '<div class="feature-card-top">' +
        '<div class="feature-card-info">' +
          '<div class="feature-card-name">Auto-launch Hub on Login</div>' +
          '<div class="feature-card-desc">Automatically open the Sovran Hub dashboard in your browser when you log in to the desktop.</div>' +
        '</div>' +
        '<label class="feature-toggle' + (enabled ? " active" : "") + '" id="autolaunch-toggle-label" title="Toggle auto-launch">' +
          '<input type="checkbox" class="feature-toggle-input" id="autolaunch-toggle-input"' + (enabled ? " checked" : "") + ' />' +
          '<span class="feature-toggle-slider"></span>' +
        '</label>' +
      '</div>' +
    '</div>';

  $sidebarFeatures.appendChild(section);

  var input = document.getElementById("autolaunch-toggle-input");
  var label = document.getElementById("autolaunch-toggle-label");
  if (!input || !label) return;

  input.addEventListener("change", async function() {
    var newEnabled = input.checked;
    // Revert visually until confirmed
    input.checked = !newEnabled;
    if (newEnabled) { label.classList.remove("active"); } else { label.classList.add("active"); }
    input.disabled = true;
    try {
      await apiFetch("/api/autolaunch/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: newEnabled }),
      });
      input.checked = newEnabled;
      if (newEnabled) { label.classList.add("active"); } else { label.classList.remove("active"); }
    } catch (err) {
      alert("Failed to update auto-launch setting. Please try again.");
    } finally {
      input.disabled = false;
    }
  });
}
