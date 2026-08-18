"use strict";

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
  if (health === "syncing")         return "syncing";
  if (STATUS_LOADING_STATES.has(health)) return "loading";
  if (health === "checking_reachability") return "checking-reachability";
  return "unknown";
}

function statusText(health, enabled) {
  if (!enabled) return "Disabled";
  if (health === "healthy")         return "Active";
  if (health === "needs_attention") return "Needs Attention";
  if (health === "active")          return "Active";
  if (health === "inactive")        return "Inactive";
  if (health === "failed")          return "Failed";
  if (health === "syncing")         return "Syncing\u2026";
  if (!health || health === "unknown") return "Unknown";
  if (STATUS_LOADING_STATES.has(health)) return health;
  if (health === "checking_reachability") return "Checking\u2026";
  return health;
}

function escHtml(str) {
  return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function linkify(str) {
  return escHtml(str).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" class="creds-link">$1</a>');
}

// ── Router port-forwarding guide ──────────────────────────────────
// Whether a port is truly reachable can only be judged from OUTSIDE the
// network, so we never show a local "ready" verdict here. We only tell the
// user exactly what to enter in their router.

// Render the protocol cell so TCP / UDP / both is unmistakable.
function portProtocolHtml(protocol) {
  var p = String(protocol || "TCP").toUpperCase();
  var isTcp = p.indexOf("TCP") !== -1;
  var isUdp = p.indexOf("UDP") !== -1;
  if (isTcp && isUdp) {
    return '<span class="port-proto-badge port-proto-badge--both">TCP + UDP</span>' +
      '<span class="port-proto-note">both required</span>';
  }
  if (isUdp) return '<span class="port-proto-badge port-proto-badge--udp">UDP</span>';
  return '<span class="port-proto-badge port-proto-badge--tcp">TCP</span>';
}

// ports: [{ port, protocol, description }]
// opts:  { internalIp, serviceName, tableClass, introClass, noteClass }
function renderPortForwardGuideHtml(ports, opts) {
  opts = opts || {};
  var tableClass = opts.tableClass || "port-req-table";
  var introClass = opts.introClass || "port-req-intro";
  var noteClass  = opts.noteClass  || "port-req-hint";
  var ipHtml = opts.internalIp
    ? '<code class="port-req-internal-ip">' + escHtml(opts.internalIp) + '</code>'
    : 'this computer&rsquo;s <strong>internal IP</strong> (shown as &ldquo;Internal IP&rdquo; at the top of the Hub dashboard)';

  var rows = (ports || []).map(function(p) {
    return '<tr>' +
      '<td class="port-req-port">' + escHtml(p.port) + '</td>' +
      '<td class="port-req-proto">' + portProtocolHtml(p.protocol) + '</td>' +
      '<td class="port-req-desc">' + escHtml(p.description || "") + '</td>' +
      '</tr>';
  }).join("");

  var forWhat = opts.serviceName
    ? 'For <strong>' + escHtml(opts.serviceName) + '</strong> to be reachable from outside your home network, open'
    : 'Open';

  return '<p class="' + introClass + '">' +
      forWhat + ' the ports below in your router&rsquo;s <strong>port forwarding</strong> settings ' +
      'and point them at ' + ipHtml + '.' +
    '</p>' +
    '<ul class="port-req-steps">' +
      '<li>Set the <strong>internal (private) port</strong> and the <strong>external (public) port</strong> to the <strong>same number</strong>.</li>' +
      '<li>Match the <strong>protocol</strong> exactly — a rule set to TCP will not pass UDP traffic. Where the table says <strong>TCP + UDP</strong>, create both rules (or pick &ldquo;Both&rdquo;/&ldquo;TCP/UDP&rdquo; if your router offers it).</li>' +
      '<li>For a range such as <strong>30000-40000</strong>, use your router&rsquo;s port-range fields — start 30000, end 40000 — rather than one rule per port.</li>' +
    '</ul>' +
    '<table class="' + tableClass + '">' +
      '<thead><tr><th>Port(s)</th><th>Protocol</th><th>Used for</th></tr></thead>' +
      '<tbody>' + rows + '</tbody>' +
    '</table>' +
    '<p class="' + noteClass + '">' +
      '📱 <strong>How to confirm it worked:</strong> forwarding happens on your router, so it can only be verified from outside your network. ' +
      'Turn Wi-Fi off on your phone and open the service over mobile data — if it loads, your ports are open.' +
    '</p>';
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

// Avoid issuing multiple redirects when several startup requests discover an
// expired session at the same time.
let _authRedirectInProgress = false;

async function apiFetch(path, options) {
  const res = await fetch(path, options || {});
  if (res.status === 401) {
    if (!_authRedirectInProgress) {
      _authRedirectInProgress = true;
      window.location.replace("/login");
    }
    throw new Error("Unauthenticated");
  }
  if (!res.ok) {
    let detail = res.status + " " + res.statusText;
    try {
      const body = await res.json();
      if (body && body.detail) {
        if (typeof body.detail === "string") {
          detail = body.detail;
        } else if (body.detail && typeof body.detail.message === "string") {
          detail = body.detail.message;
        }
      } else if (body && typeof body.message === "string") {
        detail = body.message;
      } else if (body && typeof body.error === "string") {
        detail = body.error;
      }
    } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}

async function apiFetchWithTimeout(path, options, timeoutMs) {
  var controller = new AbortController();
  var fetchOptions = Object.assign({}, options || {});
  fetchOptions.signal = controller.signal;
  var timer = setTimeout(function() { controller.abort(); }, timeoutMs);
  try {
    return await apiFetch(path, fetchOptions);
  } catch (err) {
    if (controller.signal.aborted) {
      var timeoutError = new Error("Request timed out");
      timeoutError.name = "TimeoutError";
      throw timeoutError;
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
