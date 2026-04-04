/* Sovran_SystemsOS Hub — Vanilla JS Frontend
   v7 — Status-only dashboard + Tech Support + Feature Manager */
"use strict";

const POLL_INTERVAL_SERVICES    = 5000;
const POLL_INTERVAL_UPDATES     = 1800000;
const UPDATE_POLL_INTERVAL      = 2000;
const REBOOT_CHECK_INTERVAL     = 5000;
const SUPPORT_TIMER_INTERVAL    = 1000;

const CATEGORY_ORDER = [
  "infrastructure",
  "bitcoin-base",
  "bitcoin-apps",
  "communication",
  "apps",
  "nostr",
];

const FEATURE_SUBCATEGORY_LABELS = {
  "infrastructure": "🔧 Infrastructure",
  "bitcoin":        "₿ Bitcoin",
  "communication":  "💬 Communication",
  "nostr":          "📡 Nostr",
};

const FEATURE_SUBCATEGORY_ORDER = ["infrastructure", "bitcoin", "communication", "nostr"];

const STATUS_LOADING_STATES = new Set([
  "reloading", "activating", "deactivating", "maintenance",
]);

// ── State ─────────────────────────────────────────────────────────

let _servicesCache    = [];
let _categoryLabels   = {};
let _updateLog        = "";
let _updatePollTimer  = null;
let _updateLogOffset  = 0;
let _serverWasDown    = false;
let _updateFinished   = false;
let _supportTimerInt      = null;
let _supportEnabledAt     = null;
let _supportStatus        = null;   // last fetched /api/support/status payload
let _walletUnlockTimerInt = null;
let _cachedExternalIp = null;

// Feature Manager state
let _featuresData         = null;
let _rebuildLog           = "";
let _rebuildLogOffset     = 0;
let _rebuildPollTimer     = null;
let _rebuildFinished      = false;
let _rebuildServerDown    = false;
let _pendingToggle        = null; // {feature, extra} waiting for domain/confirm
let _rebuildFeatureName   = "";
let _rebuildIsEnabling    = true;

// ── DOM refs ──────────────────────────────────────────────────────

const $tilesArea      = document.getElementById("tiles-area");
const $sidebarSupport = document.getElementById("sidebar-support");
const $sidebarFeatures = document.getElementById("sidebar-features");
const $updateBtn      = document.getElementById("btn-update");
const $updateBadge    = document.getElementById("update-badge");
const $refreshBtn     = document.getElementById("btn-refresh");
const $internalIp     = document.getElementById("ip-internal");
const $externalIp     = document.getElementById("ip-external");

const $modal          = document.getElementById("update-modal");
const $modalSpinner   = document.getElementById("modal-spinner");
const $modalStatus    = document.getElementById("modal-status");
const $modalLog       = document.getElementById("modal-log");
const $btnReboot      = document.getElementById("btn-reboot");
const $btnSave        = document.getElementById("btn-save-report");
const $btnCloseModal  = document.getElementById("btn-close-modal");

const $rebootOverlay  = document.getElementById("reboot-overlay");

const $credsModal     = document.getElementById("creds-modal");
const $credsTitle     = document.getElementById("creds-modal-title");
const $credsBody      = document.getElementById("creds-body");
const $credsCloseBtn  = document.getElementById("creds-close-btn");

const $supportModal     = document.getElementById("support-modal");
const $supportBody      = document.getElementById("support-body");
const $supportCloseBtn  = document.getElementById("support-close-btn");

// Feature Manager — rebuild modal
const $rebuildModal    = document.getElementById("rebuild-modal");
const $rebuildSpinner  = document.getElementById("rebuild-spinner");
const $rebuildStatus   = document.getElementById("rebuild-status");
const $rebuildLog      = document.getElementById("rebuild-log");
const $rebuildReboot   = document.getElementById("rebuild-reboot-btn");
const $rebuildSave     = document.getElementById("rebuild-save-report");
const $rebuildClose    = document.getElementById("rebuild-close-btn");

// Feature Manager — domain setup modal
const $domainSetupModal = document.getElementById("domain-setup-modal");
const $domainSetupTitle = document.getElementById("domain-setup-title");
const $domainSetupBody  = document.getElementById("domain-setup-body");
const $domainSetupClose = document.getElementById("domain-setup-close-btn");

