/* Sovran_SystemsOS Hub — First-Boot Onboarding Wizard
   Drives the 6-step post-install setup flow. */
"use strict";

// ── Constants ─────────────────────────────────────────────────────

const TOTAL_STEPS = 6;

// Domains that may need configuration, with service unit mapping for enabled check
const DOMAIN_DEFS = [
  { name: "matrix",          label: "Matrix (Synapse)",             unit: "matrix-synapse.service",   needsDdns: true },
  { name: "haven",           label: "Haven Nostr Relay",            unit: "haven-relay.service",      needsDdns: true },
  { name: "element-calling", label: "Element Video/Audio Calling",  unit: "livekit.service",          needsDdns: true },
  { name: "vaultwarden",     label: "Vaultwarden (Password Vault)", unit: "vaultwarden.service",      needsDdns: true },
  { name: "btcpayserver",    label: "BTCPay Server",                unit: "btcpayserver.service",     needsDdns: true },
  { name: "nextcloud",       label: "Nextcloud",                    unit: "phpfpm-nextcloud.service", needsDdns: true },
  { name: "wordpress",       label: "WordPress",                    unit: "phpfpm-wordpress.service", needsDdns: true },
];

const REBUILD_POLL_INTERVAL = 2000;

// ── State ─────────────────────────────────────────────────────────

var _currentStep  = 1;
var _servicesData = null;
var _domainsData  = null;
var _featuresData = null;

var _rebuildPollTimer  = null;
var _rebuildLogOffset  = 0;
var _rebuildFinished   = false;

