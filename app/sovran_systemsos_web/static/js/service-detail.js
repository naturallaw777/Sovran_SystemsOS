"use strict";

// ── Service detail modal ──────────────────────────────────────────

function _renderCredsHtml(credentials, unit) {
  var html = "";
  for (var i = 0; i < credentials.length; i++) {
    var cred = credentials[i];
    var id = "cred-" + Math.random().toString(36).substring(2, 8);
    var qrBlock = "";
    if (cred.qrcode) {
      var qrHint = (unit === "zeus-connect-setup.service")
        ? "In Zeus: <em>Settings → Connect a node → Scan LN node QR</em>. This is an <strong>LND REST</strong> QR for direct node access."
        : "In Zeus: <em>Wallets → + → scan icon</em>. This is an <strong>LND REST</strong> QR for direct node access.";
      qrBlock = '<div class="creds-qr-wrap"><img class="creds-qr-img" src="' + cred.qrcode + '" alt="QR Code for ' + escHtml(cred.label) + '"><div class="creds-qr-hint">' + qrHint + '</div></div>';
    }
    // If qronly, render the label + QR block only — skip value and copy button
    if (cred.qronly) {
      html += '<div class="creds-row"><div class="creds-label">' + escHtml(cred.label) + '</div>' + qrBlock + '</div>';
      continue;
    }
    var displayValue = linkify(cred.value);
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

var _nwcModalState = null;

function _isNwcServiceUnit(unit) {
  // The dashboard tile is backed by Alby Hub, while older drafts referred to
  // the logical feature as nwc-wallets.service. Support both so the Wallet
  // Connections manager appears from the actual tile and any legacy configs.
  return unit === "albyhub.service" || unit === "nwc-wallets.service";
}

function _nwcStateMessageHtml() {
  if (!_nwcModalState || !_nwcModalState.message) return "";
  var msgClass = _nwcModalState.messageKind === "success" ? "success" : "error";
  return '<div class="matrix-form-result ' + msgClass + '">' + escHtml(_nwcModalState.message) + '</div>';
}

function _nwcSetMessage(kind, text) {
  if (!_nwcModalState) return;
  _nwcModalState.messageKind = kind || "error";
  _nwcModalState.message = text || "";
}

function _nwcClearMessage() {
  if (!_nwcModalState) return;
  _nwcModalState.messageKind = "";
  _nwcModalState.message = "";
}

function _nwcWalletSectionEl() {
  return document.getElementById("nwc-wallets-body");
}

function _nwcFormatSats(value) {
  var n = Number(value || 0);
  if (!Number.isFinite(n)) n = 0;
  return n.toLocaleString("en-US");
}

// "Go to Service & Setup" shortcut shown when no Lightning Address domain
// is configured yet — jumps to the sibling tab instead of dead-ending.
function _nwcWireDomainLink() {
  var link = document.getElementById("nwc-domain-setup-link");
  if (link) link.addEventListener("click", function() { _nwcActivateTab("setup"); });
}

// ── Lightning Wallet Connections: tabbed modal shell ──────────────
// The wallet manager is a small app in its own right, so it gets the full
// width of the dialog on a "Wallets" tab, while status / enable / domain /
// ports / restart live on a "Service & Setup" tab.

function _setCredsDialogWide(on) {
  if (!$credsModal) return;
  var dialog = $credsModal.querySelector(".creds-dialog");
  if (dialog) dialog.classList.toggle("creds-dialog--wide", !!on);
}

function _nwcTabsShellHtml(opts) {
  var domainChip = opts.domain
    ? '<span class="nwc-header-chip nwc-header-chip--domain" title="Lightning Address domain">🌐 ' + escHtml(opts.domain) + '</span>'
    : '<span class="nwc-header-chip nwc-header-chip--warn" title="No Lightning Address domain configured yet">🌐 Domain not set</span>';

  return '<div class="nwc-tabs" data-active="' + escHtml(opts.activeTab) + '">' +
    '<div class="nwc-tabs-bar" role="tablist" aria-label="Lightning Wallet Connections sections">' +
      '<div class="nwc-tabs-btns">' +
        '<button class="nwc-tab-btn" role="tab" data-tab="wallets" id="nwc-tab-btn-wallets" aria-controls="nwc-tab-wallets">⚡ Wallets</button>' +
        '<button class="nwc-tab-btn" role="tab" data-tab="setup" id="nwc-tab-btn-setup" aria-controls="nwc-tab-setup">⚙ Service &amp; Setup</button>' +
      '</div>' +
      '<div class="nwc-header-chips">' +
        '<span class="nwc-header-chip"><span class="status-dot ' + opts.statusDotClass + '"></span>' + escHtml(opts.statusLabel) + '</span>' +
        domainChip +
      '</div>' +
    '</div>' +
    '<div class="nwc-tab-panel" role="tabpanel" id="nwc-tab-wallets" aria-labelledby="nwc-tab-btn-wallets" data-tab="wallets">' + opts.walletsHtml + '</div>' +
    '<div class="nwc-tab-panel" role="tabpanel" id="nwc-tab-setup" aria-labelledby="nwc-tab-btn-setup" data-tab="setup">' + opts.setupHtml + '</div>' +
  '</div>';
}

function _nwcActivateTab(tab) {
  var root = document.querySelector(".nwc-tabs");
  if (!root) return;
  root.setAttribute("data-active", tab);
  root.querySelectorAll(".nwc-tab-btn").forEach(function(btn) {
    var on = btn.getAttribute("data-tab") === tab;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  root.querySelectorAll(".nwc-tab-panel").forEach(function(panel) {
    panel.classList.toggle("active", panel.getAttribute("data-tab") === tab);
  });
  var body = document.getElementById("creds-body");
  if (body) body.scrollTop = 0;
}

function _nwcWireTabs() {
  var root = document.querySelector(".nwc-tabs");
  if (!root) return;
  root.querySelectorAll(".nwc-tab-btn").forEach(function(btn) {
    btn.addEventListener("click", function() {
      _nwcActivateTab(btn.getAttribute("data-tab"));
    });
  });
  _nwcActivateTab(root.getAttribute("data-active") || "wallets");
  var gotoSetup = document.getElementById("nwc-goto-setup-btn");
  if (gotoSetup) gotoSetup.addEventListener("click", function() { _nwcActivateTab("setup"); });
}

function _nwcRenderWalletState() {
  var host = _nwcWalletSectionEl();
  if (!host || !_nwcModalState) return;
  var state = _nwcModalState;
  var html = "";
  html += _nwcStateMessageHtml();

  if (state.view === "create") {
    var selectedLimited = state.createForm.access_preset === "send_receive_limited";
    html +=
      '<div class="nwc-tab-intro-title">Create a Wallet</div>' +
      '<p class="nwc-tab-intro-desc">Create a secure, sandboxed wallet for a specific app. Each wallet gets its own Lightning Address and optional spending limit.</p>' +
      '<div class="matrix-form-group"><label class="matrix-form-label" for="nwc-wallet-name">Wallet Name</label>' +
        '<input class="matrix-form-input" id="nwc-wallet-name" type="text" placeholder="My Wallet" value="' + escHtml(state.createForm.name || "") + '" autocomplete="off"></div>' +
      '<div class="matrix-form-group"><label class="matrix-form-label" for="nwc-wallet-alias">Lightning Address Alias</label>' +
        '<input class="matrix-form-input" id="nwc-wallet-alias" type="text" placeholder="my-wallet" value="' + escHtml(state.createForm.alias || "") + '" autocomplete="off">' +
        '<div class="creds-qr-hint">Lowercase letters, numbers, "_" and "-" only.</div></div>' +
      '<div class="matrix-form-group"><label class="matrix-form-label" for="nwc-wallet-preset">Access Preset</label>' +
        '<select class="matrix-form-input" id="nwc-wallet-preset">' +
          '<option value="receive_only"' + (state.createForm.access_preset === "receive_only" ? " selected" : "") + '>Receive only</option>' +
          '<option value="send_receive_limited"' + (selectedLimited ? " selected" : "") + '>Send + receive (limited)</option>' +
        '</select></div>' +
      '<div class="matrix-form-group"><label class="matrix-form-label" for="nwc-wallet-limit">Spending Limit (sats)</label>' +
        '<input class="matrix-form-input" id="nwc-wallet-limit" type="number" min="1" step="1" placeholder="50000" value="' + escHtml(state.createForm.spending_limit_sats || "") + '"' + (selectedLimited ? "" : " disabled") + "></div>" +
      '<div class="matrix-form-actions">' +
        '<button class="matrix-form-back" id="nwc-create-cancel-btn"' + (state.busy ? " disabled" : "") + '>← Back</button>' +
        '<button class="matrix-form-submit" id="nwc-create-submit-btn"' + (state.busy ? " disabled" : "") + '>' + (state.busy ? "Creating…" : "Create Wallet") + '</button>' +
      '</div>';
    host.innerHTML = html;
    var presetSel = document.getElementById("nwc-wallet-preset");
    if (presetSel) {
      presetSel.addEventListener("change", function() {
        state.createForm.access_preset = presetSel.value;
        _nwcRenderWalletState();
      });
    }
    var cancelBtn = document.getElementById("nwc-create-cancel-btn");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", function() {
        if (state.busy) return;
        state.view = state.wallets.length > 0 ? "list" : "empty";
        _nwcClearMessage();
        _nwcRenderWalletState();
      });
    }
    var submitBtn = document.getElementById("nwc-create-submit-btn");
    if (submitBtn) submitBtn.addEventListener("click", _nwcCreateWallet);
    return;
  }

  if (state.view === "created" && state.lastCreated) {
    var created = state.lastCreated;
    var pairId = "nwc-pairing-uri-" + Math.random().toString(36).substring(2, 8);
    html += '<div class="nwc-secret-warning">⚠ One-time pairing secret. Save it now — it will not be shown again.</div>';
    if (created.pairing_qrcode) {
      html += '<div class="creds-row"><div class="creds-label">QR Code</div>' +
        '<div class="creds-qr-wrap"><img class="creds-qr-img" src="' + created.pairing_qrcode + '" alt="QR code for Lightning Wallet Connections pairing secret"><div class="creds-qr-hint">This is an <strong>NWC</strong> pairing QR — in Zeus, add a wallet and use the scan icon (see steps below).</div></div></div>';
    }
    html += '<div class="creds-row"><div class="creds-label">Pairing URI</div>' +
      '<div class="creds-value-wrap"><div class="creds-value" id="' + pairId + '">' + escHtml(created.pairing_uri || "Unavailable") + '</div><button class="creds-copy-btn" data-target="' + pairId + '">Copy</button></div></div>';
    if (created.wallet && created.wallet.lightning_address) {
      html += '<div class="creds-row"><div class="creds-label">Lightning Address</div>' +
        '<div class="creds-value-wrap"><div class="creds-value">' + escHtml(created.wallet.lightning_address) + '</div></div></div>';
    }
    html += '<div class="nwc-connect-guide">' +
      '<div class="nwc-connect-guide-title">📱 Connect to Zeus</div>' +
      '<p class="nwc-connect-guide-intro">This pairing URI is an <strong>NWC (Nostr Wallet Connect)</strong> connection — the modern, mobile-friendly way to use Zeus with your node. It connects directly through your Lightning domain, so no Tor or port forwarding is needed on your phone.</p>' +
      '<div class="nwc-connect-steps">' +
        '<div class="nwc-connect-step"><div class="nwc-step-num">1</div><div><strong>Download Zeus</strong> from the App Store or Google Play.</div></div>' +
        '<div class="nwc-connect-step"><div class="nwc-step-num">2</div><div>Open Zeus and open the <strong>Wallets</strong> screen.</div></div>' +
        '<div class="nwc-connect-step"><div class="nwc-step-num">3</div><div>Tap the <strong>+ (Add Wallet)</strong> button in the top-right corner.</div></div>' +
        '<div class="nwc-connect-step"><div class="nwc-step-num">4</div><div>On <strong>Wallet Configuration</strong>, tap the <strong>scan icon</strong> in the top-right corner, then scan the QR code above.</div></div>' +
        '<div class="nwc-connect-step"><div class="nwc-step-num">5</div><div>Zeus detects the NWC QR and fills in <strong>Nostr Wallet Connect</strong>. Review it, then tap <strong>Save Wallet Config</strong>.</div></div>' +
      '</div>' +
      '<div class="nwc-connect-note"><strong>💡 Note:</strong> This is <em>not</em> the same as the LND REST / Tor QR shown on your LND tile — that connects Zeus directly to your Lightning node for full admin control. NWC gives your wallet sandboxed, limited access for everyday spending.</div>' +
    '</div>';
    html += '<div class="matrix-form-actions">' +
      '<button class="matrix-form-back" id="nwc-created-another-btn"' + (state.busy ? " disabled" : "") + '>Create Another Wallet</button>' +
      '<button class="matrix-form-submit" id="nwc-created-continue-btn"' + (state.busy ? " disabled" : "") + '>I Saved This Secret</button>' +
      '</div>';
    host.innerHTML = html;
    _attachCopyHandlers(host);
    var continueBtn = document.getElementById("nwc-created-continue-btn");
    if (continueBtn) {
      continueBtn.addEventListener("click", async function() {
        if (state.busy) return;
        state.lastCreated = null;
        state.view = "list";
        await _nwcRefreshWallets();
      });
    }
    var anotherBtn = document.getElementById("nwc-created-another-btn");
    if (anotherBtn) {
      anotherBtn.addEventListener("click", function() {
        if (state.busy) return;
        state.view = "create";
        _nwcClearMessage();
        _nwcRenderWalletState();
      });
    }
    return;
  }

  if (state.view === "share" && state.shareWallet) {
    var sw = state.shareWallet;
    var swId = encodeURIComponent(String(sw.id || sw.pubkey || ""));
    var swAddress = sw.lightning_address || ((sw.alias && state.domain) ? sw.alias + "@" + state.domain : "");
    var pngUrl = "/api/nwc/wallets/" + swId + "/lnurl-qr.png";
    var shareAddrId = "nwc-share-addr-" + Math.random().toString(36).substring(2, 8);
    var shareLnurlId = "nwc-share-lnurl-" + Math.random().toString(36).substring(2, 8);
    html += '<p class="svc-detail-desc">Share the Lightning Address for <strong>' + escHtml(sw.name || "Wallet") + '</strong>. This QR never expires — anyone can scan it with any Lightning wallet to send sats, as many times as they like.</p>' +
      '<div class="creds-qr-wrap">' +
        '<img class="creds-qr-img" src="' + pngUrl + '" alt="LNURL QR code for ' + escHtml(swAddress) + '">' +
        '<div class="creds-qr-hint">Scan with any Lightning wallet to pay ' + escHtml(swAddress) + '</div>' +
      '</div>' +
      (swAddress
        ? '<div class="creds-row"><div class="creds-label">Lightning Address</div><div class="creds-value-wrap"><div class="creds-value" id="' + shareAddrId + '">' + escHtml(swAddress) + '</div><button class="creds-copy-btn" data-target="' + shareAddrId + '">Copy</button></div></div>'
        : "") +
      '<div class="creds-row"><div class="creds-label">LNURL</div><div class="creds-value-wrap"><div class="creds-value nwc-lnurl-value" id="' + shareLnurlId + '">Loading…</div><button class="creds-copy-btn" data-target="' + shareLnurlId + '">Copy</button></div></div>' +
      '<div class="nwc-share-actions">' +
        '<button class="matrix-form-submit" id="nwc-share-dl-png-btn">⬇ Download PNG</button>' +
        '<button class="matrix-form-back" id="nwc-share-dl-svg-btn">⬇ Download SVG</button>' +
        '<button class="matrix-form-back" id="nwc-share-print-btn">🖨 Print…</button>' +
        '<button class="matrix-form-back" id="nwc-share-back-btn">← Back</button>' +
      '</div>' +
      '<div class="creds-qr-hint nwc-share-formats-hint">PNG is ideal for websites and social posts. SVG stays sharp at any print size.</div>';
    host.innerHTML = html;
    _attachCopyHandlers(host);
    apiFetch("/api/nwc/wallets/" + swId + "/lnurl").then(function(payload) {
      var el = document.getElementById(shareLnurlId);
      if (el) el.textContent = payload.lnurl || "Unavailable";
    }).catch(function() {
      var el = document.getElementById(shareLnurlId);
      if (el) el.textContent = "Unavailable";
    });
    function _nwcShareDownload(url) {
      var a = document.createElement("a");
      a.href = url;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    var dlPngBtn = document.getElementById("nwc-share-dl-png-btn");
    if (dlPngBtn) dlPngBtn.addEventListener("click", function() { _nwcShareDownload(pngUrl + "?download=1"); });
    var dlSvgBtn = document.getElementById("nwc-share-dl-svg-btn");
    if (dlSvgBtn) dlSvgBtn.addEventListener("click", function() { _nwcShareDownload("/api/nwc/wallets/" + swId + "/lnurl-qr.svg?download=1"); });
    var printBtn = document.getElementById("nwc-share-print-btn");
    if (printBtn) printBtn.addEventListener("click", function() { window.open("/api/nwc/wallets/" + swId + "/lnurl-qr/print", "_blank", "noopener"); });
    var shareBackBtn = document.getElementById("nwc-share-back-btn");
    if (shareBackBtn) {
      shareBackBtn.addEventListener("click", function() {
        state.view = "list";
        state.shareWallet = null;
        _nwcClearMessage();
        _nwcRenderWalletState();
      });
    }
    return;
  }

  var canCreate = !!state.domain && !state.busy;
  var walletCount = (state.wallets || []).length;
  html += '<div class="nwc-toolbar">' +
    '<div class="nwc-toolbar-count">' + (walletCount === 1 ? '1 wallet' : walletCount + ' wallets') + '</div>' +
    '<div class="nwc-toolbar-actions">' +
      '<button class="matrix-form-back nwc-toolbar-refresh" id="nwc-refresh-btn"' + (state.busy ? " disabled" : "") + '>↻ Refresh</button>' +
      '<button class="matrix-action-btn" id="nwc-open-create-btn"' + (canCreate ? "" : " disabled") + '>➕ New Wallet</button>' +
    '</div>' +
  '</div>';
  if (!state.domain) {
    html += '<div class="nwc-domain-required">' +
      '<strong>⚠ Lightning Address domain required</strong>' +
      '<div class="nwc-domain-required-body">Set up a unique hostname such as <strong>lightning.yourdomain.com</strong> before creating wallets.</div>' +
      '<button class="btn btn-primary nwc-domain-required-btn" id="nwc-domain-setup-link">⚙ Go to Service &amp; Setup</button>' +
    '</div>';
  }

  if (!state.wallets || state.wallets.length === 0) {
    html += '<div class="nwc-empty-state">' +
      '<div class="nwc-empty-icon">⚡</div>' +
      '<div class="nwc-empty-title">Ready to start spending</div>' +
      '<p class="nwc-empty-desc">Create your first isolated wallet to connect to apps like Zeus (via NWC) or Nostr. Experience faster, more secure Lightning payments today.</p>' +
      '</div>';
    host.innerHTML = html;
    _nwcWireDomainLink();
    var openCreateBtn = document.getElementById("nwc-open-create-btn");
    if (openCreateBtn) {
      openCreateBtn.addEventListener("click", function() {
        if (state.busy) return;
        _nwcClearMessage();
        state.view = "create";
        _nwcRenderWalletState();
      });
    }
    var refreshBtnEmpty = document.getElementById("nwc-refresh-btn");
    if (refreshBtnEmpty) refreshBtnEmpty.addEventListener("click", _nwcRefreshWallets);
    return;
  }

  html += '<div class="nwc-wallet-list">';
  state.wallets.forEach(function(wallet) {
    var id = wallet.id || wallet.pubkey || "";
    var addressId = "nwc-wallet-addr-" + Math.random().toString(36).substring(2, 8);
    var pending = Number(wallet.pending_transactions || 0);
    html += '<div class="nwc-wallet-card">' +
      '<div class="nwc-wallet-card-head">' +
        '<div class="nwc-wallet-card-title">' + escHtml(wallet.name || "Wallet") + '</div>' +
        '<div class="nwc-wallet-chips">' +
          '<span class="nwc-wallet-chip nwc-wallet-chip--balance">' + escHtml(_nwcFormatSats(wallet.balance_sats)) + ' sats</span>' +
          (pending > 0
            ? '<span class="nwc-wallet-chip nwc-wallet-chip--pending" title="Pending transactions">⏳ ' + escHtml(String(pending)) + ' pending</span>'
            : '') +
        '</div>' +
      '</div>' +
      (wallet.lightning_address
        ? '<div class="nwc-wallet-address">' +
            '<div class="creds-label">Lightning Address</div>' +
            '<div class="creds-value-wrap"><div class="creds-value" id="' + addressId + '">' + escHtml(wallet.lightning_address) + '</div>' +
            '<button class="creds-copy-btn" data-target="' + addressId + '">Copy</button></div>' +
          '</div>'
        : '<div class="nwc-wallet-address"><div class="creds-label">Alias</div>' +
            '<div class="creds-value-wrap"><div class="creds-value">' + escHtml(wallet.alias || "") + '</div></div></div>') +
      '<div class="nwc-wallet-actions">' +
        '<button class="matrix-action-btn nwc-wallet-action-btn" data-action="share" data-wallet-id="' + escHtml(id) + '"' + ((state.busy || !wallet.lightning_address) ? " disabled" : "") + '>⚡ Share QR</button>' +
        '<button class="matrix-form-back nwc-wallet-action-btn" data-action="test" data-wallet-alias="' + escHtml(wallet.alias || "") + '"' + (state.busy ? " disabled" : "") + '>Verify</button>' +
        '<span class="nwc-wallet-actions-spacer"></span>' +
        '<button class="matrix-form-back nwc-wallet-action-btn nwc-wallet-danger-btn" data-action="drain" data-wallet-id="' + escHtml(id) + '"' + (state.busy ? " disabled" : "") + '>Drain</button>' +
        '<button class="matrix-form-back nwc-wallet-action-btn nwc-wallet-danger-btn" data-action="delete" data-wallet-id="' + escHtml(id) + '"' + (state.busy ? " disabled" : "") + '>Delete</button>' +
      '</div>' +
    '</div>';
  });
  html += "</div>";
  host.innerHTML = html;
  _attachCopyHandlers(host);
  _nwcWireDomainLink();

  var createBtn = document.getElementById("nwc-open-create-btn");
  if (createBtn) {
    createBtn.addEventListener("click", function() {
      if (state.busy) return;
      _nwcClearMessage();
      state.view = "create";
      _nwcRenderWalletState();
    });
  }

  var refreshBtn = document.getElementById("nwc-refresh-btn");
  if (refreshBtn) refreshBtn.addEventListener("click", _nwcRefreshWallets);

  host.querySelectorAll(".nwc-wallet-action-btn").forEach(function(btn) {
    btn.addEventListener("click", function() {
      var action = btn.getAttribute("data-action");
      if (action === "share") _nwcOpenShare(btn.getAttribute("data-wallet-id"));
      else if (action === "test") _nwcVerifyWallet(btn.getAttribute("data-wallet-alias"));
      else if (action === "drain") _nwcDrainWallet(btn.getAttribute("data-wallet-id"));
      else if (action === "delete") _nwcDeleteWallet(btn.getAttribute("data-wallet-id"));
    });
  });
}

function _nwcOpenShare(walletId) {
  if (!_nwcModalState || _nwcModalState.busy || !walletId) return;
  var wallet = null;
  for (var i = 0; i < _nwcModalState.wallets.length; i++) {
    var w = _nwcModalState.wallets[i];
    if (String(w.id || w.pubkey || "") === String(walletId)) { wallet = w; break; }
  }
  if (!wallet) {
    _nwcSetMessage("error", "Wallet connection not found.");
    _nwcRenderWalletState();
    return;
  }
  _nwcClearMessage();
  _nwcModalState.shareWallet = wallet;
  _nwcModalState.view = "share";
  _nwcRenderWalletState();
}

async function _nwcRefreshWallets() {
  if (!_nwcModalState) return;
  var host = _nwcWalletSectionEl();
  if (host) host.innerHTML = '<p class="creds-loading">Loading wallet connections…</p>';
  try {
    var payload = await apiFetch("/api/nwc/wallets");
    _nwcModalState.wallets = Array.isArray(payload.wallets) ? payload.wallets : [];
    _nwcModalState.domain = payload.domain || null;
    if (_nwcModalState.view !== "create" && _nwcModalState.view !== "created" && _nwcModalState.view !== "share") {
      _nwcModalState.view = _nwcModalState.wallets.length > 0 ? "list" : "empty";
    }
    _nwcRenderWalletState();
  } catch (err) {
    _nwcSetMessage("error", (err && err.message) ? err.message : "Could not load wallet connections.");
    _nwcRenderWalletState();
  }
}

function _nwcBusy(on) {
  if (!_nwcModalState) return;
  _nwcModalState.busy = !!on;
}

async function _nwcCreateWallet() {
  if (!_nwcModalState || _nwcModalState.busy) return;
  var nameEl = document.getElementById("nwc-wallet-name");
  var aliasEl = document.getElementById("nwc-wallet-alias");
  var presetEl = document.getElementById("nwc-wallet-preset");
  var limitEl = document.getElementById("nwc-wallet-limit");
  if (!nameEl || !aliasEl || !presetEl || !limitEl) return;

  var name = (nameEl.value || "").trim();
  var alias = (aliasEl.value || "").trim().toLowerCase();
  var preset = presetEl.value || "receive_only";
  var limitRaw = (limitEl.value || "").trim();
  var limit = null;

  _nwcModalState.createForm = {
    name: name,
    alias: alias,
    access_preset: preset,
    spending_limit_sats: limitRaw
  };

  if (!name) {
    _nwcSetMessage("error", "Wallet name is required.");
    _nwcRenderWalletState();
    return;
  }
  if (!/^[a-z0-9][a-z0-9_-]{0,31}$/.test(alias)) {
    _nwcSetMessage("error", 'Alias must start with a letter or number and use only lowercase letters, numbers, "_" or "-".');
    _nwcRenderWalletState();
    return;
  }
  if (preset === "send_receive_limited") {
    limit = parseInt(limitRaw, 10);
    if (!Number.isFinite(limit) || limit <= 0) {
      _nwcSetMessage("error", "A positive spending limit is required for limited send access.");
      _nwcRenderWalletState();
      return;
    }
  }

  _nwcBusy(true);
  _nwcClearMessage();
  _nwcRenderWalletState();
  try {
    var payload = await apiFetch("/api/nwc/wallets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name,
        alias: alias,
        access_preset: preset,
        spending_limit_sats: preset === "send_receive_limited" ? limit : null
      })
    });
    _nwcModalState.lastCreated = {
      wallet: payload.wallet || null,
      pairing_uri: payload.pairing_uri || "",
      pairing_qrcode: payload.pairing_qrcode || "",
      lightning_address: payload.lightning_address || null
    };
    _nwcModalState.view = "created";
    _nwcSetMessage("success", "Wallet created. Save the one-time secret before you continue.");
    _nwcBusy(false);
    _nwcRenderWalletState();
  } catch (err) {
    _nwcBusy(false);
    _nwcSetMessage("error", (err && err.message) ? err.message : "Failed to create wallet connection.");
    _nwcRenderWalletState();
  }
}