// Feature Manager — SSL email modal
const $sslEmailModal  = document.getElementById("ssl-email-modal");
const $sslEmailInput  = document.getElementById("ssl-email-input");
const $sslEmailSave   = document.getElementById("ssl-email-save-btn");
const $sslEmailCancel = document.getElementById("ssl-email-cancel-btn");
const $sslEmailClose  = document.getElementById("ssl-email-close-btn");

// Feature Manager — confirm modal
const $featureConfirmModal   = document.getElementById("feature-confirm-modal");
const $featureConfirmMsg     = document.getElementById("feature-confirm-message");
const $featureConfirmOk      = document.getElementById("feature-confirm-ok-btn");
const $featureConfirmCancel  = document.getElementById("feature-confirm-cancel-btn");
const $featureConfirmClose   = document.getElementById("feature-confirm-close-btn");

// Port Requirements modal
const $portReqModal  = document.getElementById("port-requirements-modal");
const $portReqBody   = document.getElementById("port-req-body");
const $portReqClose  = document.getElementById("port-req-close-btn");

// System status banner
// (removed — health is now shown per-tile via the composite health field)

// ── Helpers ───────────────────────────────────────────────────────

function tileId(svc) { return svc.unit + "::" + svc.name; }

function statusClass(health) {
  if (!health) return "unknown";
  if (health === "healthy")         return "active";
  if (health === "needs_attention") return "needs-attention";
  if (health === "active")          return "active";   // backwards compat
  if (health === "inactive")        return "inactive";
  if (health === "failed")          return "failed";
  if (health === "disabled")        return "disabled";
  if (STATUS_LOADING_STATES.has(health)) return "loading";
  return "unknown";
}

function statusText(health, enabled) {
  if (!enabled) return "Disabled";
  if (health === "healthy")         return "Active";
  if (health === "needs_attention") return "Needs Attention";
  if (health === "active")          return "Active";
  if (health === "inactive")        return "Inactive";
  if (health === "failed")          return "Failed";
  if (!health || health === "unknown") return "Unknown";
  if (STATUS_LOADING_STATES.has(health)) return health;
  return health;
}

function escHtml(str) {
  return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function linkify(str) {
  return escHtml(str).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" class="creds-link">$1</a>');
}

function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return h + "h " + m + "m " + s + "s";
  if (m > 0) return m + "m " + s + "s";
  return s + "s";
}

// ── Fetch wrappers ────────────────────────────────────────────────