// ── Helpers ───────────────────────────────────────────────────────

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function apiFetch(path, options) {
  var res = await fetch(path, options || {});
  if (!res.ok) {
    var detail = res.status + " " + res.statusText;
    try {
      var body = await res.json();
      if (body && body.detail) detail = body.detail;
    } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}

function setStatus(elId, msg, type) {
  var el = document.getElementById(elId);
  if (!el) return;
  el.textContent = msg;
  el.className = "onboarding-save-status" + (type ? " onboarding-save-status--" + type : "");
}

// ── Progress / step navigation ────────────────────────────────────

function updateProgress(step) {
  var fill = document.getElementById("onboarding-progress-fill");
  if (fill) {
    fill.style.width = Math.round(((step - 1) / (TOTAL_STEPS - 1)) * 100) + "%";
  }
  var dots = document.querySelectorAll(".onboarding-step-dot");
  dots.forEach(function(dot) {
    var ds = parseInt(dot.dataset.step, 10);
    dot.classList.remove("active", "completed");
    if (ds < step) dot.classList.add("completed");
    if (ds === step) dot.classList.add("active");
  });
}

function showStep(step) {
  for (var i = 1; i <= TOTAL_STEPS; i++) {
    var panel = document.getElementById("step-" + i);
    if (panel) panel.style.display = (i === step) ? "" : "none";
  }
  _currentStep = step;
  updateProgress(step);

  // Lazy-load step content
  if (step === 2) loadStep2();
  if (step === 3) loadStep3();
  if (step === 4) loadStep4();
  if (step === 5) loadStep5();
}

// ── Step 1: Welcome ───────────────────────────────────────────────

async function loadStep1() {
  try {
    var cfg = await apiFetch("/api/config");
    var badge = document.getElementById("onboarding-role-badge");
    if (badge && cfg.role_label) badge.textContent = cfg.role_label;
  } catch (_) {}
}

// ── Step 2: Domain Configuration ─────────────────────────────────

async function loadStep2() {
  var body = document.getElementById("step-2-body");
  if (!body) return;

  try {
    // Fetch services, domains, and network info in parallel
    var results = await Promise.all([
      apiFetch("/api/services"),
      apiFetch("/api/domains/status"),
      apiFetch("/api/network"),
    ]);
    _servicesData = results[0];
    _domainsData  = results[1];
    var networkData = results[2];
  } catch (err) {
    body.innerHTML = '<p class="onboarding-error">⚠ Could not load service data: ' + escHtml(err.message) + '</p>';
    return;
  }

  var externalIp = (networkData && networkData.external_ip) || "Unknown (could not retrieve)";

  // Build set of enabled service units
  var enabledUnits = new Set();
  (_servicesData || []).forEach(function(svc) {
    if (svc.enabled) enabledUnits.add(svc.unit);
  });

  // Filter domain defs to only those whose service is enabled
  var relevantDomains = DOMAIN_DEFS.filter(function(d) {
    return enabledUnits.has(d.unit);
  });

  var html = "";

  if (relevantDomains.length === 0) {
    html += '<p class="onboarding-body-text">No domain-based services are enabled for your role. You can skip this step.</p>';
  } else {
    html += '<div class="onboarding-port-warn" style="margin-bottom:16px;">'
      + '<strong>Before you continue:</strong>'
      + '<ol style="margin:8px 0 0 16px; padding:0; line-height:1.7;">'
      + '<li>Create an account at <a href="https://njal.la" target="_blank" style="color:var(--accent-color);">https://njal.la</a></li>'
      + '<li>Purchase a new domain on Njal.la, or create a subdomain from a domain you already own. Tip: Subdomains are free to create — you only need to purchase one domain, and you can add as many subdomains as you need at no extra cost.</li>'
      + '<li>In the Njal.la web interface, create a <strong>Dynamic</strong> record pointing to this machine\'s external IP address:<br>'
      + '<span style="display:inline-block;margin-top:4px;padding:4px 12px;background:var(--card-color);border:1px solid var(--border-color);border-radius:6px;font-family:monospace;font-size:1.1em;font-weight:700;letter-spacing:0.03em;">' + escHtml(externalIp) + '</span></li>'
      + '<li>Njal.la will give you a curl command like:<br>'
      + '<code style="font-size:0.8em;">curl "https://njal.la/update/?h=sub.domain.com&amp;k=abc123&amp;auto"</code></li>'
      + '<li>Enter the subdomain and paste that curl command below for each service</li>'
      + '</ol>'
      + '</div>';
    html += '<p class="onboarding-hint">Enter each fully-qualified subdomain (e.g. <code>matrix.yourdomain.com</code>) and its Njal.la DDNS curl command.</p>';
    relevantDomains.forEach(function(d) {
      var currentVal = (_domainsData && _domainsData[d.name]) || "";
      html += '<div class="onboarding-domain-group">';
      html += '<label class="onboarding-domain-label">' + escHtml(d.label) + '</label>';
      html += '<input class="onboarding-domain-input domain-field-input" type="text" id="domain-input-' + escHtml(d.name) + '" data-domain="' + escHtml(d.name) + '" placeholder="e.g. ' + escHtml(d.name) + '.yourdomain.com" value="' + escHtml(currentVal) + '" />';
      html += '<label class="onboarding-domain-label onboarding-domain-label--sub">Njal.la DDNS Curl Command</label>';
      html += '<input class="onboarding-domain-input domain-field-input" type="text" id="ddns-input-' + escHtml(d.name) + '" data-ddns="' + escHtml(d.name) + '" placeholder="curl &quot;https://njal.la/update/?h=' + escHtml(d.name) + '.yourdomain.com&amp;k=abc123&amp;auto&quot;" />';
      html += '<p class="onboarding-hint" style="margin-top:4px;">ℹ Paste the curl URL from your Njal.la dashboard\'s Dynamic record</p>';
      html += '</div>';
    });
  }

  // SSL email section
  var emailVal = (_domainsData && _domainsData["sslemail"]) || "";
  html += '<div class="onboarding-domain-group onboarding-domain-group--email">';
  html += '<label class="onboarding-domain-label">📧 SSL Certificate Email</label>';
  html += '<p class="onboarding-hint onboarding-hint--inline">Let\'s Encrypt uses this for certificate expiry notifications.</p>';
  html += '<input class="onboarding-domain-input domain-field-input" type="email" id="ssl-email-input" placeholder="you@example.com" value="' + escHtml(emailVal) + '" />';
  html += '</div>';

  body.innerHTML = html;
}

async function saveStep2() {
  setStatus("step-2-status", "Saving domains…", "info");
  var errors = [];

  // Save each domain input
  var domainInputs = document.querySelectorAll("[data-domain]");
  for (var i = 0; i < domainInputs.length; i++) {
    var inp = domainInputs[i];
    var domainName = inp.dataset.domain;
    var domainVal = inp.value.trim();
    if (!domainVal) continue; // skip empty — not required

    var ddnsInput = document.getElementById("ddns-input-" + domainName);
    var ddnsVal = ddnsInput ? ddnsInput.value.trim() : "";

    try {
      await apiFetch("/api/domains/set", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain_name: domainName, domain: domainVal, ddns_url: ddnsVal }),
      });
    } catch (err) {
      errors.push(domainName + ": " + err.message);
    }
  }

  // Save SSL email
  var emailInput = document.getElementById("ssl-email-input");
  if (emailInput && emailInput.value.trim()) {
    try {
      await apiFetch("/api/domains/set-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: emailInput.value.trim() }),
      });
    } catch (err) {
      errors.push("SSL email: " + err.message);
    }
  }

  if (errors.length > 0) {
    setStatus("step-2-status", "⚠ Some errors: " + errors.join("; "), "error");
    return false;
  }

  setStatus("step-2-status", "✓ Saved", "ok");
  return true;
}

