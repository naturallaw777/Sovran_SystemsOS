"use strict";

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

// Current role (set during init from /api/config)
let _currentRole = "server_plus_desktop";

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
// No longer needed — Update System moved to sidebar
// const $updateBtn      = document.getElementById("btn-update");
// const $updateBadge    = document.getElementById("update-badge");
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

// Upgrade modal (Node → Server+Desktop)
const $upgradeModal       = document.getElementById("upgrade-modal");
const $upgradeConfirmBtn  = document.getElementById("upgrade-confirm-btn");
const $upgradeCancelBtn   = document.getElementById("upgrade-cancel-btn");
const $upgradeCloseBtn    = document.getElementById("upgrade-close-btn");

// Legacy security warning state (populated by checkLegacySecurity in security.js)
var _securityIsLegacy       = false;
var _securityWarningMessage = "";

// System status banner
// (removed — health is now shown per-tile via the composite health field)