/* Sovran_SystemsOS Hub — Shared domain and router instructions.

   This is the single source of truth for the simple setup guidance shown in:

     • First-boot onboarding for Server + Desktop
     • Feature setup in the Hub
     • Domain reconfiguration and troubleshooting

   Keep the wording consistent by editing it here. */
"use strict";

function dpEsc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/* Explain only what the user needs for the step in front of them. */
function renderDomainNeedsHtml(opts) {
  opts = opts || {};
  var serviceName = opts.serviceName || null;
  var purpose = opts.purpose || "";
  var html = "";

  if (purpose === "btcpay") {
    html += "<p><strong>Put your BTCPay Server online</strong></p>";
    html += "<p>Let people donate Bitcoin, pay you, or visit your online store.</p>";
    html += "<p>BTCPay Server needs a domain so people can reach it. "
      + "Sovran_SystemsOS walks you through getting your domain from "
      + '<a href="https://njal.la" target="_blank" rel="noopener noreferrer" style="color:var(--accent-color);">Njal.la</a>'
      + " and connecting it. Just follow the steps below.</p>";
  } else if (serviceName) {
    html += "<p>To make <strong>" + dpEsc(serviceName) + "</strong> available outside your home, it needs a domain.</p>";
    html += "<p>Sovran_SystemsOS walks you through getting your domain from "
      + '<a href="https://njal.la" target="_blank" rel="noopener noreferrer" style="color:var(--accent-color);">Njal.la</a>'
      + " and connecting it. Just follow the steps below.</p>";
  } else {
    html += "<p>Your domain is the address people use to reach your services on the internet.</p>";
    html += "<p>Sovran_SystemsOS walks you through getting your domain from "
      + '<a href="https://njal.la" target="_blank" rel="noopener noreferrer" style="color:var(--accent-color);">Njal.la</a>'
      + " and connecting your services. Just follow the steps below.</p>";
  }
  return html;
}

/* The shortest Njal.la steps that still tell the user exactly what to do. */
function renderNjallaStepsHtml(opts) {
  var hostExample = dpEsc((opts && opts.hostExample) || "call");
  var pasteHint = (opts && opts.pasteHint) || "below";
  var html = "";

  html += '<p style="margin-top:12px;"><strong>Get and connect your domain:</strong></p>';
  html += '<ol style="margin:8px 0 0 16px;padding:0;line-height:1.7;">';
  html += '<li>Open <a href="https://njal.la" target="_blank" rel="noopener noreferrer" style="color:var(--accent-color);">Njal.la</a>, create an account, and get a domain.</li>';
  html += "<li>Open your domain and add a <strong>Dynamic</strong> record for this service. "
    + "In the <strong>Name</strong> box, enter only the first part of the address. "
    + "For <code>" + hostExample + ".yourdomain.com</code>, enter <code>" + hostExample + "</code>. "
    + "If you are using the whole domain, leave the box blank or enter <code>@</code>.</li>";
  html += "<li>Copy the update command Njal.la gives you and paste it " + pasteHint + ".</li>";
  html += "</ol>";
  return html;
}

/* One router task shared by all normal domain-based services. */
function renderRouterPortsHtml(opts) {
  opts = opts || {};
  var ipPart = opts.internalIp
    ? " to this computer at <strong>" + dpEsc(opts.internalIp) + "</strong>"
    : " to this computer";

  var html = "";
  html += "🔌 <strong>One router task:</strong> in your router&rsquo;s <strong>Port Forwarding</strong> settings, "
    + "forward <strong>80 (TCP)</strong> and <strong>443 (TCP)</strong>"
    + ipPart + ". If your router asks for outside and inside port numbers, use the same number for both. "
    + "You only need to do this once. All your services share these two ports.";
  if (opts.extraNote) {
    html += " " + dpEsc(opts.extraNote);
  }
  return html;
}

/* Show generic wording immediately, then add the computer's address when found. */
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
    .catch(function() { /* Generic wording is already shown. */ });
}