// ── Step 3: Port Forwarding ───────────────────────────────────────

async function loadStep3() {
  var body = document.getElementById("step-3-body");
  if (!body) return;
  body.innerHTML = '<p class="onboarding-loading">Checking ports…</p>';

  var networkData = null;

  try {
    networkData = await apiFetch("/api/network");
  } catch (err) {
    body.innerHTML = '<p class="onboarding-error">⚠ Could not load network data: ' + escHtml(err.message) + '</p>';
    return;
  }

  var internalIp = (networkData && networkData.internal_ip) || "unknown";

  var ip = escHtml(internalIp);

  var html = '<p class="onboarding-port-note" style="margin-bottom:14px;">'
    + '⚠ <strong>Each port only needs to be forwarded once — all services share the same ports.</strong>'
    + '</p>';

  html += '<div class="onboarding-port-ip">';
  html += '  <span class="onboarding-port-ip-label">Forward ports to this machine\'s internal IP:</span>';
  html += '  <span class="port-req-internal-ip">' + ip + '</span>';
  html += '</div>';

  // Required ports table
  html += '<div class="onboarding-port-section" style="margin-bottom:20px;">';
  html += '<div class="onboarding-port-section-title" style="font-weight:700;margin-bottom:8px;">Required Ports — open these on your router:</div>';
  html += '<table class="onboarding-port-table">';
  html += '<thead><tr><th>Port</th><th>Protocol</th><th>Forward&nbsp;to</th><th>Purpose</th></tr></thead>';
  html += '<tbody>';
  html += '<tr><td class="port-req-port">80</td><td class="port-req-proto">TCP</td><td class="port-req-internal-ip">' + ip + '</td><td class="port-req-desc">HTTP</td></tr>';
  html += '<tr><td class="port-req-port">443</td><td class="port-req-proto">TCP</td><td class="port-req-internal-ip">' + ip + '</td><td class="port-req-desc">HTTPS</td></tr>';
  html += '<tr><td class="port-req-port">22</td><td class="port-req-proto">TCP</td><td class="port-req-internal-ip">' + ip + '</td><td class="port-req-desc">SSH Remote Access</td></tr>';
  html += '<tr><td class="port-req-port">8448</td><td class="port-req-proto">TCP</td><td class="port-req-internal-ip">' + ip + '</td><td class="port-req-desc">Matrix Federation</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // Optional ports table
  html += '<div class="onboarding-port-section" style="margin-bottom:20px;">';
  html += '<div class="onboarding-port-section-title" style="font-weight:700;margin-bottom:4px;">Optional — Only needed if you enable Element Calling:</div>';
  html += '<div style="font-size:0.88em;margin-bottom:8px;color:var(--color-text-muted,#888);">These 5 additional port openings are required on top of the 4 required ports above.</div>';
  html += '<table class="onboarding-port-table">';
  html += '<thead><tr><th>Port</th><th>Protocol</th><th>Forward&nbsp;to</th><th>Purpose</th></tr></thead>';
  html += '<tbody>';
  html += '<tr><td class="port-req-port">7881</td><td class="port-req-proto">TCP</td><td class="port-req-internal-ip">' + ip + '</td><td class="port-req-desc">LiveKit WebRTC signalling</td></tr>';
  html += '<tr><td class="port-req-port">7882–7894</td><td class="port-req-proto">UDP</td><td class="port-req-internal-ip">' + ip + '</td><td class="port-req-desc">LiveKit media streams</td></tr>';
  html += '<tr><td class="port-req-port">5349</td><td class="port-req-proto">TCP</td><td class="port-req-internal-ip">' + ip + '</td><td class="port-req-desc">TURN over TLS</td></tr>';
  html += '<tr><td class="port-req-port">3478</td><td class="port-req-proto">UDP</td><td class="port-req-internal-ip">' + ip + '</td><td class="port-req-desc">TURN (STUN/relay)</td></tr>';
  html += '<tr><td class="port-req-port">30000–40000</td><td class="port-req-proto">TCP/UDP</td><td class="port-req-internal-ip">' + ip + '</td><td class="port-req-desc">TURN relay (WebRTC)</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // Totals
  html += '<div class="onboarding-port-totals">';
  html += '<strong>Total port openings: 4</strong> (without Element Calling)<br>';
  html += '<strong>Total port openings: 9</strong> (with Element Calling — 4 required + 5 optional)';
  html += '</div>';

  html += '<div class="onboarding-port-warn" style="margin-bottom:16px;">'
    + '⚠ <strong>Ports 80 and 443 must be forwarded first.</strong> '
    + 'Caddy uses these to obtain SSL certificates from Let\'s Encrypt. '
    + 'If they are closed, HTTPS will not work and your services will be unreachable from outside your network.'
    + '</div>';

  html += '<details class="onboarding-port-details" style="margin-bottom:16px;">'
    + '<summary class="onboarding-port-details-summary">How to set up port forwarding</summary>'
    + '<ol style="margin:12px 0 0 16px; padding:0; line-height:1.8;">'
    + '<li>Open your router\'s admin panel — usually <code>http://192.168.1.1</code> or <code>http://192.168.0.1</code></li>'
    + '<li>Look for <strong>"Port Forwarding"</strong>, <strong>"NAT"</strong>, or <strong>"Virtual Server"</strong> in the settings</li>'
    + '<li>Create a new rule for each port listed above</li>'
    + '<li>Set the destination/internal IP to <strong>' + ip + '</strong></li>'
    + '<li>Set both internal and external port to the same number</li>'
    + '<li>Save and apply changes</li>'
    + '</ol>'
    + '</details>';

  body.innerHTML = html;
}

