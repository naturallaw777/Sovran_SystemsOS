/* Sovran_SystemsOS Hub — First-Boot Onboarding Wizard
   Drives the 5-step post-install setup flow. */
"use strict";

// ── Constants ─────────────────────────────────────────────────────

const TOTAL_STEPS = 5;

// Steps to skip per role (steps 2, 3, 4 involve VPS tunnel + domain setup)
const ROLE_SKIP_STEPS = {
  "desktop": [2, 3, 4],
  "node":    [2, 3, 4],
};

// ── Role state (loaded at init) ───────────────────────────────────

var _onboardingRole = "server_plus_desktop";

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

var _currentStep     = 1;
var _servicesData    = null;
var _domainsData     = null;
var _vpsIp           = null;   // VPS IP captured after tunnel setup
var _tunnelLogOffset = 0;
var _tunnelPollTimer = null;

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
  if (step === 3) loadStep3();
  if (step === 4) loadStep4();
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

// ── Step 2: Njal.la Account Setup ────────────────────────────────

// Step 2 is static HTML — no JS loading needed.

// ── Step 3: Connect VPS ──────────────────────────────────────────

function loadStep3() {
  var body = document.getElementById("step-3-body");
  if (!body) return;

  body.innerHTML =
    '<p class="onboarding-body-text" style="margin-bottom:12px;">' +
    'Enter the VPS IP address and root password from your Njal.la VPS. ' +
    'The Hub will automatically configure a secure WireGuard tunnel — no manual setup required.' +
    '</p>' +
    '<div class="onboarding-domain-group">' +
    '<label class="onboarding-domain-label">VPS IP Address</label>' +
    '<input class="onboarding-domain-input domain-field-input" type="text" id="vps-ip-input" placeholder="185.94.x.x" autocomplete="off" />' +
    '</div>' +
    '<div class="onboarding-domain-group">' +
    '<label class="onboarding-domain-label">Root Password</label>' +
    '<input class="onboarding-domain-input domain-field-input" type="password" id="vps-password-input" placeholder="Root password" autocomplete="new-password" />' +
    '</div>' +
    '<div id="tunnel-log-box" style="display:none;margin-top:12px;background:var(--card-color);border:1px solid var(--border-color);border-radius:8px;padding:10px 12px;font-family:monospace;font-size:0.82em;max-height:220px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;"></div>' +
    '<div id="step-3-status" class="onboarding-save-status"></div>';
}

async function connectVps() {
  var ipInput  = document.getElementById("vps-ip-input");
  var pwInput  = document.getElementById("vps-password-input");
  var btn      = document.getElementById("step-3-connect-btn");
  var logBox   = document.getElementById("tunnel-log-box");

  var vpsIp  = ipInput  ? ipInput.value.trim()  : "";
  var vpsPw  = pwInput  ? pwInput.value.trim()  : "";

  if (!vpsIp)  { setStatus("step-3-status", "⚠ Please enter the VPS IP address.", "error");   return; }
  if (!vpsPw)  { setStatus("step-3-status", "⚠ Please enter the VPS root password.", "error"); return; }

  if (btn) { btn.disabled = true; btn.textContent = "Connecting…"; }
  if (logBox) { logBox.style.display = ""; logBox.textContent = ""; }
  setStatus("step-3-status", "Setting up tunnel…", "info");

  _tunnelLogOffset = 0;

  try {
    await apiFetch("/api/tunnel/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vps_ip: vpsIp, vps_password: vpsPw }),
    });
  } catch (err) {
    setStatus("step-3-status", "⚠ " + err.message, "error");
    if (btn) { btn.disabled = false; btn.textContent = "Connect & Setup Tunnel"; }
    return;
  }

  // Poll rebuild/tunnel log until done
  _tunnelPollTimer = setInterval(async function() {
    try {
      var data = await apiFetch("/api/rebuild/status?offset=" + _tunnelLogOffset);
      _tunnelLogOffset = data.offset || _tunnelLogOffset;
      if (logBox && data.log) {
        logBox.textContent += data.log;
        logBox.scrollTop = logBox.scrollHeight;
      }

      if (!data.running) {
        clearInterval(_tunnelPollTimer);
        _tunnelPollTimer = null;
        if (data.result === "success") {
          // Clear the password from memory
          if (pwInput) pwInput.value = "";
          _vpsIp = vpsIp;
          setStatus("step-3-status", "✅ Tunnel established — VPS IP: " + vpsIp, "ok");
          if (btn) { btn.disabled = false; btn.textContent = "Connect & Setup Tunnel"; }
          // Auto-advance after a short delay
          setTimeout(function() { showStep(nextStep(3)); }, 1500);
        } else {
          setStatus("step-3-status", "✗ Tunnel setup failed. Check the log above.", "error");
          if (btn) { btn.disabled = false; btn.textContent = "Retry"; }
        }
      }
    } catch (err) {
      // Server may be rebuilding — keep polling
    }
  }, 2000);
}

