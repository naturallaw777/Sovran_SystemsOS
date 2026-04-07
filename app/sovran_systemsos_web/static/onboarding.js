/* Sovran_SystemsOS Hub — First-Boot Onboarding Wizard
   Drives the 5-step post-install setup flow. */
"use strict";

// ── Constants ─────────────────────────────────────────────────────

const TOTAL_STEPS = 5;

// Steps to skip per role (steps 3 and 4 involve domain/port setup)
// Step 2 (password) is NEVER skipped — all roles need it.
const ROLE_SKIP_STEPS = {
  "desktop": [3, 4],
  "node":    [3, 4],
};

// ── Role state (loaded at init) ───────────────────────────────────

var _onboardingRole = "server_plus_desktop";

// Password default state (loaded at step 2)
var _passwordIsDefault = true;

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

// ── State ─────────────────────────────────────────────────────────

var _currentStep  = 1;
var _servicesData = null;
var _domainsData  = null;

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
  // Step 5 (Complete) is static — no lazy-load needed
}

// Return the next step number, skipping over role-excluded steps
function nextStep(current) {
  var skip = ROLE_SKIP_STEPS[_onboardingRole] || [];
  var next = current + 1;
  while (next < TOTAL_STEPS && skip.indexOf(next) !== -1) next++;
  return next;
}

// Return the previous step number, skipping over role-excluded steps
function prevStep(current) {
  var skip = ROLE_SKIP_STEPS[_onboardingRole] || [];
  var prev = current - 1;
  while (prev > 1 && skip.indexOf(prev) !== -1) prev--;
  return prev;
}

// ── Step 1: Welcome ───────────────────────────────────────────────

async function loadStep1() {
  try {
    var cfg = await apiFetch("/api/config");
    var badge = document.getElementById("onboarding-role-badge");
    if (badge && cfg.role_label) badge.textContent = cfg.role_label;
  } catch (_) {}
}

// ── Step 2: Create Your Password ─────────────────────────────────

async function loadStep2() {
  var body = document.getElementById("step-2-body");
  if (!body) return;

  var nextBtn = document.getElementById("step-2-next");

  try {
    var result = await apiFetch("/api/security/password-is-default");
    _passwordIsDefault = result.is_default !== false;
  } catch (_) {
    _passwordIsDefault = true;
  }

  if (_passwordIsDefault) {
    // Factory-sealed scenario: password must be set before continuing
    if (nextBtn) nextBtn.textContent = "Set Password & Continue \u2192";

    body.innerHTML =
      '<div class="onboarding-password-group">' +
        '<label class="onboarding-domain-label" for="pw-new">New Password</label>' +
        '<div class="onboarding-password-input-wrap">' +
          '<input class="onboarding-password-input" type="password" id="pw-new" autocomplete="new-password" placeholder="At least 8 characters" />' +
          '<button type="button" class="onboarding-password-toggle" data-target="pw-new" aria-label="Show password">👁</button>' +
        '</div>' +
        '<p class="onboarding-password-hint">Minimum 8 characters</p>' +
      '</div>' +
      '<div class="onboarding-password-group">' +
        '<label class="onboarding-domain-label" for="pw-confirm">Confirm Password</label>' +
        '<div class="onboarding-password-input-wrap">' +
          '<input class="onboarding-password-input" type="password" id="pw-confirm" autocomplete="new-password" placeholder="Re-enter your password" />' +
          '<button type="button" class="onboarding-password-toggle" data-target="pw-confirm" aria-label="Show password">👁</button>' +
        '</div>' +
      '</div>' +
      '<div class="onboarding-password-warning">⚠️ Write this password down — it cannot be recovered.</div>';

    // Wire show/hide toggles
    body.querySelectorAll(".onboarding-password-toggle").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var inp = document.getElementById(btn.dataset.target);
        if (inp) inp.type = (inp.type === "password") ? "text" : "password";
      });
    });

  } else {
    // DIY install scenario: password already set by installer
    if (nextBtn) nextBtn.textContent = "Continue \u2192";

    body.innerHTML =
      '<div class="onboarding-password-success">✅ Your password was already set during installation.</div>' +
      '<details class="onboarding-password-optional">' +
        '<summary>Change it anyway</summary>' +
        '<div style="margin-top:14px;">' +
          '<div class="onboarding-password-group">' +
            '<label class="onboarding-domain-label" for="pw-new">New Password</label>' +
            '<div class="onboarding-password-input-wrap">' +
              '<input class="onboarding-password-input" type="password" id="pw-new" autocomplete="new-password" placeholder="At least 8 characters" />' +
              '<button type="button" class="onboarding-password-toggle" data-target="pw-new" aria-label="Show password">👁</button>' +
            '</div>' +
            '<p class="onboarding-password-hint">Minimum 8 characters</p>' +
          '</div>' +
          '<div class="onboarding-password-group">' +
            '<label class="onboarding-domain-label" for="pw-confirm">Confirm Password</label>' +
            '<div class="onboarding-password-input-wrap">' +
              '<input class="onboarding-password-input" type="password" id="pw-confirm" autocomplete="new-password" placeholder="Re-enter your password" />' +
              '<button type="button" class="onboarding-password-toggle" data-target="pw-confirm" aria-label="Show password">👁</button>' +
            '</div>' +
          '</div>' +
          '<div class="onboarding-password-warning">⚠️ Write this password down — it cannot be recovered.</div>' +
        '</div>' +
      '</details>';

    // Wire show/hide toggles
    body.querySelectorAll(".onboarding-password-toggle").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var inp = document.getElementById(btn.dataset.target);
        if (inp) inp.type = (inp.type === "password") ? "text" : "password";
      });
    });
  }
}

