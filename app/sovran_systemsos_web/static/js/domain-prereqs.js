/* Sovran_SystemsOS Hub — Shared domain-prerequisite instructions.

   SINGLE SOURCE OF TRUTH for the "you need a Njal.la domain + router port
   forwarding" guidance that must read identically everywhere it appears:

     • First-boot onboarding wizard (Server + Desktop role)
       — onboarding.js step 3
     • Feature-enable domain modal (Node role, and any role)
       — features.js openDomainSetupModal()
       (Lightning Wallet Connections / NWC, BTCPay Server, Haven, …)
     • Domain reconfigure / troubleshooting modal
       — features.js openDomainReconfigureModal()

   Keep these three surfaces word-for-word consistent: always edit this
   file, never fork the wording inline. Plain classic script (no modules) —
   both templates load it with a plain <script> tag. */
"use strict";

/* Escape helper local to this file so it is self-contained on both pages. */
function dpEsc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/* ── "What you'll need" intro ──────────────────────────────────────
   opts.serviceName — e.g. "Lightning Wallet Connections", or null for
   the multi-service (onboarding) wording.
   opts.hostExample — e.g. "lightning" → lightning.yourdomain.com */
function renderDomainNeedsHtml(opts) {
  var serviceName = opts.serviceName || null;
  var hostExample = dpEsc(opts.hostExample || "myservice");
  var html = "";

  if (serviceName) {
    html += "<p>To enable <strong>" + dpEsc(serviceName) + "</strong>, you'll need two things first:</p>";
    html += '<ol style="margin:8px 0 0 16px;padding:0;line-height:1.7;">';
    html += "<li><strong>A domain of your own from <a href=\"https://njal.la\" target=\"_blank\" rel=\"noopener noreferrer\" style=\"color:var(--accent-color);\">Njal.la</a></strong> "
      + "— privacy-friendly, no personal details required, accepts Bitcoin. "
      + dpEsc(serviceName) + " gets its own hostname: a subdomain (e.g. <code>" + hostExample + ".yourdomain.com</code>) "
      + "or a separate domain — your choice. Subdomains are free, and one domain can have many.</li>";
    html += "<li><strong>Access to your router</strong> — you'll forward ports <strong>80</strong> and <strong>443</strong> (TCP) "
      + "to this computer once. All domain-based services share these two ports; "
      + "they're required for HTTPS and SSL certificates.</li>";
    html += "</ol>";
  } else {
    html += "<p><strong>Each service below needs two things set up:</strong></p>";
    html += '<ol style="margin:8px 0 0 16px;padding:0;line-height:1.7;">';
    html += "<li><strong>A domain of your own from <a href=\"https://njal.la\" target=\"_blank\" rel=\"noopener noreferrer\" style=\"color:var(--accent-color);\">Njal.la</a></strong> "
      + "— privacy-friendly, no personal details required, accepts Bitcoin. "
      + "Each service gets its own hostname: its own subdomain (e.g. <code>" + hostExample + ".yourdomain.com</code>) "
      + "or a separate domain — your choice. Subdomains are free, and one domain can have many, "
      + "so a single domain can serve every service.</li>";
    html += "<li><strong>Access to your router</strong> — you'll forward ports <strong>80</strong> and <strong>443</strong> (TCP) "
      + "to this computer once. All domain-based services share these two ports; "
      + "they're required for HTTPS and SSL certificates.</li>";
    html += "</ol>";
  }
  return html;
}

/* ── "How to set it up at Njal.la" steps ───────────────────────────
   opts.hostExample — host part used in the examples (default "call").
   opts.pasteHint   — where the curl command goes:
                      "below" (single service) or "next to its service below"
                      (onboarding, many services). */