async function apiFetch(path, options) {
  const res = await fetch(path, options || {});
  if (!res.ok) {
    let detail = res.status + " " + res.statusText;
    try { const body = await res.json(); if (body && body.detail) detail = body.detail; } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}

// ── Render: initial build ─────────────────────────────────────────

function buildTiles(services, categoryLabels) {
  _servicesCache = services;
  var grouped = {};
  var supportServices = [];
  for (var i = 0; i < services.length; i++) {
    var svc = services[i];
    // Support tiles go to the sidebar, not the main grid
    if (svc.category === "support" || svc.type === "support") {
      supportServices.push(svc);
      continue;
    }
    var cat = svc.category || "other";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(svc);
  }
  renderSidebarSupport(supportServices);
  $tilesArea.innerHTML = "";
  var orderedKeys = CATEGORY_ORDER.filter(function(k) { return grouped[k]; });
  Object.keys(grouped).forEach(function(k) {
    if (orderedKeys.indexOf(k) === -1) orderedKeys.push(k);
  });
  for (var j = 0; j < orderedKeys.length; j++) {
    var catKey = orderedKeys[j];
    var entries = grouped[catKey];
    if (!entries || entries.length === 0) continue;
    var label = categoryLabels[catKey] || catKey;
    var section = document.createElement("div");
    section.className = "category-section";
    section.dataset.category = catKey;
    section.innerHTML = '<div class="section-header">' + escHtml(label) + '</div><hr class="section-divider" /><div class="tiles-grid" data-cat="' + escHtml(catKey) + '"></div>';
    var grid = section.querySelector(".tiles-grid");
    for (var k = 0; k < entries.length; k++) {
      grid.appendChild(buildTile(entries[k]));
    }
    $tilesArea.appendChild(section);
  }
  if ($tilesArea.children.length === 0) {
    $tilesArea.innerHTML = '<div class="empty-state"><p>No services configured.</p></div>';
  }
}

function renderSidebarSupport(supportServices) {
  $sidebarSupport.innerHTML = "";
  for (var i = 0; i < supportServices.length; i++) {
    var svc = supportServices[i];
    var btn = document.createElement("button");
    btn.className = "sidebar-support-btn";
    btn.innerHTML =
      '<span class="sidebar-support-icon">🛟</span>' +
      '<span class="sidebar-support-text">' +
        '<span class="sidebar-support-title">' + escHtml(svc.name || "Tech Support") + '</span>' +
        '<span class="sidebar-support-hint">Click for help</span>' +
      '</span>';
    btn.addEventListener("click", function() { openSupportModal(); });
    $sidebarSupport.appendChild(btn);
  }
  if (supportServices.length > 0) {
    var hr = document.createElement("hr");
    hr.className = "sidebar-divider";
    $sidebarSupport.appendChild(hr);
  }
}

function buildTile(svc) {
  var isSupport = svc.type === "support";
  var sc = statusClass(svc.health || svc.status);
  var st = statusText(svc.health || svc.status, svc.enabled);
  var dis = !svc.enabled;

  var tile = document.createElement("div");
  tile.className = "service-tile" + (dis ? " disabled" : "") + (isSupport ? " support-tile" : "");
  tile.dataset.unit = svc.unit;
  tile.dataset.tileId = tileId(svc);
  if (dis) tile.title = svc.name + " is not enabled in custom.nix";

  if (isSupport) {
    tile.innerHTML = '<img class="tile-icon" src="/static/icons/' + escHtml(svc.icon) + '.svg" alt="' + escHtml(svc.name) + '" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"><div class="tile-icon-fallback" style="display:none">?</div><div class="tile-name">' + escHtml(svc.name) + '</div><div class="tile-status"><span class="support-status-label">Click for help</span></div>';
    tile.style.cursor = "pointer";
    tile.addEventListener("click", function() { openSupportModal(); });
    return tile;
  }

  tile.innerHTML = '<img class="tile-icon" src="/static/icons/' + escHtml(svc.icon) + '.svg" alt="' + escHtml(svc.name) + '" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"><div class="tile-icon-fallback" style="display:none">?</div><div class="tile-name">' + escHtml(svc.name) + '</div><div class="tile-status"><span class="status-dot ' + sc + '"></span><span class="status-text">' + st + '</span></div>';

  tile.style.cursor = "pointer";
  tile.addEventListener("click", function() {
    openServiceDetailModal(svc.unit, svc.name);
  });

  return tile;
}

// ── Render: live update ───────────────────────────────────────────

function updateTiles(services) {
  _servicesCache = services;
  for (var i = 0; i < services.length; i++) {
    var svc = services[i];
    if (svc.type === "support") continue;
    var id = CSS.escape(tileId(svc));
    var tile = $tilesArea.querySelector('.service-tile[data-tile-id="' + id + '"]');
    if (!tile) continue;
    var sc = statusClass(svc.health || svc.status);
    var st = statusText(svc.health || svc.status, svc.enabled);
    var dot = tile.querySelector(".status-dot");
    var text = tile.querySelector(".status-text");
    if (dot) dot.className = "status-dot " + sc;
    if (text) text.textContent = st;
  }
}

// ── Service polling ───────────────────────────────────────────────

var _firstLoad = true;

async function refreshServices() {
  try {
    var services = await apiFetch("/api/services");
    if (_firstLoad) { buildTiles(services, _categoryLabels); _firstLoad = false; }
    else { updateTiles(services); }
  } catch (err) { console.warn("Failed to fetch services:", err); }
}

// ── Network IPs ───────────────────────────────────────────────────

async function loadNetwork() {
  try {
    var data = await apiFetch("/api/network");
    if ($internalIp) $internalIp.textContent = data.internal_ip || "—";
    if ($externalIp) $externalIp.textContent = data.external_ip || "—";
    _cachedExternalIp = data.external_ip || "unavailable";
  } catch (_) {
    if ($internalIp) $internalIp.textContent = "—";
    if ($externalIp) $externalIp.textContent = "—";
  }
}

// ── Update check ──────────────────────────────────────────────────

async function checkUpdates() {
  try {
    var data = await apiFetch("/api/updates/check");
    var hasUpdates = !!data.available;
    if ($updateBadge) $updateBadge.classList.toggle("visible", hasUpdates);
    if ($updateBtn) $updateBtn.classList.toggle("has-updates", hasUpdates);
  } catch (_) {}
}

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

async function openServiceDetailModal(unit, name) {
  if (!$credsModal) return;
  if ($credsTitle) $credsTitle.textContent = name;
  if ($credsBody) $credsBody.innerHTML = '<p class="creds-loading">Loading…</p>';
  $credsModal.classList.add("open");

  try {
    var data = await apiFetch("/api/service-detail/" + encodeURIComponent(unit));
    var html = "";

    // Section A: Description
    if (data.description) {
      html += '<div class="svc-detail-section">' +
        '<p class="svc-detail-desc">' + escHtml(data.description) + '</p>' +
        '</div>';
    }

    // Section B: Status
    var sc = statusClass(data.health || data.status);
    var st = statusText(data.health || data.status, data.enabled);
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
      html += '<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">🔧 Addon Feature</div>' +
        '<p class="svc-detail-desc">This is an optional addon feature. You can enable or disable it at any time.</p>' +
        '<div class="svc-detail-addon-row">' +
          '<span class="svc-detail-addon-status ' + addonStatusCls + '">' + addonStatusLabel + '</span>' +
          '<button class="' + addonBtnCls + '" id="svc-detail-addon-btn">' + escHtml(addonBtnLabel) + '</button>' +
        '</div>' +
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

async function openCredsModal(unit, name) {
  if (!$credsModal) return;
  if ($credsTitle) $credsTitle.textContent = name + " — Connection Info";
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

function openMatrixCreateUserModal(unit, name) {
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
    openServiceDetailModal(unit, name);
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

function openMatrixChangePasswordModal(unit, name) {
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
    openServiceDetailModal(unit, name);
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

function closeCredsModal() { if ($credsModal) $credsModal.classList.remove("open"); }

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

// ── Update modal ──────────────────────────────────────────────────

function openUpdateModal() {
  if (!$modal) return;
  _updateLog = "";
  _updateLogOffset = 0;
  _serverWasDown = false;
  _updateFinished = false;
  if ($modalLog) $modalLog.textContent = "";
  if ($modalStatus) $modalStatus.textContent = "Starting update…";
  if ($modalSpinner) $modalSpinner.classList.add("spinning");
  if ($btnReboot) $btnReboot.style.display = "none";
  if ($btnSave) $btnSave.style.display = "none";
  if ($btnCloseModal) $btnCloseModal.disabled = true;
  $modal.classList.add("open");
  startUpdate();
}

function closeUpdateModal() {
  if (!$modal) return;
  $modal.classList.remove("open");
  stopUpdatePoll();
}

function appendLog(text) {
  if (!text) return;
  _updateLog += text;
  if ($modalLog) { $modalLog.textContent += text; $modalLog.scrollTop = $modalLog.scrollHeight; }
}

function startUpdate() {
  fetch("/api/updates/run", { method: "POST" })
    .then(function(response) {
      if (!response.ok) return response.text().then(function(t) { throw new Error(t); });
      return response.json();
    })
    .then(function(data) {
      if (data.status === "already_running") appendLog("[Update already in progress, attaching…]\n\n");
      if ($modalStatus) $modalStatus.textContent = "Updating…";
      startUpdatePoll();
    })
    .catch(function(err) {
      appendLog("[Error: failed to start update — " + err + "]\n");
      onUpdateDone(false);
    });
}

function startUpdatePoll() {
  pollUpdateStatus();
  _updatePollTimer = setInterval(pollUpdateStatus, UPDATE_POLL_INTERVAL);
}

function stopUpdatePoll() {
  if (_updatePollTimer) { clearInterval(_updatePollTimer); _updatePollTimer = null; }
}

async function pollUpdateStatus() {
  if (_updateFinished) return;
  try {
    var data = await apiFetch("/api/updates/status?offset=" + _updateLogOffset);
    if (_serverWasDown) { _serverWasDown = false; appendLog("[Server reconnected]\n"); if ($modalStatus) $modalStatus.textContent = "Updating…"; }
    if (data.log) appendLog(data.log);
    _updateLogOffset = data.offset;
    if (data.running) return;
    _updateFinished = true;
    stopUpdatePoll();
    if (data.result === "success") onUpdateDone(true);
    else onUpdateDone(false);
  } catch (err) {
    if (!_serverWasDown) { _serverWasDown = true; appendLog("\n[Server restarting — waiting for it to come back…]\n"); if ($modalStatus) $modalStatus.textContent = "Server restarting…"; }
  }
}

function onUpdateDone(success) {
  if ($modalSpinner) $modalSpinner.classList.remove("spinning");
  if ($btnCloseModal) $btnCloseModal.disabled = false;
  if (success) {
    if ($modalStatus) $modalStatus.textContent = "✓ Update complete";
    if ($btnReboot) $btnReboot.style.display = "inline-flex";
  } else {
    if ($modalStatus) $modalStatus.textContent = "✗ Update failed";
    if ($btnSave) $btnSave.style.display = "inline-flex";
    if ($btnReboot) $btnReboot.style.display = "inline-flex";
  }
}

function saveErrorReport() {
  var blob = new Blob([_updateLog], { type: "text/plain" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = "sovran-update-error-" + new Date().toISOString().split(".")[0].replace(/:/g, "-") + ".txt";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Reboot ────────────────────────────────────────────────────────

function doReboot() {
  if ($modal) $modal.classList.remove("open");
  if ($rebuildModal) $rebuildModal.classList.remove("open");
  stopUpdatePoll();
  stopRebuildPoll();
  if ($rebootOverlay) $rebootOverlay.classList.add("visible");
  fetch("/api/reboot", { method: "POST" }).catch(function() {});
  setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
}

function waitForServerReboot() {
  fetch("/api/config", { cache: "no-store" })
    .then(function(res) {
      if (res.ok) window.location.reload();
      else setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL);
    })
    .catch(function() { setTimeout(waitForServerReboot, REBOOT_CHECK_INTERVAL); });
}

// ── Rebuild modal ─────────────────────────────────────────────────

function openRebuildModal() {
  if (!$rebuildModal) return;
  _rebuildLog = "";
  _rebuildLogOffset = 0;
  _rebuildServerDown = false;
  _rebuildFinished = false;
  if ($rebuildLog) { $rebuildLog.textContent = ""; $rebuildLog.style.display = "none"; }
  var action = _rebuildIsEnabling ? "Enabling" : "Disabling";
  var label = _rebuildFeatureName || "feature";
  if ($rebuildStatus) $rebuildStatus.textContent = action + " " + label + "…";
  if ($rebuildSpinner) $rebuildSpinner.classList.add("spinning");
  if ($rebuildReboot) $rebuildReboot.style.display = "none";
  if ($rebuildSave) $rebuildSave.style.display = "none";
  if ($rebuildClose) $rebuildClose.disabled = true;
  $rebuildModal.classList.add("open");
  // Delay first poll slightly to let the rebuild service start and clear stale log
  setTimeout(startRebuildPoll, 1500);
}

function closeRebuildModal() {
  if ($rebuildModal) $rebuildModal.classList.remove("open");
  stopRebuildPoll();
}

function appendRebuildLog(text) {
  if (!text) return;
  _rebuildLog += text;
  // Log is collected silently for error reports — not displayed to user
}

function startRebuildPoll() {
  pollRebuildStatus();
  _rebuildPollTimer = setInterval(pollRebuildStatus, UPDATE_POLL_INTERVAL);
}

function stopRebuildPoll() {
  if (_rebuildPollTimer) { clearInterval(_rebuildPollTimer); _rebuildPollTimer = null; }
}

async function pollRebuildStatus() {
  if (_rebuildFinished) return;
  try {
    var data = await apiFetch("/api/rebuild/status?offset=" + _rebuildLogOffset);
    if (_rebuildServerDown) { _rebuildServerDown = false; }
    if (data.log) appendRebuildLog(data.log);
    _rebuildLogOffset = data.offset;
    if (data.running) return;
    _rebuildFinished = true;
    stopRebuildPoll();
    onRebuildDone(data.result === "success");
  } catch (err) {
    if (!_rebuildServerDown) { _rebuildServerDown = true; if ($rebuildStatus) $rebuildStatus.textContent = "Applying changes…"; }
  }
}

function onRebuildDone(success) {
  if ($rebuildSpinner) $rebuildSpinner.classList.remove("spinning");
  if ($rebuildClose) $rebuildClose.disabled = false;
  if (success) {
    if ($rebuildStatus) $rebuildStatus.textContent = "✓ Done";
    // Auto-reload the page after a short delay so tiles and toggles reflect the new state
    setTimeout(function() { window.location.reload(); }, 1200);
  } else {
    if ($rebuildStatus) $rebuildStatus.textContent = "✗ Something went wrong";
    if ($rebuildSave) $rebuildSave.style.display = "inline-flex";
    if ($rebuildReboot) $rebuildReboot.style.display = "inline-flex";
  }
}

function saveRebuildErrorReport() {
  var blob = new Blob([_rebuildLog], { type: "text/plain" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = "sovran-rebuild-error-" + new Date().toISOString().split(".")[0].replace(/:/g, "-") + ".txt";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

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

  var externalIp = _cachedExternalIp || "your external IP";

  $domainSetupBody.innerHTML =
    '<div class="domain-setup-intro">' +
    '<p><strong>Before continuing:</strong></p>' +
    '<ol>' +
    '<li>Create an account at <a href="https://njal.la" target="_blank" rel="noopener noreferrer" style="color:var(--accent-color);">https://njal.la</a></li>' +
    '<li>Purchase a new domain on Njal.la, or create a subdomain from a domain you already own. Tip: Subdomains are free to create — you only need to purchase one domain, and you can add as many subdomains as you need at no extra cost.</li>' +
    '<li>In the Njal.la web interface, create a <strong>Dynamic</strong> record pointing to this machine\'s external IP address:<br>' +
    '<span style="display:inline-block;margin-top:4px;padding:4px 10px;background:var(--card-color);border:1px solid var(--border-color);border-radius:6px;font-family:monospace;font-size:1em;font-weight:700;">' + escHtml(externalIp) + '</span></li>' +
    '<li>Njal.la will give you a curl command like:<br>' +
    '<code style="font-size:0.8em;">curl &quot;https://njal.la/update/?h=sub.domain.com&amp;k=abc123&amp;auto&quot;</code></li>' +
    '<li>Enter the subdomain and paste that curl command below</li>' +
    '</ol>' +
    '</div>' +
    '<div class="domain-field-group"><label class="domain-field-label" for="domain-subdomain-input">Subdomain (e.g. myservice.example.com):</label><input class="domain-field-input" type="text" id="domain-subdomain-input" placeholder="myservice.example.com" /></div>' +
    '<div class="domain-field-group"><label class="domain-field-label" for="domain-ddns-input">Njal.la Dynamic DNS Update Command:</label><input class="domain-field-input" type="text" id="domain-ddns-input" placeholder="curl &quot;https://njal.la/update/?h=myservice.example.com&amp;k=abc123&amp;auto&quot;" /><p class="domain-field-hint">ℹ Paste the full curl command from your Njal.la dashboard\'s Dynamic record</p></div>' +
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
      saveBtn.textContent = "Save & Enable";
      alert("Failed to save domain. Please try again.");
    }
  });

  $domainSetupModal.classList.add("open");
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

  // Show loading state while fetching port status
  $portReqBody.innerHTML =
    '<p class="port-req-intro">Checking port status for <strong>' + escHtml(featureName) + '</strong>…</p>' +
    '<p class="port-req-hint">Detecting which ports are open on this machine…</p>';

  $portReqModal.classList.add("open");

  // Fetch live port status from local system commands (no external calls)
  fetch("/api/ports/status", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ports: ports }),
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var internalIp = (data.internal_ip && data.internal_ip !== "unavailable")
        ? data.internal_ip : null;
      var portStatuses = {};
      (data.ports || []).forEach(function(p) {
        portStatuses[p.port + "/" + p.protocol] = p.status;
      });

      var rows = ports.map(function(p) {
        var key = p.port + "/" + p.protocol;
        var status = portStatuses[key] || "unknown";
        var statusHtml;
        if (status === "listening") {
          statusHtml = '<span class="port-status-listening" title="Service is running and firewall allows this port">🟢 Listening</span>';
        } else if (status === "firewall_open") {
          statusHtml = '<span class="port-status-open" title="Firewall allows this port but no service is bound yet">🟡 Open (idle)</span>';
        } else if (status === "closed") {
          statusHtml = '<span class="port-status-closed" title="Firewall blocks this port and/or nothing is listening">🔴 Closed</span>';
        } else {
          statusHtml = '<span class="port-status-unknown" title="Status could not be determined">⚪ Unknown</span>';
        }
        return '<tr>' +
          '<td class="port-req-port">' + escHtml(p.port) + '</td>' +
          '<td class="port-req-proto">' + escHtml(p.protocol) + '</td>' +
          '<td class="port-req-desc">' + escHtml(p.description) + '</td>' +
          '<td class="port-req-status">' + statusHtml + '</td>' +
          '</tr>';
      }).join("");

      var ipLine = internalIp
        ? '<p class="port-req-intro">Forward each port below <strong>to this machine\'s internal IP: <code class="port-req-internal-ip">' + escHtml(internalIp) + '</code></strong></p>'
        : "<p class=\"port-req-intro\">Forward each port below to this machine's internal LAN IP in your router's port forwarding settings.</p>";

      $portReqBody.innerHTML =
        '<p class="port-req-intro"><strong>Port Forwarding Required</strong></p>' +
        '<p class="port-req-intro">For <strong>' + escHtml(featureName) + "</strong> to work with clients outside your local network, " +
        "you must configure <strong>port forwarding</strong> in your router's admin panel.</p>" +
        ipLine +
        '<table class="port-req-table">' +
        '<thead><tr><th>Port(s)</th><th>Protocol</th><th>Purpose</th><th>Status</th></tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
        '</table>' +
        "<p class=\"port-req-hint\"><strong>How to verify:</strong> Router-side forwarding cannot be checked from inside your network. " +
        "To confirm ports are forwarded correctly, test from a device on a different network (e.g. a phone on mobile data) " +
        "or check your router's port forwarding page.</p>" +
        '<p class="port-req-hint">ℹ Search "<em>how to set up port forwarding on [your router model]</em>" for step-by-step instructions.</p>' +
        '<div class="domain-field-actions">' +
        '<button class="btn btn-close-modal" id="port-req-dismiss-btn">Dismiss</button>' +
        continueBtn +
        '</div>';

      document.getElementById("port-req-dismiss-btn").addEventListener("click", function() {
        closePortRequirementsModal();
      });

      if (onContinue) {
        document.getElementById("port-req-continue-btn").addEventListener("click", function() {
          closePortRequirementsModal();
          onContinue();
        });
      }
    })
    .catch(function() {
      // Fallback: show static table without status column if fetch fails
      var rows = ports.map(function(p) {
        return '<tr><td class="port-req-port">' + escHtml(p.port) + '</td>' +
          '<td class="port-req-proto">' + escHtml(p.protocol) + '</td>' +
          '<td class="port-req-desc">' + escHtml(p.description) + '</td></tr>';
      }).join("");

      $portReqBody.innerHTML =
        '<p class="port-req-intro"><strong>Port Forwarding Required</strong></p>' +
        '<p class="port-req-intro">For <strong>' + escHtml(featureName) + '</strong> to work with clients outside your local network, ' +
        'you must configure <strong>port forwarding</strong> in your router\'s admin panel and forward each port below to this machine\'s internal LAN IP.</p>' +
        '<table class="port-req-table">' +
        '<thead><tr><th>Port(s)</th><th>Protocol</th><th>Purpose</th></tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
        '</table>' +
        '<p class="port-req-hint">ℹ Search "<em>how to set up port forwarding on [your router model]</em>" for step-by-step instructions.</p>' +
        '<div class="domain-field-actions">' +
        '<button class="btn btn-close-modal" id="port-req-dismiss-btn">Dismiss</button>' +
        continueBtn +
        '</div>';

      document.getElementById("port-req-dismiss-btn").addEventListener("click", function() {
        closePortRequirementsModal();
      });

      if (onContinue) {
        document.getElementById("port-req-continue-btn").addEventListener("click", function() {
          closePortRequirementsModal();
          onContinue();
        });
      }
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
    // Show port requirements notification if the feature has extra port needs
    var ports = feat.port_requirements || [];
    if (ports.length > 0) {
      openPortRequirementsModal(feat.name, ports, proceedAfterPortCheck);
    } else {
      proceedAfterPortCheck();
    }
  }

  if (conflictNames.length > 0) {
    var confirmMsg;
    if (feat.id === "bip110") {
      confirmMsg = "Only one Bitcoin node implementation can be active. Enabling Bitcoin Knots + BIP110 will disable Bitcoin Core (if active). Continue?";
    } else if (feat.id === "bitcoin-core") {
      confirmMsg = "Only one Bitcoin node implementation can be active. Enabling Bitcoin Core will disable Bitcoin Knots + BIP110 (if active). Continue?";
    } else {
      confirmMsg = "This will disable " + conflictNames.join(", ") + ". Continue?";
    }
    openFeatureConfirm(confirmMsg, proceedAfterConflictCheck);
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

// ── Event listeners ───────────────────────────────────────────────

if ($updateBtn) $updateBtn.addEventListener("click", openUpdateModal);
if ($refreshBtn) $refreshBtn.addEventListener("click", function() { refreshServices(); });
if ($btnCloseModal) $btnCloseModal.addEventListener("click", closeUpdateModal);
if ($btnReboot) $btnReboot.addEventListener("click", doReboot);
if ($btnSave) $btnSave.addEventListener("click", saveErrorReport);
if ($credsCloseBtn) $credsCloseBtn.addEventListener("click", closeCredsModal);
if ($supportCloseBtn) $supportCloseBtn.addEventListener("click", closeSupportModal);

// Rebuild modal
if ($rebuildClose) $rebuildClose.addEventListener("click", closeRebuildModal);
if ($rebuildReboot) $rebuildReboot.addEventListener("click", doReboot);
if ($rebuildSave) $rebuildSave.addEventListener("click", saveRebuildErrorReport);
if ($rebuildModal) $rebuildModal.addEventListener("click", function(e) { if (e.target === $rebuildModal) closeRebuildModal(); });

// Domain setup modal
if ($domainSetupClose) $domainSetupClose.addEventListener("click", closeDomainSetupModal);
if ($domainSetupModal) $domainSetupModal.addEventListener("click", function(e) { if (e.target === $domainSetupModal) closeDomainSetupModal(); });

// SSL Email modal
if ($sslEmailClose) $sslEmailClose.addEventListener("click", closeSslEmailModal);
if ($sslEmailCancel) $sslEmailCancel.addEventListener("click", closeSslEmailModal);
if ($sslEmailModal) $sslEmailModal.addEventListener("click", function(e) { if (e.target === $sslEmailModal) closeSslEmailModal(); });

// Feature confirm modal
if ($featureConfirmClose) $featureConfirmClose.addEventListener("click", closeFeatureConfirm);
if ($featureConfirmCancel) $featureConfirmCancel.addEventListener("click", closeFeatureConfirm);
if ($featureConfirmModal) $featureConfirmModal.addEventListener("click", function(e) { if (e.target === $featureConfirmModal) closeFeatureConfirm(); });

if ($modal) $modal.addEventListener("click", function(e) { if (e.target === $modal) closeUpdateModal(); });
if ($credsModal) $credsModal.addEventListener("click", function(e) { if (e.target === $credsModal) closeCredsModal(); });
if ($supportModal) $supportModal.addEventListener("click", function(e) { if (e.target === $supportModal) closeSupportModal(); });

// ── Init ──────────────────────────────────────────────────────────

async function init() {
  // Check onboarding status first — redirect to wizard if not complete
  try {
    var onboardingStatus = await apiFetch("/api/onboarding/status");
    if (!onboardingStatus.complete) {
      window.location.href = "/onboarding";
      return;
    }
  } catch (_) {
    // If we can't reach the endpoint, continue to normal dashboard
  }

  try {
    var cfg = await apiFetch("/api/config");
    if (cfg.category_order) {
      for (var i = 0; i < cfg.category_order.length; i++) {
        _categoryLabels[cfg.category_order[i][0]] = cfg.category_order[i][1];
      }
    }
    var badge = document.getElementById("role-badge");
    if (badge && cfg.role_label) badge.textContent = cfg.role_label;

    await refreshServices();
    loadNetwork();
    checkUpdates();

    setInterval(refreshServices, POLL_INTERVAL_SERVICES);
    setInterval(checkUpdates, POLL_INTERVAL_UPDATES);

    if (cfg.feature_manager) {
      loadFeatureManager();
    }
  } catch (_) {
    await refreshServices();
    loadNetwork();
    checkUpdates();
    setInterval(refreshServices, POLL_INTERVAL_SERVICES);
    setInterval(checkUpdates, POLL_INTERVAL_UPDATES);
  }
}

document.addEventListener("DOMContentLoaded", init);