// ── Step 4: Credentials ───────────────────────────────────────────

async function loadStep4() {
  var body = document.getElementById("step-4-body");
  if (!body) return;
  body.innerHTML = '<p class="onboarding-loading">Loading credentials…</p>';

  if (!_servicesData) {
    try {
      _servicesData = await apiFetch("/api/services");
    } catch (err) {
      body.innerHTML = '<p class="onboarding-error">⚠ Could not load services: ' + escHtml(err.message) + '</p>';
      return;
    }
  }

  // Find services with credentials that are enabled
  var credsServices = (_servicesData || []).filter(function(svc) {
    return svc.has_credentials && svc.enabled;
  });

  if (credsServices.length === 0) {
    body.innerHTML = '<p class="onboarding-body-text">No credentials found for your current configuration.</p>';
    return;
  }

  body.innerHTML = '<p class="onboarding-loading">Loading credentials…</p>';

  // Fetch all credentials in parallel
  var fetches = credsServices.map(function(svc) {
    return apiFetch("/api/credentials/" + encodeURIComponent(svc.unit))
      .then(function(data) { return { svc: svc, data: data, error: null }; })
      .catch(function(err) { return { svc: svc, data: null, error: err.message }; });
  });
  var allCreds = await Promise.all(fetches);

  // Group by category
  var CATEGORY_ORDER_LOCAL = [
    ["infrastructure", "🔧 Infrastructure"],
    ["bitcoin-base",   "₿ Bitcoin Base"],
    ["bitcoin-apps",   "₿ Bitcoin Apps"],
    ["communication",  "💬 Communication"],
    ["apps",           "📦 Self-Hosted Apps"],
    ["nostr",          "📡 Nostr"],
  ];

  var grouped = {};
  allCreds.forEach(function(item) {
    var cat = item.svc.category || "other";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(item);
  });

  var html = '<div class="onboarding-creds-notice">💡 Save these credentials somewhere safe. You can always view them again from the Hub dashboard.</div>';

  CATEGORY_ORDER_LOCAL.forEach(function(pair) {
    var catKey = pair[0];
    var catLabel = pair[1];
    if (!grouped[catKey] || grouped[catKey].length === 0) return;

    html += '<div class="onboarding-creds-category">';
    html += '<div class="onboarding-creds-category-title">' + escHtml(catLabel) + '</div>';

    grouped[catKey].forEach(function(item) {
      html += '<div class="onboarding-creds-service">';
      html += '<div class="onboarding-creds-service-name">' + escHtml(item.svc.name) + '</div>';

      if (item.error) {
        html += '<p class="onboarding-error">⚠ ' + escHtml(item.error) + '</p>';
      } else if (item.data && item.data.credentials) {
        item.data.credentials.forEach(function(cred) {
          html += '<div class="onboarding-cred-row">';
          html += '<span class="onboarding-cred-label">' + escHtml(cred.label || "") + '</span>';
          if (cred.value) {
            var isSecret = /password|secret|key|token/i.test(cred.label || "");
            if (isSecret) {
              html += '<span class="onboarding-cred-value onboarding-cred-secret" title="Click to reveal">'
                + '<span class="onboarding-cred-hidden">••••••••</span>'
                + '<span class="onboarding-cred-real" style="display:none">' + escHtml(cred.value) + '</span>'
                + '<button class="onboarding-cred-reveal-btn">Show</button>'
                + '</span>';
            } else {
              html += '<span class="onboarding-cred-value">' + escHtml(cred.value) + '</span>';
            }
          }
          html += '</div>';
        });
      }

      html += '</div>';
    });

    html += '</div>';
  });

  // Remaining categories not in the order
  Object.keys(grouped).forEach(function(catKey) {
    var inOrder = CATEGORY_ORDER_LOCAL.some(function(p) { return p[0] === catKey; });
    if (inOrder || !grouped[catKey] || grouped[catKey].length === 0) return;

    html += '<div class="onboarding-creds-category">';
    html += '<div class="onboarding-creds-category-title">' + escHtml(catKey) + '</div>';
    grouped[catKey].forEach(function(item) {
      html += '<div class="onboarding-creds-service">';
      html += '<div class="onboarding-creds-service-name">' + escHtml(item.svc.name) + '</div>';
      if (item.error) {
        html += '<p class="onboarding-error">⚠ ' + escHtml(item.error) + '</p>';
      } else if (item.data && item.data.credentials) {
        item.data.credentials.forEach(function(cred) {
          if (cred.value) {
            html += '<div class="onboarding-cred-row">';
            html += '<span class="onboarding-cred-label">' + escHtml(cred.label || "") + '</span>';
            html += '<span class="onboarding-cred-value">' + escHtml(cred.value) + '</span>';
            html += '</div>';
          }
        });
      }
      html += '</div>';
    });
    html += '</div>';
  });

  body.innerHTML = html;

  // Wire up reveal buttons
  body.querySelectorAll(".onboarding-cred-secret").forEach(function(el) {
    var btn     = el.querySelector(".onboarding-cred-reveal-btn");
    var hidden  = el.querySelector(".onboarding-cred-hidden");
    var real    = el.querySelector(".onboarding-cred-real");
    if (!btn || !hidden || !real) return;
    btn.addEventListener("click", function() {
      if (real.style.display === "none") {
        real.style.display = "";
        hidden.style.display = "none";
        btn.textContent = "Hide";
      } else {
        real.style.display = "none";
        hidden.style.display = "";
        btn.textContent = "Show";
      }
    });
  });
}