// ── Step 4: Domain Configuration ─────────────────────────────────

async function loadStep4() {
  var body = document.getElementById("step-4-body");
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

  // Use VPS IP if tunnel is configured, otherwise fall back to external IP
  var displayIp = _vpsIp
    || (networkData && networkData.vps_ip)
    || (networkData && networkData.external_ip)
    || "your VPS IP";

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
      + '<strong>Point DNS records to your VPS:</strong>'
      + '<ol style="margin:8px 0 0 16px; padding:0; line-height:1.7;">'
      + '<li>In your Njal.la dashboard, create a <strong>Dynamic</strong> record for each service pointing to your VPS IP address:<br>'
      + '<span style="display:inline-block;margin-top:4px;padding:4px 12px;background:var(--card-color);border:1px solid var(--border-color);border-radius:6px;font-family:monospace;font-size:1.1em;font-weight:700;letter-spacing:0.03em;">' + escHtml(displayIp) + '</span></li>'
      + '<li>Njal.la will give you a curl command like:<br>'
      + '<code style="font-size:0.8em;">curl "https://njal.la/update/?h=sub.domain.com&amp;k=abc123&amp;auto"</code></li>'
      + '<li>Enter the subdomain and paste that curl command below for each service</li>'
      + '</ol>'
      + '<p style="margin-top:8px;font-size:0.9em;opacity:0.85;">✅ No router port forwarding needed — all traffic routes through the VPS tunnel.</p>'
      + '</div>';
    html += '<p class="onboarding-hint">Enter each fully-qualified subdomain (e.g. <code>matrix.yourdomain.com</code>) and its Njal.la DDNS curl command.</p>';
    relevantDomains.forEach(function(d) {
      var currentVal = (_domainsData && _domainsData.domains && _domainsData.domains[d.name]) || "";
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
  var emailVal = (_domainsData && _domainsData.domains && _domainsData.domains["sslemail"]) || "";
  html += '<div class="onboarding-domain-group onboarding-domain-group--email">';
  html += '<label class="onboarding-domain-label">📧 SSL Certificate Email</label>';
  html += '<p class="onboarding-hint onboarding-hint--inline">Let\'s Encrypt uses this for certificate expiry notifications.</p>';
  html += '<input class="onboarding-domain-input domain-field-input" type="email" id="ssl-email-input" placeholder="you@example.com" value="' + escHtml(emailVal) + '" />';
  html += '</div>';

  body.innerHTML = html;
}

async function saveStep4() {
  setStatus("step-4-status", "Saving domains…", "info");
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
    setStatus("step-4-status", "⚠ Some errors: " + errors.join("; "), "error");
    return false;
  }

  setStatus("step-4-status", "✓ Saved", "ok");
  return true;
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
  // Step 1 → next (may skip 2-4 for desktop/node)
  var s1next = document.getElementById("step-1-next");
  if (s1next) s1next.addEventListener("click", function() { showStep(nextStep(1)); });

  // Step 2 → 3 (just continue — no data entry needed)
  var s2next = document.getElementById("step-2-next");
  if (s2next) s2next.addEventListener("click", function() { showStep(nextStep(2)); });

  // Step 3: Connect VPS button
  var s3connect = document.getElementById("step-3-connect-btn");
  if (s3connect) s3connect.addEventListener("click", connectVps);

  // Step 3 → 4 (can skip tunnel if already done)
  var s3next = document.getElementById("step-3-next");
  if (s3next) s3next.addEventListener("click", function() { showStep(nextStep(3)); });

  // Step 4 → 5 (save first)
  var s4next = document.getElementById("step-4-next");
  if (s4next) s4next.addEventListener("click", async function() {
    s4next.disabled = true;
    s4next.textContent = "Saving…";
    await saveStep4();
    s4next.disabled = false;
    s4next.textContent = "Save & Continue →";
    showStep(nextStep(4));
  });

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

  // Check if tunnel is already configured (re-running onboarding)
  try {
    var tunnelStatus = await apiFetch("/api/tunnel/status");
    if (tunnelStatus && tunnelStatus.vps_ip) {
      _vpsIp = tunnelStatus.vps_ip;
    }
  } catch (_) {}

  wireNavButtons();
  updateProgress(1);
  loadStep1();
});