async function saveStep2() {
  var newPw = document.getElementById("pw-new");
  var confirmPw = document.getElementById("pw-confirm");

  // If no fields visible or both empty and password already set → skip
  if (!newPw || !newPw.value.trim()) {
    if (!_passwordIsDefault) return true; // already set, no change requested
    setStatus("step-2-status", "⚠ Please enter a password.", "error");
    return false;
  }

  var pw = newPw.value;
  var cpw = confirmPw ? confirmPw.value : "";

  if (pw.length < 8) {
    setStatus("step-2-status", "⚠ Password must be at least 8 characters.", "error");
    return false;
  }
  if (pw !== cpw) {
    setStatus("step-2-status", "⚠ Passwords do not match.", "error");
    return false;
  }

  setStatus("step-2-status", "Saving password…", "info");
  try {
    await apiFetch("/api/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: pw, confirm_password: cpw }),
    });
  } catch (err) {
    setStatus("step-2-status", "⚠ " + err.message, "error");
    return false;
  }

  setStatus("step-2-status", "✓ Password saved", "ok");
  _passwordIsDefault = false;
  return true;
}

// ── Step 3: Domain Configuration ─────────────────────────────────

async function loadStep3() {
  var body = document.getElementById("step-3-body");
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

async function saveStep3() {
  setStatus("step-3-status", "Saving domains…", "info");
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
    setStatus("step-3-status", "⚠ Some errors: " + errors.join("; "), "error");
    return false;
  }

  setStatus("step-3-status", "✓ Saved", "ok");
  return true;
}

// ── Step 4: Port Forwarding ───────────────────────────────────────

async function loadStep4() {
  var body = document.getElementById("step-4-body");
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

// ── Step 5: Complete ──────────────────────────────────────────────

async function completeOnboarding() {
  var btn = document.getElementById("step-5-finish");
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
  // Step 1 → next
  var s1next = document.getElementById("step-1-next");
  if (s1next) s1next.addEventListener("click", function() { showStep(nextStep(1)); });

  // Step 2 → 3 (save password first)
  var s2next = document.getElementById("step-2-next");
  if (s2next) s2next.addEventListener("click", async function() {
    s2next.disabled = true;
    var origText = s2next.textContent;
    s2next.textContent = "Saving…";
    var ok = await saveStep2();
    s2next.disabled = false;
    s2next.textContent = origText;
    if (ok) showStep(nextStep(2));
  });

  // Step 3 → 4 (save domains first)
  var s3next = document.getElementById("step-3-next");
  if (s3next) s3next.addEventListener("click", async function() {
    s3next.disabled = true;
    s3next.textContent = "Saving…";
    await saveStep3();
    s3next.disabled = false;
    s3next.textContent = "Save & Continue →";
    showStep(nextStep(3));
  });

  // Step 4 → 5 (Complete)
  var s4next = document.getElementById("step-4-next");
  if (s4next) s4next.addEventListener("click", function() { showStep(nextStep(4)); });

  // Step 5: finish
  var s5finish = document.getElementById("step-5-finish");
  if (s5finish) s5finish.addEventListener("click", completeOnboarding);

  // Back buttons
  document.querySelectorAll(".onboarding-btn-back").forEach(function(btn) {
    var prev = parseInt(btn.dataset.prev, 10);
    btn.addEventListener("click", function() { showStep(prevStep(prev + 1)); });
  });
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

  // Load role so step-skipping is applied before wiring nav buttons
  try {
    var cfg = await apiFetch("/api/config");
    if (cfg.role) _onboardingRole = cfg.role;
  } catch (_) {}

  wireNavButtons();
  updateProgress(1);
  loadStep1();
});