// ── Step 5: Feature Manager ───────────────────────────────────────

async function loadStep5() {
  var body = document.getElementById("step-5-body");
  if (!body) return;
  body.innerHTML = '<p class="onboarding-loading">Loading features…</p>';

  try {
    _featuresData = await apiFetch("/api/features");
  } catch (err) {
    body.innerHTML = '<p class="onboarding-error">⚠ Could not load features: ' + escHtml(err.message) + '</p>';
    return;
  }

  renderFeaturesStep(_featuresData);
}

function renderFeaturesStep(data) {
  var body = document.getElementById("step-5-body");
  if (!body) return;

  var SUBCATEGORY_LABELS = {
    "infrastructure": "🔧 Infrastructure",
    "bitcoin":        "₿ Bitcoin",
    "communication":  "💬 Communication",
    "nostr":          "📡 Nostr",
  };

  var SUBCATEGORY_ORDER = ["infrastructure", "bitcoin", "communication", "nostr"];

  var grouped = {};
  (data.features || []).forEach(function(f) {
    var cat = f.category || "other";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(f);
  });

  var html = "";
  var orderedCats = SUBCATEGORY_ORDER.filter(function(k) { return grouped[k]; });
  Object.keys(grouped).forEach(function(k) {
    if (orderedCats.indexOf(k) === -1) orderedCats.push(k);
  });

  orderedCats.forEach(function(catKey) {
    var feats = grouped[catKey];
    if (!feats || feats.length === 0) return;

    var catLabel = SUBCATEGORY_LABELS[catKey] || catKey;
    html += '<div class="onboarding-feat-group">';
    html += '<div class="onboarding-feat-group-title">' + escHtml(catLabel) + '</div>';

    feats.forEach(function(feat) {
      var domainHtml = "";
      if (feat.needs_domain) {
        if (feat.domain_configured) {
          domainHtml = '<span class="onboarding-feat-domain onboarding-feat-domain--ok">🌐 Domain configured</span>';
        } else {
          domainHtml = '<span class="onboarding-feat-domain onboarding-feat-domain--missing">🌐 Domain not set</span>';
        }
      }

      html += '<div class="onboarding-feat-card" id="feat-card-' + escHtml(feat.id) + '">';
      html += '<div class="onboarding-feat-info">';
      html += '<div class="onboarding-feat-name">' + escHtml(feat.name) + '</div>';
      html += '<div class="onboarding-feat-desc">' + escHtml(feat.description) + '</div>';
      html += domainHtml;
      html += '</div>';
      html += '<label class="feature-toggle' + (feat.enabled ? " active" : "") + '" title="Toggle ' + escHtml(feat.name) + '">';
      html += '<input type="checkbox" class="feature-toggle-input" data-feat-id="' + escHtml(feat.id) + '"' + (feat.enabled ? " checked" : "") + ' />';
      html += '<span class="feature-toggle-slider"></span>';
      html += '</label>';
      html += '</div>';
    });

    html += '</div>';
  });

  body.innerHTML = html;

  // Wire up toggles
  body.querySelectorAll(".feature-toggle-input").forEach(function(input) {
    var featId = input.dataset.featId;
    var label  = input.closest(".feature-toggle");
    var feat   = (data.features || []).find(function(f) { return f.id === featId; });
    if (!feat) return;

    input.addEventListener("change", function() {
      var newEnabled = input.checked;
      // Revert UI until confirmed/done
      input.checked = feat.enabled;
      if (newEnabled) { if (label) label.classList.remove("active"); }
      else            { if (label) label.classList.add("active"); }

      handleFeatureToggleStep5(feat, newEnabled, input, label);
    });
  });
}