async function _nwcVerifyWallet(alias) {
  if (!_nwcModalState || _nwcModalState.busy || !alias) return;
  _nwcBusy(true);
  _nwcClearMessage();
  _nwcRenderWalletState();
  try {
    await apiFetch("/api/nwc/addresses/" + encodeURIComponent(alias) + "/test", { method: "POST" });
    _nwcSetMessage("success", "Lightning Address verification succeeded for " + alias + ".");
  } catch (err) {
    _nwcSetMessage("error", (err && err.message) ? err.message : "Lightning Address verification failed.");
  }
  _nwcBusy(false);
  _nwcRenderWalletState();
}

async function _nwcDrainWallet(walletId) {
  if (!_nwcModalState || _nwcModalState.busy || !walletId) return;
  if (!window.confirm("Drain this wallet connection now? This cannot be undone.")) return;
  _nwcBusy(true);
  _nwcClearMessage();
  _nwcRenderWalletState();
  try {
    var resp = await apiFetch("/api/nwc/wallets/" + encodeURIComponent(walletId) + "/drain", { method: "POST" });
    _nwcSetMessage("success", "Wallet drained (" + String(resp.drained_sats || 0) + " sats).");
    _nwcBusy(false);
    await _nwcRefreshWallets();
  } catch (err) {
    _nwcBusy(false);
    _nwcSetMessage("error", (err && err.message) ? err.message : "Failed to drain wallet.");
    _nwcRenderWalletState();
  }
}

