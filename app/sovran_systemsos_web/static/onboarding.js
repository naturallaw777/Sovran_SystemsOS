/* Sovran_SystemsOS Hub — First-Boot Onboarding Wizard
   Drives the 4-step post-install setup flow. */
"use strict";

// ── Constants ─────────────────────────────────────────────────────

const TOTAL_STEPS = 4;

// Steps to skip per role (step 3 involves domain setup)
// Step 2 (timezone/locale) is NEVER skipped — all roles need it.
const ROLE_SKIP_STEPS = {
  "desktop": [3],
  "node":    [3],
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

var _currentStep  = 1;
var _servicesData = null;
var _domainsData  = null;
var _migrationOccurred = false;

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

function updateCompleteChecklist() {
  var checklist = document.getElementById("onboarding-checklist");
  if (!checklist) return;
  var existing = document.getElementById("onboarding-migration-check");
  if (_migrationOccurred) {
    if (!existing) {
      var li = document.createElement("li");
      li.id = "onboarding-migration-check";
      li.textContent = "✅ Migration password noted";
      checklist.appendChild(li);
    }
    return;
  }
  if (existing) existing.remove();
}

function showMigrationStep(password) {
  for (var i = 1; i <= TOTAL_STEPS; i++) {
    var panel = document.getElementById("step-" + i);
    if (panel) panel.style.display = "none";
  }
  var migrationPanel = document.getElementById("step-migration");
  if (migrationPanel) migrationPanel.style.display = "";
  var pw = document.getElementById("migration-password-value");
  if (pw) pw.textContent = password || "";
  var progressBar = document.getElementById("onboarding-progress-bar");
  if (progressBar) progressBar.style.display = "none";
  var nav = document.getElementById("onboarding-steps-nav");
  if (nav) nav.style.display = "none";
}

function showStep1FromMigration() {
  var migrationPanel = document.getElementById("step-migration");
  if (migrationPanel) migrationPanel.style.display = "none";
  var progressBar = document.getElementById("onboarding-progress-bar");
  if (progressBar) progressBar.style.display = "";
  var nav = document.getElementById("onboarding-steps-nav");
  if (nav) nav.style.display = "";
  showStep(1);
  loadStep1();
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
  // Step 4 (Complete) is static — no lazy-load needed
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

// ── Step 2: Timezone & Locale ─────────────────────────────────────

async function loadStep2() {
  var body = document.getElementById("step-2-body");
  if (!body || body._tzLoaded) return;
  body._tzLoaded = true;

  body.innerHTML = '<p class="onboarding-loading">Loading timezone data…</p>';

  var timezones = [];
  var currentTz = null;
  var locales = [];
  var currentLocale = null;

  try {
    var results = await Promise.all([
      apiFetch("/api/system/timezones"),
      apiFetch("/api/system/locales"),
    ]);
    timezones = results[0].timezones || [];
    currentTz = results[0].current || null;
    locales = results[1].locales || [];
    currentLocale = results[1].current || null;
  } catch (err) {
    body.innerHTML = '<p class="onboarding-error">⚠ Could not load timezone data: ' + escHtml(err.message) + '</p>';
    return;
  }

  // Try to auto-detect timezone from browser
  var browserTz = null;
  try { browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (_) {}
  var selectedTz = currentTz || browserTz || "";

  var html = '';

  // Timezone section
  html += '<div class="onboarding-tz-group">';
  html += '<label class="onboarding-domain-label" for="tz-search">🕐 Timezone</label>';
  html += '<input class="onboarding-tz-search" type="text" id="tz-search" placeholder="Search timezones…" autocomplete="off" value="' + escHtml(selectedTz) + '" />';
  html += '<select class="onboarding-tz-select" id="tz-select" size="5">';
  timezones.forEach(function(tz) {
    var sel = tz === selectedTz ? ' selected' : '';
    html += '<option value="' + escHtml(tz) + '"' + sel + '>' + escHtml(tz) + '</option>';
  });
  html += '</select>';
  html += '<p class="onboarding-hint">Current: <span id="tz-current-display">' + escHtml(selectedTz || 'Not set') + '</span></p>';
  html += '</div>';

  // Locale section
  html += '<div class="onboarding-tz-group">';
  html += '<label class="onboarding-domain-label" for="locale-select">🌐 Language / Locale</label>';
  html += '<select class="onboarding-tz-select onboarding-locale-select" id="locale-select">';
  locales.forEach(function(loc) {
    var sel = loc === (currentLocale || 'en_US.UTF-8') ? ' selected' : '';
    html += '<option value="' + escHtml(loc) + '"' + sel + '>' + escHtml(loc) + '</option>';
  });
  html += '</select>';
  html += '</div>';

  body.innerHTML = html;

  // Wire timezone search filter
  var tzSearch = document.getElementById('tz-search');
  var tzSelect = document.getElementById('tz-select');
  var tzCurrentDisplay = document.getElementById('tz-current-display');

  if (tzSearch && tzSelect) {
    // When typing in search box, filter the dropdown options
    tzSearch.addEventListener('input', function() {
      var q = tzSearch.value.toLowerCase();
      var opts = tzSelect.options;
      var firstVisible = null;
      for (var i = 0; i < opts.length; i++) {
        var match = opts[i].value.toLowerCase().indexOf(q) !== -1;
        opts[i].style.display = match ? '' : 'none';
        if (match && firstVisible === null) firstVisible = i;
      }
      if (firstVisible !== null) {
        tzSelect.selectedIndex = firstVisible;
        if (tzCurrentDisplay) tzCurrentDisplay.textContent = tzSelect.options[firstVisible].value;
      }
    });

    // When selecting from dropdown, update search box
    tzSelect.addEventListener('change', function() {
      if (tzSelect.value) {
        tzSearch.value = tzSelect.value;
        if (tzCurrentDisplay) tzCurrentDisplay.textContent = tzSelect.value;
      }
    });

    // Scroll selected option into view
    if (tzSelect.selectedIndex >= 0) {
      tzSelect.options[tzSelect.selectedIndex].scrollIntoView({ block: 'nearest' });
    }
  }
}

async function saveStep2() {
  var tzSelect = document.getElementById('tz-select');
  var tzSearch = document.getElementById('tz-search');
  var localeSelect = document.getElementById('locale-select');

  // Determine selected timezone: prefer dropdown selection, fall back to search text
  var tz = (tzSelect && tzSelect.value) ? tzSelect.value : (tzSearch ? tzSearch.value.trim() : '');
  var locale = localeSelect ? localeSelect.value : '';

  if (!tz) {
    setStatus('step-2-status', '⚠ Please select a timezone.', 'error');
    return false;
  }

  setStatus('step-2-status', 'Saving…', 'info');

  var errors = [];

  try {
    await apiFetch('/api/system/timezone', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ timezone: tz }),
    });
  } catch (err) {
    errors.push('Timezone: ' + err.message);
  }

  if (locale) {
    try {
      await apiFetch('/api/system/locale', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ locale: locale }),
      });
    } catch (err) {
      errors.push('Locale: ' + err.message);
    }
  }

  if (errors.length > 0) {
    setStatus('step-2-status', '⚠ ' + errors.join('; '), 'error');
    return false;
  }

  setStatus('step-2-status', '✓ Timezone & locale saved', 'ok');
  return true;
}