function renderNjallaStepsHtml(opts) {
  var hostExample = dpEsc((opts && opts.hostExample) || "call");
  var pasteHint = (opts && opts.pasteHint) || "below";
  var html = "";

  html += "<p style=\"margin-top:12px;\"><strong>How to set it up at Njal.la:</strong></p>";
  html += '<ol style="margin:8px 0 0 16px;padding:0;line-height:1.7;">';
  html += "<li>Create an account at <a href=\"https://njal.la\" target=\"_blank\" rel=\"noopener noreferrer\" style=\"color:var(--accent-color);\">https://njal.la</a> and buy a domain.</li>";
  html += "<li>Add a <strong>Dynamic</strong> record for the hostname:"
    + '<ul style="margin:4px 0 0 16px;padding:0;line-height:1.7;">'
    + "<li>In the Njal.la <strong>Name</strong> field, type ONLY the host part — the word before your domain.<br>"
    + "(For &quot;" + hostExample + ".yourdomain.com&quot; you&apos;d type just: <code>" + hostExample + "</code>.)<br>"
    + "&#9888; Do NOT type the full domain here — Njal.la adds it automatically.</li>"
    + "<li>Dedicating a whole separate domain to this service? Leave the Name field blank or use <code>@</code>.</li>"
    + "</ul>"
    + "</li>";
  html += "<li>A Dynamic record has <strong>NO IP field</strong> — you don&apos;t enter an IP anywhere. "
    + "It auto-fills once Sovran_SystemsOS runs the update command (on save, and again after every reboot).</li>";
  html += "<li>Njal.la gives you a curl command, e.g.:<br>"
    + '<code style="font-size:0.8em;">curl &quot;https://njal.la/update/?h=' + hostExample + '.yourdomain.com&amp;k=abc123&amp;auto&quot;</code><br>'
    + "Copy it and paste it " + pasteHint + ".</li>";
  html += "</ol>";
  return html;
}

/* ── "One router task" port-forwarding box ─────────────────────────
   opts.internalIp  — LAN IP string, or empty/null for generic wording.
   opts.plural      — true for multi-service (onboarding) wording.
   opts.includeSsh  — also mention port 22 for SSH (onboarding).
   opts.extraNote   — extra sentence appended at the end (optional). */
function renderRouterPortsHtml(opts) {
  opts = opts || {};
  var ipPart = opts.internalIp
    ? " to this computer&rsquo;s internal IP <strong>" + dpEsc(opts.internalIp) + "</strong>"
    : " to this computer&rsquo;s internal IP";
  var serviceWord = opts.plural ? "services" : "service";

  var html = "";
  html += "🔌 <strong>One router task:</strong> in your router&rsquo;s <strong>port forwarding</strong> settings, "
    + "forward port <strong>80 (TCP)</strong> and port <strong>443 (TCP)</strong>"
    + ipPart + ". Use the <strong>same number for the internal and external port</strong>. "
    + "This only needs to be done once — all domain services share these ports — "
    + "but HTTPS and SSL certificates won&rsquo;t work without them, so your " + serviceWord + " "
    + "can&rsquo;t be reached from outside your home network. "
    + "You&rsquo;ll need normal access to your router&rsquo;s settings with working port forwarding — "
    + "if your ISP blocks it (e.g. CGNAT), domain-based services can&rsquo;t be reached from the internet. ";
  if (opts.includeSsh) {
    html += "Add port <strong>22 (TCP)</strong> as well if you want remote SSH access. ";
  }
  if (opts.extraNote) {
    html += dpEsc(opts.extraNote);
  }
  return html;
}

/* ── Async helper: fill a router-box container with the internal IP ──
   Renders generic text immediately, then upgrades to the concrete LAN IP
   if /api/network provides one. Best-effort — never blocks the UI. */
function renderRouterPortsBox(elId, opts) {
  var el = document.getElementById(elId);
  if (!el) return;
  el.innerHTML = renderRouterPortsHtml(opts || {});
  fetch("/api/network")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var target = document.getElementById(elId);
      if (!target) return;
      var ip = data && data.internal_ip;
      if (ip && ip !== "unavailable") {
        var next = {};
        for (var k in (opts || {})) next[k] = opts[k];
        next.internalIp = String(ip).trim();
        target.innerHTML = renderRouterPortsHtml(next);
      }
    })
    .catch(function() { /* generic wording already shown — fine */ });
}