async function _nwcDeleteWallet(walletId) {
  if (!_nwcModalState || _nwcModalState.busy || !walletId) return;
  if (!window.confirm("Delete this wallet connection? This removes the wallet alias from Lightning Wallet Connections.")) return;
  _nwcBusy(true);
  _nwcClearMessage();
  _nwcRenderWalletState();
  try {
    await apiFetch("/api/nwc/wallets/" + encodeURIComponent(walletId), { method: "DELETE" });
    _nwcSetMessage("success", "Wallet connection deleted.");
    _nwcBusy(false);
    await _nwcRefreshWallets();
  } catch (err) {
    _nwcBusy(false);
    _nwcSetMessage("error", (err && err.message) ? err.message : "Failed to delete wallet connection.");
    _nwcRenderWalletState();
  }
}

async function _nwcInitWalletFlow(unit, name, icon) {
  _nwcModalState = {
    unit: unit,
    name: name,
    icon: icon,
    view: "empty",
    wallets: [],
    domain: null,
    busy: false,
    message: "",
    messageKind: "",
    lastCreated: null,
    shareWallet: null,
    createForm: {
      name: "",
      alias: "",
      access_preset: "receive_only",
      spending_limit_sats: ""
    }
  };
  await _nwcRefreshWallets();
}

async function openServiceDetailModal(unit, name, icon) {
  if (!$credsModal) return;
  var isNwc = _isNwcServiceUnit(unit);
  _setCredsDialogWide(isNwc);
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

    // Append version badge next to title if version is detected
    var serviceVersion = data.version || data.bitcoin_version || '';
    if (serviceVersion && $credsTitle) {
      var existingBadge = $credsTitle.querySelector(".creds-title-version-badge");
      if (existingBadge) {
        existingBadge.textContent = serviceVersion;
      } else {
        var badge = document.createElement("span");
        badge.className = "creds-title-version-badge";
        badge.textContent = serviceVersion;
        $credsTitle.appendChild(badge);
      }
    }

    // Two content buckets. For most services everything lands in `html` and is
    // rendered as one column, exactly as before. For Lightning Wallet
    // Connections the day-to-day wallet manager (html) is split away from the
    // service plumbing — status, enable/disable, domain, ports, restart
    // (setupHtml) — and the two are rendered as tabs so neither feels cramped.
    var html = "";
    var setupHtml = "";
    function addSetup(chunk) {
      if (isNwc) setupHtml += chunk;
      else html += chunk;
    }

    // Section A: Description
    if (data.description) {
      addSetup('<div class="svc-detail-section">' +
        '<p class="svc-detail-desc">' + escHtml(data.description) + '</p>' +
        '</div>');
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
    addSetup('<div class="svc-detail-section">' +
      '<div class="svc-detail-section-title">Status</div>' +
      '<div class="svc-detail-status">' +
        '<span class="status-dot ' + sc + '"></span>' +
        '<span>' + escHtml(st) + '</span>' +
      '</div>' +
      '</div>');

    // Section B2: BIP-110 live status (bip110 tile only)
    if (icon === 'bip110' && data.bip110) {
      var bip110 = data.bip110;
      var bip110State = bip110.state || 'unknown';
      var bip110Cfg = BIP110_BADGE_CONFIG[bip110State] || BIP110_BADGE_CONFIG.unknown;
      var bip110Source = bip110.source ? ' <span class="bip110-source-label">(source: ' + escHtml(bip110.source) + ')</span>' : '';
      html += '<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">BIP-110 Deployment Status</div>' +
        '<div class="bip110-status-row">' +
          '<span class="tile-bip110-badge ' + bip110Cfg.cls + '" title="' + escHtml(bip110Cfg.title) + '">' + escHtml(bip110Cfg.label) + '</span>' +
          bip110Source +
        '</div>' +
        '</div>';
    }

    // Section C: Domain diagnostics (domain services)
    if (data.needs_domain) {
      var steps = data.domain_check_steps || [];
      var stepsHtml = "";
      steps.forEach(function(step) {
        var iconLabel = "—";
        if (step.status === "ok") iconLabel = "✅";
        else if (step.status === "error") iconLabel = "❌";
        else if (step.status === "warning") iconLabel = "⚠️";
        else if (step.status === "skipped") iconLabel = "⏭️";
        var detail = escHtml(step.detail || "").replace(/\n/g, "<br>");
        stepsHtml += '<div class="svc-detail-troubleshoot" style="margin-bottom:10px">' +
          '<strong>' + iconLabel + ' Step ' + escHtml(String(step.step)) + ': ' + escHtml(step.label || "") + '</strong>' +
          (detail ? '<div style="margin-top:6px">' + detail + '</div>' : '') +
          '</div>';
      });

      var domainActionHtml = "";
      var ds = data.domain_status || {};
      if (!data.domain && data.domain_name) {
        domainActionHtml = '<button class="btn btn-primary svc-detail-domain-btn" id="svc-detail-config-domain-btn">🌐 Configure Domain</button>';
      } else if (data.domain && (ds.status === "dns_mismatch" || ds.status === "unresolvable")) {
        domainActionHtml = '<button class="btn btn-primary svc-detail-domain-btn" id="svc-detail-reconfig-domain-btn">🔄 Reconfigure Domain</button>';
      }

      addSetup('<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">Domain Diagnostic Checklist</div>' +
        stepsHtml +
        domainActionHtml +
        '</div>');

      if (data.router_ports && data.router_ports.length > 0) {
        var trimmedInternalIp = data.internal_ip ? String(data.internal_ip).trim() : "";
        addSetup('<div class="svc-detail-section">' +
          '<div class="svc-detail-section-title">Ports to Forward in Your Router</div>' +
          renderPortForwardGuideHtml(data.router_ports, {
            internalIp: trimmedInternalIp || null,
            tableClass: "svc-detail-port-table",
            introClass: "svc-detail-port-note",
            noteClass: "svc-detail-port-note",
          }) +
          '</div>');
      }
    } else if (data.port_statuses && data.port_statuses.length > 0) {
      // Non-domain services (e.g. SSH): show what to forward, plus a short
      // note if the service isn't actually listening on this computer yet.
      var localInternalIp = data.internal_ip ? String(data.internal_ip).trim() : "";
      var notListening = data.port_statuses.filter(function(p) {
        return p.status === "closed";
      });
      var localNote = notListening.length
        ? '<div class="svc-detail-port-note port-status-closed">' +
            '⚠ Port ' + escHtml(notListening.map(function(p) { return p.port; }).join(", ")) +
            ' is not open on this computer yet — enable the service below first, then forward it in your router.' +
          '</div>'
        : "";
      html += '<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">Ports to Forward in Your Router</div>' +
        '<div class="svc-detail-port-note">Only needed if you want to reach this service from <strong>outside</strong> your home network. On your local network it already works without any router changes.</div>' +
        renderPortForwardGuideHtml(data.port_statuses, {
          internalIp: localInternalIp || null,
          tableClass: "svc-detail-port-table",
          introClass: "svc-detail-port-note",
          noteClass: "svc-detail-port-note",
        }) +
        localNote +
        '</div>';
    }

    // Section E: Credentials & Links
    if (isNwc) {
      if (effectiveEnabled || data.enabled) {
        html += '<div class="nwc-tab-intro">' +
            '<div class="nwc-intro-header">' +
              '<div class="nwc-tab-intro-title">Lightning Wallet Connections</div>' +
              '<p class="nwc-tab-intro-desc">Powerful, isolated wallets for your daily spending and modern apps.</p>' +
            '</div>' +
            '<div class="nwc-benefits-grid">' +
              '<div class="nwc-benefit-item">' +
                '<div class="nwc-benefit-icon">🛡️</div>' +
                '<div class="nwc-benefit-content">' +
                  '<strong>Isolated & Secure</strong>' +
                  '<p>Create sandboxed wallets for quick spending while keeping your main node protected. Isolated access is faster than Tor and perfect for budgeting.</p>' +
                '</div>' +
              '</div>' +
              '<div class="nwc-benefit-item">' +
                '<div class="nwc-benefit-icon">🌐</div>' +
                '<div class="nwc-benefit-content">' +
                  '<strong>Modern Ecosystem</strong>' +
                  '<p>Easily spend and receive bitcoin using LNURL and Nostr (NWC) across the growing ecosystem of decentralized apps.</p>' +
                '</div>' +
              '</div>' +
              '<div class="nwc-benefit-item">' +
                '<div class="nwc-benefit-icon">📱</div>' +
                '<div class="nwc-benefit-content">' +
                  '<strong>Zeus on the Go (via NWC)</strong>' +
                  '<p>Connect Zeus to your wallet using NWC — no Tor, no port forwarding. Create a wallet below, scan the pairing QR, and start spending from your phone.</p>' +
                '</div>' +
              '</div>' +
            '</div>' +
          '</div>' +
          '<div id="nwc-wallets-body"><p class="creds-loading">Loading wallets…</p></div>' +
          '<details class="nwc-liquidity-details">' +
            '<summary class="nwc-liquidity-summary">' +
              '<span class="nwc-liquidity-icon">⚡</span>' +
              '<span>' +
                '<strong>Lightning Channel &amp; Liquidity Guide</strong>' +
                '<span class="nwc-liquidity-subtitle">Why a brand-new node can\'t send or receive yet</span>' +
              '</span>' +
            '</summary>' +
            '<div class="nwc-liquidity-guide-card">' +
              '<p class="nwc-liquidity-body">' +
                'Your wallets, pairing keys, and Lightning Address endpoints (like <code>name@yourdomain.com</code>) work the moment you create them. Moving actual bitcoin, though, needs a Lightning node with open channels.' +
              '</p>' +
              '<div class="nwc-liquidity-steps">' +
                '<div class="nwc-liquidity-step">' +
                  '<div class="step-num">1</div>' +
                  '<div>' +
                    '<strong>Outbound Liquidity (Sending)</strong>' +
                    '<p class="nwc-liquidity-step-desc">Required so connected apps can pay invoices and send funds.</p>' +
                  '</div>' +
                '</div>' +
                '<div class="nwc-liquidity-step">' +
                  '<div class="step-num">2</div>' +
                  '<div>' +
                    '<strong>Inbound Liquidity (Receiving)</strong>' +
                    '<p class="nwc-liquidity-step-desc">Required so your Lightning Address can receive payments from anyone.</p>' +
                  '</div>' +
                '</div>' +
              '</div>' +
              '<div class="nwc-liquidity-action">' +
                '<p class="nwc-liquidity-analogy">💧 <strong>The Plumbing Analogy:</strong> Channels are two-way water pipes. To pour water in (receive) or pump it out (send), you need open channels with liquidity on the right side.</p>' +
                '<button class="matrix-action-btn nwc-rtl-btn" id="nwc-open-rtl-btn">🚀 Open Ride The Lightning (RTL) to Manage Channels</button>' +
              '</div>' +
            '</div>' +
          '</details>';
      } else {
        html += '<div class="nwc-disabled-state">' +
          '<div class="nwc-disabled-icon">⚡</div>' +
          '<div class="nwc-disabled-title">Lightning Wallet Connections is turned off</div>' +
          '<p class="nwc-disabled-desc">Enable it on the <strong>Service &amp; Setup</strong> tab and rebuild, then come back here to create and manage wallets.</p>' +
          '<button class="btn btn-primary" id="nwc-goto-setup-btn">⚙ Go to Service &amp; Setup</button>' +
          '</div>';
      }
    } else if (data.has_credentials && data.credentials && data.credentials.length > 0) {
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
            '<button class="matrix-action-btn" id="sys-change-pw-btn">🔑 Change Free Account Password</button>' +
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
      var addonSectionTitle = (feat.id === "bitcoin-core")
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

      addSetup('<div class="svc-detail-section">' +
        '<div class="svc-detail-section-title">' + addonSectionTitle + '</div>' +
        '<p class="svc-detail-desc">' + escHtml(addonDesc) + '</p>' +
        conflictsHtml +
        '<div class="svc-detail-addon-row">' +
          '<span class="svc-detail-addon-status ' + addonStatusCls + '">' + addonStatusLabel + '</span>' +
          '<button class="' + addonBtnCls + '" id="svc-detail-addon-btn">' + escHtml(addonBtnLabel) + '</button>' +
        '</div>' +
        '</div>');
    }

    if ((effectiveEnabled || data.enabled) && unit !== "phpfpm-nextcloud.service" && unit !== "phpfpm-wordpress.service") {
      addSetup('<div class="svc-detail-section svc-detail-restart-section">' +
        '<div class="svc-detail-section-title">Troubleshooting</div>' +
        '<p class="svc-detail-desc">If you\'re experiencing issues with this service, try restarting it.</p>' +
        '<button class="btn btn-warning svc-detail-restart-btn" id="svc-detail-restart-btn">🔄 Restart Service</button>' +
        '<div class="svc-detail-restart-result" id="svc-detail-restart-result"></div>' +
        '</div>');
    }

    if (isNwc) {
      // Land on Setup when the service is off or the domain still needs
      // configuring — otherwise the Wallets tab is the useful default.
      var domainReady = !!data.domain;
      var startTab = (effectiveEnabled || data.enabled) && domainReady ? "wallets" : "setup";
      html = _nwcTabsShellHtml({
        walletsHtml: html,
        setupHtml: setupHtml,
        statusDotClass: sc,
        statusLabel: st,
        domain: data.domain || null,
        activeTab: startTab
      });
    }

    $credsBody.innerHTML = html;
    if (isNwc) _nwcWireTabs();
    _attachCopyHandlers($credsBody);
    if (_isNwcServiceUnit(unit) && (effectiveEnabled || data.enabled)) {
      await _nwcInitWalletFlow(unit, name, icon);
      var nwcRtlBtn = document.getElementById("nwc-open-rtl-btn");
      if (nwcRtlBtn) {
        nwcRtlBtn.addEventListener("click", function() {
          openServiceDetailModal("rtl.service", "Ride The Lightning", "rtl");
        });
      }
    }

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

    var restartBtn = document.getElementById("svc-detail-restart-btn");
    var restartResult = document.getElementById("svc-detail-restart-result");
    if (restartBtn && restartResult) {
      var RESTART_REFRESH_DELAY_MS = 3000;
      restartBtn.addEventListener("click", async function() {
        restartBtn.disabled = true;
        restartBtn.textContent = "Restarting…";
        restartResult.className = "svc-detail-restart-result";
        restartResult.textContent = "";

        try {
          await apiFetch("/api/service/" + encodeURIComponent(unit) + "/restart", { method: "POST" });
          restartResult.classList.add("success");
          restartResult.textContent = "✅ Service restarted successfully.";
          restartBtn.disabled = false;
          restartBtn.textContent = "🔄 Restart Service";
          setTimeout(function() {
            openServiceDetailModal(unit, name, icon);
          }, RESTART_REFRESH_DELAY_MS);
        } catch (e) {
          restartResult.classList.add("error");
          restartResult.textContent = e && e.message ? e.message : "Failed to restart service. Please check service logs and try again.";
          restartBtn.disabled = false;
          restartBtn.textContent = "🔄 Restart Service";
        }
      });
    }

    // Configure / Reconfigure Domain buttons (for non-feature services that need a domain)
    var configDomainBtn = document.getElementById("svc-detail-config-domain-btn");
    var reconfigDomainBtn = document.getElementById("svc-detail-reconfig-domain-btn");
    if ((configDomainBtn || reconfigDomainBtn) && data.needs_domain && data.domain_name) {
      var pseudoFeat = {
        id: data.domain_name,
        name: name,
        domain_name: data.domain_name,
        needs_ddns: true,
        extra_fields: []
      };
      if (configDomainBtn) configDomainBtn.addEventListener("click", function() {
        closeCredsModal();
        openDomainSetupModal(pseudoFeat, function() {
          openServiceDetailModal(unit, name, icon);
        });
      });
      if (reconfigDomainBtn) reconfigDomainBtn.addEventListener("click", function() {
        closeCredsModal();
        openDomainReconfigureModal(pseudoFeat, data.domain || "", function() {
          openServiceDetailModal(unit, name, icon);
        });
      });
    }
  } catch (err) {
    if ($credsBody) $credsBody.innerHTML = '<p class="creds-empty">Could not load service details.</p>';
  }
}