// ── Step 3: Domain Configuration ─────────────────────────────────

async function loadStep3() {
  var body = document.getElementById("step-3-body");
  if (!body) return;

  try {
    // Fetch services and domains in parallel (network info is best-effort below)
    var results = await Promise.all([
      apiFetch("/api/services"),
      apiFetch("/api/domains/status"),
    ]);
    _servicesData = results[0];
    _domainsData  = results[1];
  } catch (err) {
    body.innerHTML = '<p class="onboarding-error">⚠ Could not load service data: ' + escHtml(err.message) + '</p>';
    return;
  }

  // Best-effort internal IP for the router note — never blocks this step
  var internalIp = "";
  try {
    var networkData = await apiFetch("/api/network");
    if (networkData && networkData.internal_ip && networkData.internal_ip !== "unavailable") {
      internalIp = String(networkData.internal_ip).trim();
    }
  } catch (_) {}

  // Build set of enabled service units
  var enabledUnits = new Set();
  (_servicesData || []).forEach(function(svc) {
    if (svc.enabled) enabledUnits.add(svc.unit);
  });

  // Filter domain defs to only those whose service is enabled
  var relevantDomains = DOMAIN_DEFS.filter(function(d) {
    return enabledUnits.has(d.unit);
  });

  var domainValues = (_domainsData && _domainsData.domains) || {};

  var html = "";

  if (relevantDomains.length === 0) {
    html += '<p class="onboarding-body-text">No domain-based services are enabled for your role. You can skip this step.</p>';
  } else {
    html += '<div class="onboarding-port-warn" style="margin-bottom:16px;">'
      + '<p style="margin:0 0 8px;"><strong>Sovran_SystemsOS uses Njal.la for domains and Dynamic DNS.</strong></p>'
      + '<ol style="margin:8px 0 0 16px; padding:0; line-height:1.7;">'
      + '<li>Create an account at <a href="https://njal.la" target="_blank" style="color:var(--accent-color);">https://njal.la</a>.</li>'
      + '<li>Buy at least one domain. Each service below needs its own domain — you can either give each service its own subdomain of a single domain you buy (subdomains are free, and one domain can have many), OR use a separate domain for each. Your choice.</li>'
      + '<li>For each service, add a <strong>Dynamic</strong> record in Njal.la:'
      + '<ul style="margin:4px 0 0 16px;padding:0;line-height:1.7;">'
      + '<li>In the Njal.la <strong>Name</strong> field, type ONLY the host part — the word before your domain.<br>'
      + '(Example only, your choice — for &quot;call.yourdomain.com&quot; you&apos;d type just: <code>call</code>.)<br>'
      + 'If you bought a whole separate domain just for this service, leave Name blank or use <code>@</code>.<br>'
      + '&#9888; Do NOT type the full domain in the Name field — Njal.la adds it automatically.</li>'
      + '<li>A Dynamic record has NO IP field. You don&apos;t enter an IP anywhere — it auto-fills once Sovran_SystemsOS updates it (on save, and again after reboot).</li>'
      + '</ul>'
      + '</li>'
      + '<li>Njal.la gives you a curl command like:<br>'
      + '<code style="font-size:0.8em;">curl &quot;https://njal.la/update/?h=call.yourdomain.com&amp;k=abc123&amp;auto&quot;</code></li>'
      + '</ol>'
      + '</div>';
    html += '<p class="onboarding-hint">Enter each service\'s full domain — a subdomain (e.g. <code>call.yourdomain.com</code>) or a separate domain (e.g. <code>call.com</code>) — and its Njal.la DDNS curl command.</p>';

    // Compact router note (full port guidance is shown when a feature is
    // enabled, and lives on each service tile afterwards)
    var routerIpPart = internalIp
      ? ' to this computer&rsquo;s internal IP <strong>' + escHtml(internalIp) + '</strong>'
      : ' to this computer&rsquo;s internal IP';
    html += '<div class="onboarding-port-warn" style="margin-bottom:16px;">'
      + '🔌 <strong>One router task:</strong> in your router&rsquo;s <strong>port forwarding</strong> settings, forward '
      + 'port <strong>80 (TCP)</strong> and port <strong>443 (TCP)</strong>'
      + routerIpPart + '. Use the <strong>same number for the internal and external port</strong>. '
      + 'These are required for HTTPS and SSL certificates — without them your services cannot be reached from outside your home network. '
      + 'Add port <strong>22 (TCP)</strong> as well if you want remote SSH access. '
      + 'Element Call needs a few extra ports (some UDP), and you&rsquo;ll be shown exactly which when you enable it.'
      + '</div>';

    relevantDomains.forEach(function(d) {
      var currentVal = domainValues[d.name] || "";
      html += '<div class="onboarding-domain-group">';
      html += '<label class="onboarding-domain-label">' + escHtml(d.label) + '</label>';
      html += '<input class="onboarding-domain-input domain-field-input" type="text" id="domain-input-' + escHtml(d.name) + '" data-domain="' + escHtml(d.name) + '" placeholder="e.g. ' + escHtml(d.name) + '.yourdomain.com" value="' + escHtml(currentVal) + '" />';
      html += '<label class="onboarding-domain-label onboarding-domain-label--sub">Njal.la DDNS Curl Command</label>';
      html += '<input class="onboarding-domain-input domain-field-input" type="text" id="ddns-input-' + escHtml(d.name) + '" data-ddns="' + escHtml(d.name) + '" placeholder="curl &quot;https://njal.la/update/?h=...&amp;k=...&amp;auto&quot;" />';
      html += '<p class="onboarding-hint" style="margin-top:4px;">ℹ Paste the curl URL from your Njal.la dashboard\'s Dynamic record</p>';
      html += '<button type="button" class="btn btn-primary onboarding-domain-save-btn" data-save-domain="' + escHtml(d.name) + '" style="align-self:flex-start;margin-top:8px;font-size:0.82rem;padding:6px 16px;">Save</button>';
      html += '<span class="onboarding-domain-save-status" id="domain-save-status-' + escHtml(d.name) + '" style="font-size:0.82rem;min-height:1.2em;"></span>';
      html += '</div>';
    });
  }

  // SSL email section
  var emailVal = domainValues["sslemail"] || "";
  html += '<div class="onboarding-domain-group onboarding-domain-group--email">';
  html += '<label class="onboarding-domain-label">📧 SSL Certificate Email</label>';
  html += '<p class="onboarding-hint onboarding-hint--inline">Let\'s Encrypt uses this for certificate expiry notifications.</p>';
  html += '<input class="onboarding-domain-input domain-field-input" type="email" id="ssl-email-input" placeholder="you@example.com" value="' + escHtml(emailVal) + '" />';
  html += '<button type="button" class="btn btn-primary onboarding-domain-save-btn" data-save-email="true" style="align-self:flex-start;margin-top:8px;font-size:0.82rem;padding:6px 16px;">Save</button>';
  html += '<span class="onboarding-domain-save-status" id="domain-save-status-email" style="font-size:0.82rem;min-height:1.2em;"></span>';
  html += '</div>';

  body.innerHTML = html;

  // Wire per-field save buttons for domains
  body.querySelectorAll('[data-save-domain]').forEach(function(btn) {
    btn.addEventListener('click', async function() {
      var domainName = btn.dataset.saveDomain;
      var domainInput = document.getElementById('domain-input-' + domainName);
      var ddnsInput = document.getElementById('ddns-input-' + domainName);
      var statusEl = document.getElementById('domain-save-status-' + domainName);
      var domainVal = domainInput ? domainInput.value.trim() : '';
      var ddnsVal = ddnsInput ? ddnsInput.value.trim() : '';

      if (!domainVal) {
        if (statusEl) { statusEl.textContent = '⚠ Enter a domain first'; statusEl.style.color = 'var(--red)'; }
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Saving…';
      if (statusEl) { statusEl.textContent = ''; }

      try {
        await apiFetch('/api/domains/set', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ domain_name: domainName, domain: domainVal, ddns_url: ddnsVal }),
        });
        if (statusEl) { statusEl.textContent = '✓ Saved'; statusEl.style.color = 'var(--green)'; }
      } catch (err) {
        if (statusEl) { statusEl.textContent = '⚠ ' + err.message; statusEl.style.color = 'var(--red)'; }
      }

      btn.disabled = false;
      btn.textContent = 'Save';
    });
  });

  // Wire save button for SSL email
  body.querySelectorAll('[data-save-email]').forEach(function(btn) {
    btn.addEventListener('click', async function() {
      var emailInput = document.getElementById('ssl-email-input');
      var statusEl = document.getElementById('domain-save-status-email');
      var emailVal = emailInput ? emailInput.value.trim() : '';

      if (!emailVal) {
        if (statusEl) { statusEl.textContent = '⚠ Enter an email first'; statusEl.style.color = 'var(--red)'; }
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Saving…';
      if (statusEl) { statusEl.textContent = ''; }

      try {
        await apiFetch('/api/domains/set-email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: emailVal }),
        });
        if (statusEl) { statusEl.textContent = '✓ Saved'; statusEl.style.color = 'var(--green)'; }
      } catch (err) {
        if (statusEl) { statusEl.textContent = '⚠ ' + err.message; statusEl.style.color = 'var(--red)'; }
      }

      btn.disabled = false;
      btn.textContent = 'Save';
    });
  });
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