async function handleFeatureToggleStep5(feat, newEnabled, inputEl, labelEl) {
  // For Bitcoin features being enabled, show a clear mutual-exclusivity confirmation
  if (newEnabled && (feat.id === "bip110" || feat.id === "bitcoin-core")) {
    var confirmMsg;
    if (feat.id === "bip110") {
      confirmMsg = "Only one Bitcoin node implementation can be active. Enabling Bitcoin Knots + BIP110 will disable Bitcoin Core (if active). Continue?";
    } else {
      confirmMsg = "Only one Bitcoin node implementation can be active. Enabling Bitcoin Core will disable Bitcoin Knots + BIP110 (if active). Continue?";
    }
    if (!confirm(confirmMsg)) {
      if (inputEl) inputEl.checked = feat.enabled;
      return;
    }
  }

  setStatus("step-5-rebuild-status", "Saving…", "info");

  // Collect nostr_npub if needed
  var extra = {};
  if (newEnabled && feat.id === "haven") {
    var npub = prompt("Enter your Nostr public key (npub1…):");
    if (!npub || !npub.trim()) {
      setStatus("step-5-rebuild-status", "⚠ npub required for Haven", "error");
      return;
    }
    extra.nostr_npub = npub.trim();
  }

  try {
    await apiFetch("/api/features/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature: feat.id, enabled: newEnabled, extra: extra }),
    });
  } catch (err) {
    setStatus("step-5-rebuild-status", "⚠ " + err.message, "error");
    return;
  }

  // Update local state
  feat.enabled = newEnabled;
  if (inputEl) inputEl.checked = newEnabled;
  if (labelEl) {
    if (newEnabled) labelEl.classList.add("active");
    else            labelEl.classList.remove("active");
  }

  setStatus("step-5-rebuild-status", "✓ Feature updated — system rebuild started", "ok");
  startRebuildPoll();
}