// ── Credentials info modal ────────────────────────────────────────

async function openCredsModal(unit, name, icon) {
  if (!$credsModal) return;
  _setCredsDialogWide(false);
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
    if (unit === "zeus-connect-setup.service") {
      html += '<div class="nwc-connect-guide">' +
        '<div class="nwc-connect-guide-title">📱 Connect to Zeus (Direct Node Access)</div>' +
        '<p class="nwc-connect-guide-intro">This QR is an <strong>LND REST</strong> connection — the direct way to use Zeus with your Lightning node for full admin control. It lets you manage channels, balances, and payments from your phone.</p>' +
        '<div class="nwc-connect-steps">' +
          '<div class="nwc-connect-step"><div class="nwc-step-num">1</div><div><strong>Download Zeus</strong> from the App Store or Google Play.</div></div>' +
          '<div class="nwc-connect-step"><div class="nwc-step-num">2</div><div>Open Zeus and go to <strong>Settings → Connect a node</strong> (or <strong>Scan Node Config</strong>).</div></div>' +
          '<div class="nwc-connect-step"><div class="nwc-step-num">3</div><div>Tap <strong>Scan LN node QR</strong> and scan the QR code above.</div></div>' +
          '<div class="nwc-connect-step"><div class="nwc-step-num">4</div><div>Review the connection details, then tap <strong>Save Node Config</strong>.</div></div>' +
        '</div>' +
        '<div class="nwc-connect-note"><strong>💡 Note:</strong> This is <em>not</em> the same as the NWC pairing QR shown in Lightning Wallet Connections — that gives your wallet sandboxed, limited access for everyday spending. LND REST connects Zeus directly to your node for full admin control.</div>' +
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
    '<div class="sys-chpw-header">' +
      '<div class="sys-chpw-title">🔑 Change Free Account &amp; Hub Login Password</div>' +
      '<div class="sys-chpw-desc">This updates the password for the <strong>free</strong> user account. <strong>This is also your Sovran Hub login password</strong> — both will change.</div>' +
    '</div>' +
    '<div class="matrix-form-group"><label class="matrix-form-label" for="sys-chpw-new">New Password</label>' +
    '<div class="pw-input-wrap">' +
    '<input class="matrix-form-input" type="password" id="sys-chpw-new" placeholder="New strong password" autocomplete="new-password">' +
    '<button type="button" class="pw-toggle-btn" id="sys-chpw-new-toggle" aria-label="Toggle password visibility">👁</button>' +
    '</div>' +
    '<div class="pw-hint">Password must be at least 8 characters.</div></div>' +
    '<div class="matrix-form-group"><label class="matrix-form-label" for="sys-chpw-confirm">Confirm Password</label>' +
    '<div class="pw-input-wrap">' +
    '<input class="matrix-form-input" type="password" id="sys-chpw-confirm" placeholder="Confirm new password" autocomplete="new-password">' +
    '<button type="button" class="pw-toggle-btn" id="sys-chpw-confirm-toggle" aria-label="Toggle password visibility">👁</button>' +
    '</div></div>' +
    '<div class="pw-credentials-note">⚠ This will change both your desktop login and Hub login password. After changing, your updated password will appear in the System Passwords credentials tile.</div>' +
    '<div class="matrix-form-actions">' +
    '<button class="matrix-form-back" id="sys-chpw-back-btn">← Back</button>' +
    '<button class="matrix-form-submit" id="sys-chpw-submit-btn">Change Password</button>' +
    '</div>' +
    '<div class="matrix-form-result" id="sys-chpw-result"></div>';

  document.getElementById("sys-chpw-back-btn").addEventListener("click", function() {
    openServiceDetailModal(unit, name, icon);
  });

  document.getElementById("sys-chpw-new-toggle").addEventListener("click", function() {
    var inp = document.getElementById("sys-chpw-new");
    var isHidden = inp.type === "password";
    inp.type = isHidden ? "text" : "password";
    this.textContent = isHidden ? "👁‍🗨" : "👁";
  });

  document.getElementById("sys-chpw-confirm-toggle").addEventListener("click", function() {
    var inp = document.getElementById("sys-chpw-confirm");
    var isHidden = inp.type === "password";
    inp.type = isHidden ? "text" : "password";
    this.textContent = isHidden ? "👁‍🗨" : "👁";
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

    if (newPassword.length < 8) {
      resultEl.className = "matrix-form-result error";
      resultEl.textContent = "Password must be at least 8 characters.";
      return;
    }

    if (newPassword !== confirmPassword) {
      resultEl.className = "matrix-form-result error";
      resultEl.textContent = "Passwords do not match.";
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
      resultEl.textContent = "✅ Free account & Hub login password changed successfully.";
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