// ── Step 4: Complete ──────────────────────────────────────────────

async function completeOnboarding() {
  var btn = document.getElementById("step-4-finish");
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
  var migrationContinue = document.getElementById("migration-password-continue");
  if (migrationContinue) migrationContinue.addEventListener("click", async function() {
    migrationContinue.disabled = true;
    migrationContinue.textContent = "Continuing…";
    setStatus("migration-password-status", "Saving acknowledgement…", "info");
    try {
      await apiFetch("/api/migration/password-acknowledge", { method: "POST" });
      _migrationOccurred = true;
      updateCompleteChecklist();
      showStep1FromMigration();
    } catch (err) {
      setStatus("migration-password-status", "⚠ " + err.message, "error");
      migrationContinue.disabled = false;
      migrationContinue.textContent = "I've written it down — Continue →";
    }
  });

  // Step 1 → next
  var s1next = document.getElementById("step-1-next");
  if (s1next) s1next.addEventListener("click", function() { showStep(nextStep(1)); });

  // Step 2 → 3 (save timezone/locale first)
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

  // Step 4: finish
  var s4finish = document.getElementById("step-4-finish");
  if (s4finish) s4finish.addEventListener("click", completeOnboarding);

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

  try {
    var migration = await apiFetch("/api/migration/password-status");
    if (migration && migration.pending) {
      updateCompleteChecklist();
      showMigrationStep(migration.password || "");
      return;
    }
  } catch (_) {}

  updateCompleteChecklist();
  showStep(1);
  loadStep1();
});