// ── Rebuild progress polling ──────────────────────────────────────

function startRebuildPoll() {
  _rebuildLogOffset = 0;
  _rebuildFinished  = false;

  var modal    = document.getElementById("ob-rebuild-modal");
  var statusEl = document.getElementById("ob-rebuild-status");
  var logEl    = document.getElementById("ob-rebuild-log");
  var closeBtn = document.getElementById("ob-rebuild-close");
  var spinner  = document.getElementById("ob-rebuild-spinner");

  if (modal) modal.style.display = "flex";
  if (statusEl) statusEl.textContent = "Rebuilding…";
  if (logEl) logEl.textContent = "";
  if (closeBtn) closeBtn.disabled = true;
  if (spinner) spinner.style.display = "";

  if (_rebuildPollTimer) clearInterval(_rebuildPollTimer);
  _rebuildPollTimer = setInterval(pollRebuild, REBUILD_POLL_INTERVAL);
}

async function pollRebuild() {
  if (_rebuildFinished) {
    clearInterval(_rebuildPollTimer);
    return;
  }

  try {
    var data = await apiFetch("/api/rebuild/status?offset=" + _rebuildLogOffset);
    var logEl    = document.getElementById("ob-rebuild-log");
    var statusEl = document.getElementById("ob-rebuild-status");
    var closeBtn = document.getElementById("ob-rebuild-close");
    var spinner  = document.getElementById("ob-rebuild-spinner");

    if (data.log && logEl) {
      logEl.textContent += data.log;
      logEl.scrollTop = logEl.scrollHeight;
      _rebuildLogOffset = data.offset || _rebuildLogOffset;
    }

    if (!data.running) {
      _rebuildFinished = true;
      clearInterval(_rebuildPollTimer);
      if (data.result === "success" || data.result === "ok") {
        if (statusEl) statusEl.textContent = "✓ Rebuild complete";
        if (spinner)  spinner.style.display = "none";
        setStatus("step-5-rebuild-status", "✓ Rebuild complete", "ok");
      } else {
        if (statusEl) statusEl.textContent = "⚠ Rebuild finished with issues";
        if (spinner)  spinner.style.display = "none";
        setStatus("step-5-rebuild-status", "⚠ Rebuild finished with issues — see log", "error");
      }
      if (closeBtn) closeBtn.disabled = false;
    }
  } catch (_) {}
}

// ── Step 6: Complete ──────────────────────────────────────────────

async function completeOnboarding() {
  var btn = document.getElementById("step-6-finish");
  if (btn) { btn.disabled = true; btn.textContent = "Finishing…"; }

  try {
    await apiFetch("/api/onboarding/complete", { method: "POST" });
  } catch (_) {
    // Even if this fails, navigate to dashboard
  }

  window.location.href = "/";
}

// ── Event wiring ──────────────────────────────────────────────────

function wireNavButtons() {
  // Step 1 → 2
  var s1next = document.getElementById("step-1-next");
  if (s1next) s1next.addEventListener("click", function() { showStep(2); });

  // Step 2 → 3 (save first)
  var s2next = document.getElementById("step-2-next");
  if (s2next) s2next.addEventListener("click", async function() {
    s2next.disabled = true;
    s2next.textContent = "Saving…";
    await saveStep2();
    s2next.disabled = false;
    s2next.textContent = "Save & Continue →";
    showStep(3);
  });

  // Step 3 → 4
  var s3next = document.getElementById("step-3-next");
  if (s3next) s3next.addEventListener("click", function() { showStep(4); });

  // Step 4 → 5
  var s4next = document.getElementById("step-4-next");
  if (s4next) s4next.addEventListener("click", function() { showStep(5); });

  // Step 5 → 6
  var s5next = document.getElementById("step-5-next");
  if (s5next) s5next.addEventListener("click", function() { showStep(6); });

  // Step 6: finish
  var s6finish = document.getElementById("step-6-finish");
  if (s6finish) s6finish.addEventListener("click", completeOnboarding);

  // Back buttons
  document.querySelectorAll(".onboarding-btn-back").forEach(function(btn) {
    var prev = parseInt(btn.dataset.prev, 10);
    btn.addEventListener("click", function() { showStep(prev); });
  });

  // Rebuild modal close
  var rebuildClose = document.getElementById("ob-rebuild-close");
  if (rebuildClose) {
    rebuildClose.addEventListener("click", function() {
      var modal = document.getElementById("ob-rebuild-modal");
      if (modal) modal.style.display = "none";
    });
  }
}

// ── Init ──────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async function() {
  // If onboarding is already complete, go to dashboard
  try {
    var status = await apiFetch("/api/onboarding/status");
    if (status.complete) {
      window.location.href = "/";
      return;
    }
  } catch (_) {}

  wireNavButtons();
  updateProgress(1);
  loadStep1();
});
