"""Sovran_SystemsOS Hub — FastAPI web server."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import glob
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import pwd
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from html import escape as _html_escape
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from .config import load_config, load_versions
from . import systemctl as sysctl
from . import nwc_hub_manager as _nwc_mgr
from . import support_ops as _support_ops
from .security_helpers import (
    _nix_escape,
    NPUB_RE,
    _validate_npub,
    _validate_ddns_url,
    _validate_ssh_pubkey,
    _DDNS_URL_MAX_LEN,
    _DDNS_CONTROL_RE,
    _DDNS_ALLOWED_HOSTNAMES,
    _SSH_PUBKEY_ALGORITHMS,
    _bech32_decode,
    _bech32_convertbits_decode,
    load_session_store,
    save_session_store,
)
from .update_state import effective_update_status

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────

FLAKE_LOCK_PATH = "/etc/nixos/flake.lock"
FLAKE_INPUT_NAME = "Sovran_Systems"
GITEA_API_BASE = "https://git.sovransystems.com/api/v1/repos/Sovran_Systems/Sovran_SystemsOS/commits"

UPDATE_LOG        = "/var/log/sovran-hub-update.log"
UPDATE_STATUS     = "/var/log/sovran-hub-update.status"
UPDATE_GENERATION = "/var/log/sovran-hub-update.generation"
UPDATE_UNIT       = "sovran-hub-update.service"

REBUILD_LOG    = "/var/log/sovran-hub-rebuild.log"
REBUILD_STATUS = "/var/log/sovran-hub-rebuild.status"
REBUILD_UNIT   = "sovran-hub-rebuild.service"
REBOOT_UNIT    = "sovran-hub-reboot.service"

# Set to True by _startup_recover_stale_status() when it corrects a stale
# RUNNING → SUCCESS/FAILED for the update unit.  Consumed by the first call
# to api_updates_status() so that the full log is returned to the frontend
# even when the frontend's offset is pointing past the pre-restart content.
_update_recovery_happened: bool = False
_cached_external_ip: str = "unavailable"
_domain_reachability_cache: dict[str, dict] = {}
_domain_reachability_cache_lock = Lock()
_DOMAIN_REACHABILITY_TTL = 60
_DOMAIN_REACHABILITY_STARTUP_DELAY = 5
_domain_reachability_task: asyncio.Task | None = None
_domain_reachability_task_lock = asyncio.Lock()

# Short-lived local diagnostics caches.  These values are only used for the
# dashboard's health hints, so a few seconds of staleness is preferable to
# launching several subprocesses and DNS lookups on every five-second poll.
_PORT_CACHE_TTL = 5
_port_cache_lock = Lock()
_listening_ports_cache: tuple[float, dict[str, set[int]]] = (0.0, {"tcp": set(), "udp": set()})
_firewall_ports_cache: tuple[float, dict[str, set[int]]] = (0.0, {"tcp": set(), "udp": set()})
_DOMAIN_DNS_CACHE_TTL = 60
_domain_dns_cache_lock = Lock()
_domain_dns_cache: dict[str, tuple[float, list[str]]] = {}

# Units to start after the next successful rebuild (feature enable flow)
_pending_service_starts: set[str] = set()
_pending_service_starts_lock = Lock()

BACKUP_LOG    = "/var/log/sovran-hub-backup.log"
BACKUP_STATUS = "/var/log/sovran-hub-backup.status"
BACKUP_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "sovran-hub-backup.sh")

CUSTOM_NIX  = "/etc/nixos/custom.nix"
HUB_BEGIN   = "  # ── Hub Managed (do not edit) ──────────────"
HUB_END     = "  # ── End Hub Managed ────────────────────────"
DOMAINS_DIR = "/var/lib/domains"
NOSTR_NPUB_FILE   = "/var/lib/secrets/nostr_npub"
NJALLA_SCRIPT     = "/var/lib/njalla/njalla.sh"
NJALLA_DDNS_URLS_FILE = "/var/lib/njalla/ddns_urls.json"

# Nostr npub validation, SSH pubkey validation, DDNS URL validation, and
# Nix escaping are imported from security_helpers (single source of truth).

# Systemd service that rewrites the Sovran-managed /etc/hosts loopback block
SOVRAN_HOSTS_SERVICE = "sovran-hosts-update.service"

# Caddy and its runtime Caddyfile generator (see modules/core/caddy.nix).
# caddy-generate-config.service rewrites /run/caddy/Caddyfile from
# /var/lib/domains/*; caddy.service serves that generated config.
CADDY_GENERATE_UNIT = "caddy-generate-config.service"
CADDY_UNIT          = "caddy.service"

# Domain keys that produce a public HTTPS virtual host via Caddy
_SERVICE_DOMAIN_KEYS = frozenset([
    "matrix", "wordpress", "nextcloud", "btcpayserver",
    "vaultwarden", "haven", "element-calling", "lightning",
])

INTERNAL_IP_FILE = "/var/lib/secrets/internal-ip"
ZEUS_CONNECT_FILE = "/var/lib/secrets/zeus-connect-url"

ONBOARDING_FLAG = "/var/lib/sovran/onboarding-complete"
AUTOLAUNCH_DISABLE_FLAG = "/var/lib/sovran/hub-autolaunch-disabled"

# ── Hub web authentication ────────────────────────────────────────

FREE_PASSWORD_FILE      = "/var/lib/secrets/free-password"
FREE_PASSWORD_FILE_WEB  = "/var/lib/secrets/free-password-web"
MIGRATION_NEWPASS_FILE  = "/var/lib/secrets/free-password-migration-newpass"
HUB_SESSION_SECRET_FILE  = "/var/lib/secrets/hub-session-secret"
SESSION_COOKIE_NAME      = "hub_session"
MANUAL_LOGOUT_COOKIE_NAME = "hub_manual_logout"
SESSION_MAX_AGE          = 86400  # 24 hours
# Chromium limits persistent cookies to roughly 400 days. This marker only
# suppresses desktop auto-login until the next successful password login.
MANUAL_LOGOUT_MAX_AGE    = 400 * 86400

# Sessions are persisted here so logins survive a restart of the Hub service.
# nixos-rebuild switch restarts sovran-hub-web.service during activation (its
# unit definition changes with every feature toggle — e.g. the Bitcoin
# PATH).  Without persistence the browser session dies mid-rebuild, the
# /api/rebuild/status polling starts receiving 401s and the rebuild modal
# hangs forever showing "Applying changes…".  The file lives in
# /var/lib/secrets so a security reset wipes it and forces a re-login, like
# the session secret itself.
SESSIONS_FILE = "/var/lib/secrets/hub-sessions.json"

# Session store: token → expiry timestamp (float).  Loaded lazily from
# SESSIONS_FILE on first use and written back on every meaningful change.
_sessions: dict[str, float] = {}
_sessions_loaded = False
_sessions_lock = Lock()

# Sliding the expiry on every authenticated request would rewrite the store on
# every poll, so persist slide-only updates at most this often.
_SESSION_PERSIST_MIN_INTERVAL = 30.0  # seconds
_sessions_last_persist = 0.0

# Failed login tracking: ip → list of failure timestamps
_login_failures: dict[str, list[float]] = {}
LOGIN_FAIL_DELAY  = 2.0   # seconds to sleep after a failed attempt
LOGIN_FAIL_WINDOW = 60.0  # rolling window (seconds) for counting failures
LOGIN_FAIL_MAX    = 10    # max failures in window before extra delay

# Public paths that are accessible without a valid session
_AUTH_EXEMPT_PATHS = {"/login", "/api/login", "/auto-login", "/api/ping"}
# Prefixes for static assets required by the login page
_AUTH_EXEMPT_PREFIXES = (
    "/static/css/",
    "/static/sovran-hub-icon.svg",
)

# ── Security constants ────────────────────────────────────────────

SECURITY_BANNER_DISMISSED_FLAG = "/var/lib/sovran/security-banner-dismissed"

# ── Tech Support constants ────────────────────────────────────────

SUPPORT_KEY_FILE = "/root/.ssh/sovran_support_authorized"
AUTHORIZED_KEYS  = "/root/.ssh/authorized_keys"
SUPPORT_STATUS_FILE = "/var/lib/secrets/support-session-status"

SUPPORT_KEY_COMMENT = "sovransystemsos-support"

# Maximum duration for a support session in seconds (24 hours).
# After this time the session is automatically expired on startup and on any
# support status/wallet operation.
SUPPORT_SESSION_MAX_SECONDS = 86400  # 24 hours

# Dedicated restricted support user (non-root) for wallet privacy
SUPPORT_USER              = "sovran-support"
SUPPORT_USER_HOME         = "/var/lib/sovran-support"
SUPPORT_USER_SSH_DIR      = "/var/lib/sovran-support/.ssh"
SUPPORT_USER_AUTH_KEYS    = "/var/lib/sovran-support/.ssh/authorized_keys"

# Audit log for all support session events
SUPPORT_AUDIT_LOG = "/var/log/sovran-support-audit.log"

# Time-limited wallet unlock state
WALLET_UNLOCK_FILE             = "/var/lib/secrets/support-wallet-unlock"
WALLET_UNLOCK_DURATION_DEFAULT = 3600  # seconds (1 hour)

# Wallet paths protected by default from the support user
PROTECTED_WALLET_PATHS: list[str] = [
    "/etc/nix-bitcoin-secrets",
    "/var/lib/bitcoind",
    "/var/lib/lnd",
    "/home",
]

# Server-side independent expiry timer for the active support session.
# Scheduled when a session is enabled; cancelled when disabled.
_support_expiry_timer: threading.Timer | None = None
_support_expiry_timer_lock = Lock()

CATEGORY_ORDER = [
    ("infrastructure", "Infrastructure"),
    ("bitcoin-base",   "Bitcoin Base"),
    ("bitcoin-apps",   "Bitcoin Apps"),
    ("communication",  "Communication"),
    ("apps",           "Self-Hosted Apps"),
    ("nostr",          "Nostr"),
    ("support",        "Support"),
    ("feature-manager", "Feature Manager"),
]

FEATURE_REGISTRY = [
    {
        "id": "rdp",
        "name": "Remote Desktop (RDP)",
        "description": "Access your desktop remotely via RDP client",
        "category": "infrastructure",
        "needs_domain": False,
        "domain_name": None,
        "needs_ddns": False,
        "extra_fields": [],
        "conflicts_with": [],
        "port_requirements": [],
    },
    {
        "id": "haven",
        "name": "Haven NOSTR Relay",
        "description": "Run your own private Nostr relay",
        "category": "nostr",
        "needs_domain": True,
        "domain_name": "haven",
        "needs_ddns": True,
        "extra_fields": [
            {
                "id": "nostr_npub",
                "label": "Nostr Public Key (npub1...)",
                "type": "text",
                "required": True,
                "current_value": "",
            },
        ],
        "conflicts_with": [],
        # Haven uses only 80/443, already covered by the main install alert
        "port_requirements": [],
    },
    {
        "id": "element-calling",
        "name": "Element Video & Audio Calling",
        "description": "Add video/audio calling to Matrix via LiveKit",
        "category": "communication",
        "needs_domain": True,
        "domain_name": "element-calling",
        "needs_ddns": True,
        "extra_fields": [],
        "conflicts_with": [],
        "requires": ["matrix_domain"],
        "port_requirements": [
            {"port": "80",          "protocol": "TCP",     "description": "HTTP (redirect to HTTPS)"},
            {"port": "443",         "protocol": "TCP",     "description": "HTTPS (domain)"},
            {"port": "7881",        "protocol": "TCP",     "description": "LiveKit WebRTC signalling"},
            {"port": "7882",        "protocol": "UDP",     "description": "LiveKit media (UDP mux)"},
            {"port": "5349",        "protocol": "TCP",     "description": "TURN over TLS"},
            {"port": "3478",        "protocol": "UDP",     "description": "TURN (STUN/relay)"},
            {"port": "30000-40000", "protocol": "TCP/UDP", "description": "TURN relay (WebRTC)"},
        ],
    },
    {
        "id": "nwc-wallets",
        "name": "Lightning Wallet Connections",
        "description": "Connect apps to isolated wallets on your Lightning node and create reusable Lightning Addresses.",
        "category": "bitcoin",
        "needs_domain": True,
        "domain_name": "lightning",
        "needs_ddns": True,
        "extra_fields": [],
        "conflicts_with": [],
        "port_requirements": [
            {"port": "80", "protocol": "TCP", "description": "HTTP (redirect to HTTPS)"},
            {"port": "443", "protocol": "TCP", "description": "HTTPS"},
        ],
    },
    {
        "id": "mempool",
        "name": "Mempool Explorer",
        "description": "Bitcoin mempool visualization and explorer",
        "category": "bitcoin",
        "needs_domain": False,
        "domain_name": None,
        "needs_ddns": False,
        "extra_fields": [],
        "conflicts_with": [],
        "port_requirements": [],
    },
    {
        "id": "bitcoin-tor-gossip",
        "name": "Advertise Tor IBD Node",
        "description": "Advertise this Bitcoin Core node's onion address through Bitcoin peer gossip so more Tor-capable nodes can discover it and request blocks.",
        "details": [
            "Your Tor IBD listener remains available whether or not advertising is enabled.",
            "Enabling this announces only the node's .onion P2P address; it does not publish your home IP address.",
            "Other Tor nodes can discover your node and request historical blocks while performing Initial Block Download (IBD).",
            "No clearnet port or router port forwarding is opened.",
            "Serving additional IBD peers can use significant upload bandwidth.",
        ],
        "category": "bitcoin",
        "modal_only": True,
        "needs_domain": False,
        "domain_name": None,
        "needs_ddns": False,
        "extra_fields": [],
        "conflicts_with": [],
        "requires": ["bitcoin-service"],
        "port_requirements": [],
    },
    {
        "id": "sshd",
        "name": "SSH Remote Access",
        "description": "Enable SSH for remote terminal access. Required for Tech Support. Disabled by default for security — enable only when needed.",
        "category": "support",
        "needs_domain": False,
        "domain_name": None,
        "needs_ddns": False,
        "extra_fields": [],
        "conflicts_with": [],
        "port_requirements": [
            {"port": "22", "protocol": "TCP", "description": "SSH"},
        ],
    },
    {
        "id": "btcpay-web",
        "name": "BTCPay Server Web Access",
        "description": "Expose BTCPay Server to the internet via your domain. When disabled, BTCPay Server still runs locally but is not accessible from the web.",
        "category": "bitcoin",
        "needs_domain": True,
        "domain_name": "btcpayserver",
        "needs_ddns": True,
        "extra_fields": [],
        "conflicts_with": [],
        "port_requirements": [
            {"port": "80",  "protocol": "TCP", "description": "HTTP (redirect to HTTPS)"},
            {"port": "443", "protocol": "TCP", "description": "HTTPS"},
        ],
    },
]

# Feature ids that have been removed/deprecated. The Hub must never write these
# back into custom.nix, and should strip any it finds (see startup migration).
DEPRECATED_FEATURE_IDS: set[str] = {"bitcoin-core"}

# Map feature IDs to their systemd units in config.json
FEATURE_SERVICE_MAP = {
    "rdp": "gnome-remote-desktop.service",
    "haven": "haven-relay.service",
    "element-calling": "livekit.service",
    "mempool": "mempool.service",
    "bitcoin-tor-gossip": None,
    "btcpay-web": "btcpayserver.service",
    "nwc-wallets": "albyhub.service",
    "sshd": "sshd.service",
}

# Port requirements for service tiles (keyed by unit name or icon)
_PORTS_ELEMENT_CALLING = [
    {"port": "7881",        "protocol": "TCP",     "description": "LiveKit WebRTC signalling"},
    {"port": "7882",        "protocol": "UDP",     "description": "LiveKit media (UDP mux)"},
    {"port": "5349",        "protocol": "TCP",     "description": "TURN over TLS"},
    {"port": "3478",        "protocol": "UDP",     "description": "TURN (STUN/relay)"},
    {"port": "30000-40000", "protocol": "TCP/UDP", "description": "TURN relay (WebRTC)"},
]

# Units whose port requirements exist purely so the user can forward them in
# their router.  Whether those ports actually work can only be judged from
# OUTSIDE the network, so we never show a local "ready/not ready" verdict for
# them and they never affect tile health — we just tell the user what to
# forward.  (E.g. the LiveKit TURN relay range is bound on demand, so a local
# `ss` check reports "closed" even on a perfectly working system.)
ROUTER_FORWARD_ONLY_UNITS: set[str] = {"livekit.service"}

SERVICE_PORT_REQUIREMENTS: dict[str, list[dict]] = {
    # Infrastructure
    "caddy.service":                    [],
    # Communication
    "matrix-synapse.service":           [],
    "livekit.service":                  _PORTS_ELEMENT_CALLING,
    # Domain-based apps (80/443 handled by end-to-end domain reachability checks)
    "btcpayserver.service":             [],
    "vaultwarden.service":              [],
    "phpfpm-nextcloud.service":         [],
    "phpfpm-wordpress.service":         [],
    "haven-relay.service":              [],
    "albyhub.service":                  [],
    "nwc-lnurl.service":                [],
    # SSH (only open when feature is enabled)
    "sshd.service":                     [{"port": "22", "protocol": "TCP", "description": "SSH"}],
}

# Maps service unit names to their domain file name in DOMAINS_DIR.
# Only services that require a domain are listed here.
SERVICE_DOMAIN_MAP: dict[str, str] = {
    "matrix-synapse.service":      "matrix",
    "btcpayserver.service":        "btcpayserver",
    "vaultwarden.service":         "vaultwarden",
    "phpfpm-nextcloud.service":    "nextcloud",
    "phpfpm-wordpress.service":    "wordpress",
    "haven-relay.service":         "haven",
    "livekit.service":             "element-calling",
    "albyhub.service":             "lightning",
}

# For features that share a unit, disambiguate by icon field
FEATURE_ICON_MAP: dict[str, str] = {}

ROLE_LABELS = {
    "server_plus_desktop": "Server + Desktop",
    "desktop":             "Desktop Only",
    "node":                "Bitcoin Node",
}

# Categories shown per role (None = show all)
ROLE_CATEGORIES: dict[str, set[str] | None] = {
    "server_plus_desktop": None,
    "desktop":             {"infrastructure", "support", "feature-manager"},
    "node":                {"infrastructure", "bitcoin-base", "bitcoin-apps", "support", "feature-manager"},
}

# Features shown per role (None = show all)
ROLE_FEATURES: dict[str, set[str] | None] = {
    "server_plus_desktop": None,
    "desktop":             {"rdp", "sshd"},
    "node":                {"rdp", "bitcoin-tor-gossip", "mempool", "btcpay-web", "nwc-wallets", "sshd"},
}

SERVICE_DESCRIPTIONS: dict[str, str] = {
    "bitcoind.service": (
        "The foundation of your financial sovereignty. Your node independently verifies "
        "every transaction and block — no banks, no intermediaries, no trust required. "
        "Powered by Sovran_SystemsOS, your node is always on and fully synced."
    ),
    "electrs.service": (
        "Your own Electrum indexing server. Connect any Electrum-compatible wallet "
        "directly to your node for maximum privacy — your transactions never touch "
        "a third-party server. Sovran_SystemsOS keeps it running and indexed automatically."
    ),
    "lnd.service": (
        "Your Lightning Network node for instant, low-fee Bitcoin payments. "
        "LND powers your Zeus wallet (via direct LND REST or Tor), Ride The Lightning dashboard, and BTCPayServer's "
        "Lightning capabilities. For mobile spending with sandboxed wallets, use Lightning Wallet Connections (NWC) instead."
    ),
    "rtl.service": (
        "Your personal Lightning Network command center. Open channels, manage liquidity, "
        "send payments, and monitor your node — all from a clean browser interface. "
        "Sovran_SystemsOS gives you full visibility into your Lightning operations."
    ),
    "btcpayserver.service": (
        "Your own payment processor — accept Bitcoin and Lightning payments directly, "
        "with zero fees to any third party. No Stripe, no Square, no middleman. "
        "Sovran_SystemsOS makes running a production-grade payment gateway as simple as flipping a switch."
    ),
    "zeus-connect-setup.service": (
        "Connect the Zeus mobile wallet to your Lightning node via LND REST over Tor. Send and receive "
        "Lightning payments from your phone using a direct node connection. "
        "Scan the QR code to add your node to Zeus, then enable Use Tor — this gives full node admin access."
    ),
    "mempool.service": (
        "Your own blockchain explorer and mempool visualizer. Monitor transactions, "
        "fee estimates, and blocks in real time — verified by your node, not someone else's. "
        "Sovran_SystemsOS runs it locally so your queries stay private."
    ),
    "matrix-synapse.service": (
        "Your own encrypted messaging server. Chat, call, and collaborate using Element "
        "or any Matrix client — every message is end-to-end encrypted and stored on hardware you control. "
        "No corporate surveillance, no data harvesting. Sovran_SystemsOS makes private communication effortless."
    ),
    "livekit.service": (
        "Encrypted voice and video calling, integrated directly with your Matrix server. "
        "Private video conferences without Zoom, Google Meet, or any third-party cloud. "
        "Sovran_SystemsOS handles the infrastructure — you just make the call."
    ),
    "vaultwarden.service": (
        "Your own password manager, compatible with all Bitwarden apps. Store passwords, "
        "credit cards, and secure notes across every device — synced through your server, "
        "never a third-party cloud. Sovran_SystemsOS keeps your vault always accessible and always private."
    ),
    "phpfpm-nextcloud.service": (
        "Your private cloud — file storage, calendar, contacts, and collaboration tools "
        "all running on your own hardware. Think Google Drive and Google Docs, but without Google. "
        "Sovran_SystemsOS delivers a full productivity suite that you actually own."
    ),
    "phpfpm-wordpress.service": (
        "Your own publishing platform, powered by the world's most popular CMS. "
        "Build websites, blogs, or online stores with full creative control and zero monthly hosting fees. "
        "Sovran_SystemsOS hosts it on your infrastructure — your content, your rules."
    ),
    "haven-relay.service": (
        "Your own Nostr relay for censorship-resistant social networking. Publish and receive notes "
        "on the Nostr protocol from infrastructure you control — no platform can silence you. "
        "Sovran_SystemsOS keeps your relay online and connected to the network."
    ),
    "caddy.service": (
        "The automatic HTTPS web server and reverse proxy powering all your services. "
        "Caddy handles SSL certificates, domain routing, and secure connections behind the scenes. "
        "Sovran_SystemsOS configures it automatically — you never have to touch a config file."
    ),
    "tor.service": (
        "The onion router, providing .onion addresses for your services. Access your node, "
        "wallet, and apps from anywhere in the world — privately and without port forwarding. "
        "Sovran_SystemsOS integrates Tor natively across your entire stack."
    ),
    "albyhub.service": (
        "Create isolated Lightning wallets for your apps and attach reusable Lightning "
        "Addresses on your Sovran_SystemsOS node."
    ),
    "gnome-remote-desktop.service": (
        "Access your server's full desktop environment from anywhere using any RDP client. "
        "Manage your system visually without being physically present. "
        "Sovran_SystemsOS sets up secure remote access with generated credentials — connect and go."
    ),
    "sshd.service": (
        "Secure Shell (SSH) remote access. When enabled, authorized users can connect "
        "to your machine over the network via encrypted terminal sessions. "
        "Sovran_SystemsOS keeps SSH disabled by default for maximum security — "
        "enable it only when you need remote access or Tech Support."
    ),
    "root-password-setup.service": (
        "Your system account credentials. These are the keys to your Sovran_SystemsOS machine — "
        "root access, user accounts, and SSH passphrases. Keep them safe."
    ),
    "sparrow-autoconnect.service": (
        "Sparrow Wallet is a privacy-focused Bitcoin desktop wallet for sending, receiving, "
        "and managing your Bitcoin. Sovran_SystemsOS automatically connects it to your local "
        "Electrs server on first boot — your address lookups, balances, and transactions "
        "never touch a third-party server. Full privacy, zero configuration.\n\n"
        "To use Sparrow Wallet, open it directly from your desktop — it's already installed and "
        "auto-configured to connect to your local Electrs server."
    ),
}

# ── Diceware password generation ─────────────────────────────────

_DICEWARE_WORDS = [
    "apple", "barn", "brook", "cabin", "cedar", "cloud", "coral", "crane",
    "delta", "eagle", "ember", "fern", "field", "flame", "flora", "flint",
    "frost", "grove", "haven", "hedge", "holly", "heron", "jade", "juniper",
    "kelp", "larch", "lemon", "lilac", "linden", "loch", "lotus", "maple",
    "marsh", "meadow", "mist", "mossy", "mount", "oak", "ocean", "olive",
    "petal", "pine", "pixel", "plum", "pond", "prism", "quartz", "raven",
    "ridge", "river", "robin", "rocky", "rose", "rowan", "sage", "sand",
    "sierra", "silver", "slate", "snow", "solar", "spark", "spruce", "stone",
    "storm", "summit", "swift", "thorn", "tide", "timber", "torch", "trout",
    "vale", "vault", "vine", "walnut", "wave", "willow", "wren", "amber",
    "aspen", "birch", "blaze", "bloom", "bluff", "coast", "copper", "crest",
    "dune", "elder", "fjord", "forge", "glade", "glen", "glow", "gulf",
]


def _generate_diceware_password() -> str:
    """Generate a human-readable diceware-style passphrase: word-word-word-N."""
    import secrets as _secrets
    words = [_secrets.choice(_DICEWARE_WORDS) for _ in range(3)]
    digit = _secrets.randbelow(10)
    return "-".join(words) + f"-{digit}"


# ── App setup ────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Sovran_SystemsOS Hub")


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        # Note: "cookies" is intentionally omitted so session cookies are not cleared
        response.headers["Clear-Site-Data"] = '"cache", "storage"'
        return response


# ── Session / authentication helpers ─────────────────────────────

def _get_or_create_session_secret() -> bytes:
    """Return the Hub session secret, generating it on first boot.

    The file is stored in /var/lib/secrets/ (mode 0600) so it is wiped
    automatically during a security reset, which forces re-login after reset.
    """
    try:
        with open(HUB_SESSION_SECRET_FILE, "rb") as f:
            data = f.read().strip()
            if len(data) >= 32:
                return data
    except FileNotFoundError:
        pass
    # Generate 32 random bytes and hex-encode for human readability
    token_bytes = secrets.token_bytes(32)
    token_hex = token_bytes.hex().encode()
    try:
        os.makedirs(os.path.dirname(HUB_SESSION_SECRET_FILE), exist_ok=True)
        with open(HUB_SESSION_SECRET_FILE, "wb") as f:
            f.write(token_hex)
        os.chmod(HUB_SESSION_SECRET_FILE, 0o600)
    except OSError:
        pass
    return token_hex


def _load_sessions_once() -> None:
    """Lazily load the persisted session store on first use (idempotent)."""
    global _sessions_loaded
    with _sessions_lock:
        if _sessions_loaded:
            return
        _sessions.update(load_session_store(SESSIONS_FILE))
        _sessions_loaded = True


def _persist_sessions(force: bool = False) -> None:
    """Write the session store to SESSIONS_FILE (best-effort).

    Expiry slides happen on every authenticated request, so non-forced
    persists are throttled; create/destroy/purge pass ``force=True``.
    """
    global _sessions_last_persist
    now = time.time()
    with _sessions_lock:
        if not force and (now - _sessions_last_persist) < _SESSION_PERSIST_MIN_INTERVAL:
            return
        snapshot = dict(_sessions)
        _sessions_last_persist = now
    save_session_store(SESSIONS_FILE, snapshot)


def _create_session() -> str:
    """Create a new opaque session token and register it in the store."""
    _load_sessions_once()
    _purge_expired_sessions()
    token = secrets.token_hex(32)
    _sessions[token] = time.time() + SESSION_MAX_AGE
    _persist_sessions(force=True)
    return token


def _destroy_session(token: str) -> None:
    """Remove a session token from the store."""
    _load_sessions_once()
    if _sessions.pop(token, None) is not None:
        _persist_sessions(force=True)


def _purge_expired_sessions() -> None:
    """Remove all expired sessions from the store."""
    _load_sessions_once()
    now = time.time()
    expired = [tok for tok, exp in _sessions.items() if exp <= now]
    for tok in expired:
        del _sessions[tok]
    if expired:
        _persist_sessions(force=True)


def _is_authenticated(request: Request) -> bool:
    """Return True if the request carries a valid, unexpired session cookie."""
    _load_sessions_once()
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return False
    expiry = _sessions.get(token)
    if expiry is None or time.time() >= expiry:
        if _sessions.pop(token, None) is not None:
            _persist_sessions(force=True)
        return False
    # Slide the expiry window on activity
    _sessions[token] = time.time() + SESSION_MAX_AGE
    _persist_sessions()  # throttled — don't rewrite the store on every poll
    return True


def _read_free_password() -> str | None:
    """Return the contents of the free-password secrets file, or None."""
    try:
        with open(FREE_PASSWORD_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return None




def _hash_password(password: str) -> str:
    """Return a scrypt-hash with 16-byte salt, formatted salt_hex:hash_hex."""
    salt = os.urandom(16)
    hashed = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return salt.hex() + ":" + hashed.hex()


def _check_password(submitted: str) -> bool:
    """Constant-time comparison against stored scrypt hash or legacy plaintext."""
    for fp in (FREE_PASSWORD_FILE_WEB, FREE_PASSWORD_FILE):
        try:
            with open(fp, "r") as f:
                stored = f.read().strip()
        except Exception:
            continue
        if not stored:
            continue
        if ":" in stored:
            try:
                salt_hex, hash_hex = stored.split(":", 1)
                salt = bytes.fromhex(salt_hex)
                submitted_hash = hashlib.scrypt(submitted.encode(), salt=salt, n=16384, r=8, p=1)
                if hmac.compare_digest(submitted_hash.hex().encode(), hash_hex.encode()):
                    return True
            except Exception:
                pass
        else:
            if hmac.compare_digest(submitted.encode(), stored.encode()):
                try:
                    with open(FREE_PASSWORD_FILE_WEB, "w") as f:
                        f.write(_hash_password(submitted))
                    os.chmod(FREE_PASSWORD_FILE_WEB, 0o600)
                except Exception:
                    pass
                return True
    return False


def _ensure_onboarding_reopened_for_migration() -> None:
    """Re-open onboarding when a migration password disclosure is pending."""
    if not os.path.isfile(MIGRATION_NEWPASS_FILE):
        return
    try:
        os.remove(ONBOARDING_FLAG)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Could not clear onboarding flag for migration flow: %s", exc)


def _record_failure(client_ip: str) -> None:
    """Record a failed login attempt and apply a rate-limit delay.

    Must always be called via loop.run_in_executor() so that the blocking
    time.sleep() does not stall the asyncio event loop.
    """
    now = time.time()
    failures = _login_failures.setdefault(client_ip, [])
    # Prune old entries outside the window
    _login_failures[client_ip] = [t for t in failures if now - t < LOGIN_FAIL_WINDOW]
    _login_failures[client_ip].append(now)
    # Sleep in the thread-pool thread to slow brute-force without blocking the loop
    time.sleep(LOGIN_FAIL_DELAY)


# ── Authentication middleware ─────────────────────────────────────

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public paths and static assets needed by the login page
        if path in _AUTH_EXEMPT_PATHS:
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in _AUTH_EXEMPT_PREFIXES):
            return await call_next(request)

        if not _is_authenticated(request):
            accept = request.headers.get("accept", "")
            if "text/html" in accept:
                return RedirectResponse(url="/login", status_code=303)
            return JSONResponse({"detail": "Unauthenticated"}, status_code=401)

        return await call_next(request)


app.add_middleware(AuthMiddleware)
app.add_middleware(NoCacheMiddleware)

_ICONS_DIR = os.environ.get(
    "SOVRAN_HUB_ICONS",
    os.path.join(os.path.dirname(_BASE_DIR), "icons"),
)
if os.path.isdir(_ICONS_DIR):
    app.mount(
        "/static/icons",
        StaticFiles(directory=_ICONS_DIR),
        name="icons",
    )

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(_BASE_DIR, "static")),
    name="static",
)

templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

# ── Static asset cache-busting ────────────────────────────────────

def _compute_asset_version() -> str:
    """Return a 16-char asset version from Nix store hash or static/template metadata."""
    nix_match = re.search(r"/nix/store/([a-z0-9]{32})-", os.path.realpath(_BASE_DIR))
    if nix_match:
        return nix_match.group(1)[:16]

    hasher = hashlib.sha256()
    for root in (
        os.path.join(_BASE_DIR, "static"),
        os.path.join(_BASE_DIR, "templates"),
    ):
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for filename in sorted(filenames):
                path = os.path.join(dirpath, filename)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                hasher.update(path.encode())
                hasher.update(b"\0")
                hasher.update(f"{stat.st_mtime_ns}:{stat.st_size}".encode())
                hasher.update(b"\0")
    return hasher.hexdigest()[:16]


ASSET_VERSION = _compute_asset_version()


def _file_hash(filename: str) -> str:
    """Return first 8 chars of the MD5 hex digest for a static file."""
    path = os.path.join(_BASE_DIR, "static", filename)
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except FileNotFoundError:
        return "0"

_ONBOARDING_JS_HASH = _file_hash("onboarding.js")

# ── Update check helpers ──────────────────────────────────────────

def _get_locked_info():
    try:
        with open(FLAKE_LOCK_PATH, "r") as f:
            lock = json.load(f)
        nodes = lock.get("nodes", {})
        node = nodes.get(FLAKE_INPUT_NAME, {})
        locked = node.get("locked", {})
        rev = locked.get("rev")
        branch = locked.get("ref")
        if not branch:
            branch = node.get("original", {}).get("ref")
        return rev, branch
    except Exception:
        pass
    return None, None


def _get_remote_rev(branch=None):
    try:
        url = GITEA_API_BASE + "?limit=1"
        if branch:
            url += f"&sha={branch}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("sha")
    except Exception:
        pass
    return None


def check_for_updates() -> bool | None:
    locked_rev, branch = _get_locked_info()
    remote_rev = _get_remote_rev(branch)
    if locked_rev and remote_rev:
        return locked_rev != remote_rev
    return None  # inconclusive — couldn't read lock or reach remote


# ── IP helpers ───────────────────────────────────────────────────

def _get_internal_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if parts:
                return parts[0]
    except Exception:
        pass
    return "unavailable"


def _save_internal_ip(ip: str):
    """Write the internal IP to a file so credentials can reference it."""
    if ip and ip != "unavailable":
        try:
            os.makedirs(os.path.dirname(INTERNAL_IP_FILE), exist_ok=True)
            with open(INTERNAL_IP_FILE, "w") as f:
                f.write(ip)
        except OSError:
            pass


def _get_external_ip() -> str:
    MAX_IP_LENGTH = 46
    for url in [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ]:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                ip = resp.read().decode().strip()
                if ip and len(ip) < MAX_IP_LENGTH:
                    return ip
        except Exception:
            continue
    return "unavailable"


# ── Port status helpers (local-only, no external calls) ──────────

def _get_listening_ports() -> dict[str, set[int]]:
    """Return sets of TCP and UDP ports that have services actively listening.

    Uses ``ss -tln`` for TCP and ``ss -uln`` for UDP.  Returns a dict with
    keys ``"tcp"`` and ``"udp"`` whose values are sets of integer port numbers.

    The ``ss`` LISTEN/UNCONN output has a fixed column layout when split on
    whitespace: ``State Recv-Q Send-Q Local_Address:Port Peer_Address:Port ...``
    The local address is always at index 3, regardless of address format
    (``0.0.0.0:PORT``, ``*:PORT``, ``[::]:PORT``, ``127.0.0.1:PORT``).

    Header lines (``State``/``Netid``) and non-LISTEN/UNCONN rows are skipped
    so only truly active listeners are returned.
    """
    result: dict[str, set[int]] = {"tcp": set(), "udp": set()}

    def _extract_port(addr: str) -> int | None:
        m = re.search(r":(\d+)$", addr)
        if not m:
            return None
        return int(m.group(1))

    for proto, flag in (("tcp", "-tln"), ("udp", "-uln")):
        try:
            proc = subprocess.run(
                ["ss", flag],
                capture_output=True, text=True, timeout=5,
            )
            logger.debug("ss %s rc=%s stderr=%r", flag, proc.returncode, proc.stderr.strip())
            logger.debug("ss %s output sample: %r", flag, "\n".join(proc.stdout.splitlines()[:8]))
            if proc.returncode != 0:
                continue
            for line in proc.stdout.splitlines():
                parts = line.split()
                if len(parts) < 5:
                    continue
                # Skip header lines
                if parts[0] in ("State", "Netid"):
                    continue
                # Only process LISTEN (TCP) or UNCONN (UDP) state lines
                if parts[0] not in ("LISTEN", "UNCONN"):
                    continue
                # Typical layout:
                # State Recv-Q Send-Q Local_Address:Port Peer_Address:Port ...
                # Be defensive and fall back to scanning for the first token that
                # looks like an address with a numeric port.
                local_addr = parts[3]
                port = _extract_port(local_addr)
                if port is None:
                    for token in parts[3:]:
                        port = _extract_port(token)
                        if port is not None:
                            break
                if port is not None:
                    result[proto].add(port)
        except Exception:
            pass
    logger.debug(
        "parsed listening ports: tcp=%s udp=%s",
        sorted(result["tcp"]),
        sorted(result["udp"]),
    )
    return result


def _get_firewall_allowed_ports() -> dict[str, set[int]]:
    """Return sets of TCP and UDP ports that the firewall allows.

    Tries ``nft list ruleset`` first (NixOS default), then falls back to
    ``iptables -L -n``.  Returns a dict with keys ``"tcp"`` and ``"udp"``.
    """
    result: dict[str, set[int]] = {"tcp": set(), "udp": set()}

    # ── nftables ─────────────────────────────────────────────────
    try:
        proc = subprocess.run(
            ["nft", "list", "ruleset"],
            capture_output=True, text=True, timeout=5,
        )
        logger.debug("nft list ruleset rc=%s stderr=%r", proc.returncode, proc.stderr.strip())
        logger.debug("nft output sample: %r", "\n".join(proc.stdout.splitlines()[:12]))
        if proc.returncode == 0:
            text = proc.stdout
            # Match patterns like: tcp dport 443 ... or tcp dport { 80, 443 } ...
            for proto in ("tcp", "udp"):
                for m in re.finditer(rf"{proto}\s+dport\s+\{{\s*([^}}]+?)\s*\}}", text):
                    raw = m.group(1)
                    for token in re.split(r'[\s,]+', raw):
                        token = token.strip()
                        if re.match(r'^\d+$', token):
                            result[proto].add(int(token))
                        elif re.match(r'^(\d+)-(\d+)$', token):
                            lo, hi = token.split("-")
                            result[proto].update(range(int(lo), int(hi) + 1))
                for m in re.finditer(rf"{proto}\s+dport\s+(\d+(?:-\d+)?)\b", text):
                    token = m.group(1)
                    if re.match(r'^\d+$', token):
                        result[proto].add(int(token))
                    else:
                        lo, hi = token.split("-")
                        result[proto].update(range(int(lo), int(hi) + 1))
            logger.debug(
                "parsed firewall ports from nft: tcp=%s udp=%s",
                sorted(result["tcp"]),
                sorted(result["udp"]),
            )
            return result
    except Exception:
        pass

    # ── iptables fallback ─────────────────────────────────────────
    try:
        proc = subprocess.run(
            ["iptables", "-L", "-n"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                # e.g. ACCEPT tcp  -- ... dpt:443  or  dpts:7882:7894
                m = re.search(r'(tcp|udp).*dpts?:(\d+)(?::(\d+))?', line)
                if m:
                    proto_match = m.group(1)
                    lo = int(m.group(2))
                    hi = int(m.group(3)) if m.group(3) else lo
                    result[proto_match].update(range(lo, hi + 1))
    except Exception:
        pass

    return result


def _get_listening_ports_cached() -> dict[str, set[int]]:
    """Return listening ports from a short-lived cache."""
    global _listening_ports_cache
    now = time.monotonic()
    with _port_cache_lock:
        cached_at, cached_value = _listening_ports_cache
        if now - cached_at < _PORT_CACHE_TTL:
            return cached_value

    value = _get_listening_ports()
    with _port_cache_lock:
        _listening_ports_cache = (now, value)
    return value


def _get_firewall_allowed_ports_cached() -> dict[str, set[int]]:
    """Return firewall ports from a short-lived cache."""
    global _firewall_ports_cache
    now = time.monotonic()
    with _port_cache_lock:
        cached_at, cached_value = _firewall_ports_cache
        if now - cached_at < _PORT_CACHE_TTL:
            return cached_value

    value = _get_firewall_allowed_ports()
    with _port_cache_lock:
        _firewall_ports_cache = (now, value)
    return value


def _resolve_all_addresses_cached(domain: str) -> list[str]:
    """Resolve a domain once per cache window for dashboard health checks."""
    now = time.monotonic()
    with _domain_dns_cache_lock:
        cached = _domain_dns_cache.get(domain)
        if cached is not None and now - cached[0] < _DOMAIN_DNS_CACHE_TTL:
            return cached[1]

    addresses = _resolve_all_addresses(domain)
    with _domain_dns_cache_lock:
        _domain_dns_cache[domain] = (now, addresses)
    return addresses


def _port_range_to_ints(port_str: str) -> list[int]:
    """Convert a port string like ``"443"``, ``"30000-40000"`` to a list of ints."""
    port_str = port_str.strip()
    if re.match(r'^\d+$', port_str):
        return [int(port_str)]
    m = re.match(r'^(\d+)-(\d+)$', port_str)
    if m:
        return list(range(int(m.group(1)), int(m.group(2)) + 1))
    return []


def _check_port_status(
    port_str: str,
    protocol: str,
    listening: dict[str, set[int]],
    allowed: dict[str, set[int]],
) -> str:
    """Return ``"listening"``, ``"firewall_open"``, ``"closed"``, or ``"unknown"``."""
    protos = []
    p = protocol.upper()
    if "TCP" in p:
        protos.append("tcp")
    if "UDP" in p:
        protos.append("udp")
    if not protos:
        protos = ["tcp"]

    ports = _port_range_to_ints(port_str)
    if not ports:
        return "unknown"

    ports_set = set(ports)
    is_listening = any(
        pt in listening.get(proto_key, set())
        for proto_key in protos
        for pt in ports_set
    )
    is_allowed = any(
        pt in allowed.get(proto_key, set())
        for proto_key in protos
        for pt in ports_set
    )

    # A process bound to the port is the authoritative signal; firewall
    # detection (nft/iptables) is only used as a secondary hint when nothing
    # is listening yet.
    if is_listening:
        return "listening"
    if is_allowed:
        return "firewall_open"
    return "closed"



# Regex for validating domain values written into /etc/hosts.  Rejects anything
# containing whitespace, newlines, or characters that could escape a hosts entry.
# NOTE: The equivalent pattern in modules/core/local-domain-loopback.nix (shell
# grep -E) must be kept in sync with this Python regex.
_SAFE_DOMAIN_RE = re.compile(
    r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
)


def _validate_domain_value(domain: str) -> bool:
    """Return True if *domain* is a valid hostname safe to write into /etc/hosts.

    Rejects values containing whitespace, newlines, or other characters that
    could inject additional entries or corrupt the hosts file.
    """
    if not domain or len(domain) > 253:
        return False
    # Guard against newline / whitespace injection before regex check.
    if any(c in domain for c in ('\n', '\r', ' ', '\t', '#')):
        return False
    return bool(_SAFE_DOMAIN_RE.match(domain))


def _is_loopback_address(ip: str) -> bool:
    """Return True if *ip* is a loopback address (127.0.0.0/8 or ::1)."""
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def _resolve_all_addresses(domain: str) -> list[str]:
    """Return all unique IP addresses that *domain* resolves to, or an empty list.

    The first element is the address that the system resolver would normally
    use for a connection.  All elements are checked when determining whether
    any address matches the expected public IP or is a loopback address.
    """
    try:
        results = socket.getaddrinfo(domain, None)
        unique_addresses: list[str] = []
        for r in results:
            addr = r[4][0]
            if addr not in unique_addresses:
                unique_addresses.append(addr)
        return unique_addresses
    except Exception:
        return []


def _trigger_hosts_update() -> None:
    """Start the sovran-hosts-update systemd service (best-effort, no-op if unavailable)."""
    try:
        subprocess.run(
            ["systemctl", "start", SOVRAN_HOSTS_SERVICE],
            timeout=30,
            check=False,
            capture_output=True,
        )
    except Exception:
        pass


def _check_domain_reachable(domain: str) -> dict:
    """Check HTTPS reachability for *domain* via local Caddy (loopback).

    Using ``--resolve`` ensures the request reaches Caddy on this computer
    without depending on router NAT loopback or the public DNS result.
    A successful local check is sufficient to confirm that Caddy and the
    virtual-host configuration are working correctly.
    """
    try:
        result = subprocess.run(
            [
                "curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
                "--max-time", "10",
                "--resolve", f"{domain}:443:127.0.0.1",
                "--resolve", f"{domain}:80:127.0.0.1",
                f"https://{domain}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        status_code = result.stdout.strip()
        if status_code and status_code.isdigit() and int(status_code) > 0:
            return {"reachable": True, "status_code": int(status_code), "via_loopback": True}
        return {"reachable": False, "error": result.stderr.strip() or "No response"}
    except subprocess.TimeoutExpired:
        return {"reachable": False, "error": "timeout"}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


def _check_domain_health_fast(domain: str | None, external_ip: str) -> bool:
    """Fast domain issue check for tile health (no curl/subprocess calls).

    Returns ``True`` when a domain issue is detected that warrants
    ``needs_attention``, ``False`` otherwise.
    Loopback resolution is treated as an intentional server-local override,
    not a DNS mismatch.
    """
    if not domain:
        return True

    addrs = _resolve_all_addresses(domain)
    if not addrs:
        return True

    # If every resolved address is loopback the intentional /etc/hosts
    # override is in place — this is healthy, not a mismatch.
    if all(_is_loopback_address(a) for a in addrs):
        return False

    if external_ip == "unavailable":
        return False
    return not any(a == external_ip for a in addrs)


def _is_domain_reachable_cached(domain: str) -> bool | None:
    """Return cached reachability, or ``None`` if not yet checked."""
    with _domain_reachability_cache_lock:
        entry = _domain_reachability_cache.get(domain)
    if entry is None:
        return None
    return bool(entry.get("reachable", False))


def _get_domain_reachability_cached(domain: str) -> dict | None:
    """Return cached domain reachability result, or ``None`` if not yet checked."""
    with _domain_reachability_cache_lock:
        entry = _domain_reachability_cache.get(domain)
    return dict(entry) if entry is not None else None


def _evaluate_domain_checklist(
    domain: str | None,
    external_ip: str,
    internal_ip: str | None = None,
    cached_reachability: dict | None = None,
    use_cached_reachability: bool = False,
) -> dict:
    """Evaluate sequential domain diagnostics and return UI-ready checklist data."""
    steps: list[dict] = []
    domain_status: dict = {
        "status": "not_set",
        "resolved_ip": None,
        "expected_ip": external_ip,
    }
    domain_reachable: dict | None = None

    if not domain:
        steps.append({
            "step": 1,
            "label": "Domain Configured",
            "status": "error",
            "detail": "No domain configured",
        })
        steps.append({
            "step": 2,
            "label": "DNS Points to Your Server",
            "status": "skipped",
            "detail": "Skipped until a domain is configured",
        })
        steps.append({
            "step": 3,
            "label": "Ports 80 & 443 Open",
            "status": "skipped",
            "detail": "Skipped until domain and DNS are configured",
        })
        return {
            "domain_status": domain_status,
            "domain_reachable": domain_reachable,
            "domain_check_steps": steps,
            "has_issues": True,
        }

    steps.append({
        "step": 1,
        "label": "Domain Configured",
        "status": "ok",
        "detail": domain,
    })

    addrs = _resolve_all_addresses(domain)
    resolved_ip: str | None = addrs[0] if addrs else None

    if not resolved_ip:
        domain_status = {
            "status": "unresolvable",
            "resolved_ip": None,
            "expected_ip": external_ip,
        }
        steps.append({
            "step": 2,
            "label": "DNS Points to Your Server",
            "status": "error",
            "detail": "Domain does not resolve — check your DNS provider",
        })
        steps.append({
            "step": 3,
            "label": "Ports 80 & 443 Open",
            "status": "skipped",
            "detail": "Skipped until DNS resolves to your server",
        })
        return {
            "domain_status": domain_status,
            "domain_reachable": domain_reachable,
            "domain_check_steps": steps,
            "has_issues": True,
        }

    # Detect intentional server-local loopback override from /etc/hosts.
    # When all addresses are loopback the public DNS is not checked via the
    # system resolver (which would always return the override).  We proceed
    # to the reachability check so Caddy health can still be verified.
    loopback_override = all(_is_loopback_address(a) for a in addrs)

    if loopback_override:
        domain_status = {
            "status": "local_override",
            "resolved_ip": resolved_ip,
            "expected_ip": external_ip,
        }
        steps.append({
            "step": 2,
            "label": "DNS / Local Override",
            "status": "ok",
            "detail": (
                "Server-local loopback override is active — this computer routes the domain "
                "directly to Caddy without going through the router. "
                "Public DNS cannot be verified from this computer while the override is in place. "
                "To check your public DNS from outside, use a tool such as "
                "https://dnschecker.org or run: dig @1.1.1.1 " + domain
            ),
        })
    elif external_ip == "unavailable":
        domain_status = {
            "status": "error",
            "resolved_ip": resolved_ip,
            "expected_ip": external_ip,
        }
        steps.append({
            "step": 2,
            "label": "DNS Points to Your Server",
            "status": "warning",
            "detail": f"Resolves to {resolved_ip} (external IP unavailable for comparison)",
        })
    elif not any(a == external_ip for a in addrs):
        domain_status = {
            "status": "dns_mismatch",
            "resolved_ip": resolved_ip,
            "expected_ip": external_ip,
        }
        steps.append({
            "step": 2,
            "label": "DNS Points to Your Server",
            "status": "error",
            "detail": f"Resolves to {resolved_ip} but your external IP is {external_ip}",
        })
        steps.append({
            "step": 3,
            "label": "Ports 80 & 443 Open",
            "status": "skipped",
            "detail": "Skipped until DNS points to your external IP",
        })
        return {
            "domain_status": domain_status,
            "domain_reachable": domain_reachable,
            "domain_check_steps": steps,
            "has_issues": True,
        }
    else:
        domain_status = {
            "status": "connected",
            "resolved_ip": resolved_ip,
            "expected_ip": external_ip,
        }
        steps.append({
            "step": 2,
            "label": "DNS Points to Your Server",
            "status": "ok",
            "detail": f"Resolves to {resolved_ip} (matches your external IP)",
        })

    if use_cached_reachability:
        domain_reachable = cached_reachability
    else:
        domain_reachable = _check_domain_reachable(domain)

    if domain_reachable is None:
        steps.append({
            "step": 3,
            "label": "Ports 80 & 443 Open",
            "status": "warning",
            "detail": "Checking reachability…",
        })
    elif domain_reachable.get("reachable"):
        status_code = domain_reachable.get("status_code")
        steps.append({
            "step": 3,
            "label": "Ports 80 & 443 Open",
            "status": "ok",
            "detail": f"HTTPS reachable (HTTP {status_code})",
        })
    else:
        internal = internal_ip or "your server"
        error_text = domain_reachable.get("error") or "No response"
        steps.append({
            "step": 3,
            "label": "Ports 80 & 443 Open",
            "status": "error",
            "detail": (
                f"Could not reach https://{domain} ({error_text}).\n"
                f"→ Forward ports 80 & 443 on your router to {internal}\n"
                "→ This only needs to be done once — all domain services share these ports\n"
                "→ Test from your phone on mobile data (your home network may not support hairpin NAT / loopback)"
            ),
        })

    has_issues = any(step.get("status") == "error" for step in steps[:3])
    return {
        "domain_status": domain_status,
        "domain_reachable": domain_reachable,
        "domain_check_steps": steps,
        "has_issues": has_issues,
    }


# ── QR code helper ────────────────────────────────────────────────

def _generate_qr_png_bytes(data: str, scale: int = 6, margin: int = 2) -> bytes | None:
    """Generate a QR code PNG and return the raw bytes.
    Uses qrencode CLI (available on the system via credentials.nix).

    High error-correction (H) is preferred for short payloads. Long
    lndconnect URIs can exceed version-40 capacity at H, so fall back to
    quartile then low ECC — otherwise the Hub shows an empty Zeus QR.
    """
    for ecc in ("H", "Q", "L"):
        try:
            result = subprocess.run(
                ["qrencode", "-o", "-", "-t", "PNG", "-s", str(scale), "-m", str(margin), "-l", ecc, data],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception:
            pass
    return None


def _generate_qr_svg(data: str, scale: int = 10, margin: int = 4) -> str | None:
    """Generate a QR code SVG document (resolution-independent, ideal if the
    user wants to embed the QR in a website or print it at any size)."""
    for ecc in ("H", "Q", "L"):
        try:
            result = subprocess.run(
                ["qrencode", "-o", "-", "-t", "SVG", "-s", str(scale), "-m", str(margin), "-l", ecc, data],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.decode("utf-8", errors="replace")
        except Exception:
            pass
    return None


def _generate_qr_base64(data: str) -> str | None:
    """Generate a QR code PNG and return it as a base64-encoded data URI."""
    png = _generate_qr_png_bytes(data, scale=6, margin=2)
    if png:
        b64 = base64.b64encode(png).decode("ascii")
        return f"data:image/png;base64,{b64}"
    return None


# ── Bech32 encoding (BIP-173) — used for LNURL strings (LUD-01) ──

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32_GENERATOR = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)


def _bech32_polymod(values: list[int]) -> int:
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for i in range(5):
            if (top >> i) & 1:
                chk ^= _BECH32_GENERATOR[i]
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _bech32_create_checksum(hrp: str, data: list[int]) -> list[int]:
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> (5 * (5 - i))) & 31 for i in range(6)]


def _bech32_convertbits(data: bytes, frombits: int, tobits: int) -> list[int]:
    acc = 0
    bits = 0
    ret: list[int] = []
    maxv = (1 << tobits) - 1
    for value in data:
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if bits:
        ret.append((acc << (tobits - bits)) & maxv)
    return ret


def _bech32_encode(hrp: str, payload: bytes) -> str:
    """Encode payload bytes as a bech32 string with the given HRP (BIP-173)."""
    data = _bech32_convertbits(payload, 8, 5)
    combined = data + _bech32_create_checksum(hrp, data)
    return hrp + "1" + "".join(_BECH32_CHARSET[d] for d in combined)


def _nwc_lnurl_bech32(alias: str, domain: str) -> str:
    """Return the LUD-01 bech32 LNURL for a wallet connection alias."""
    url = f"https://{domain}/.well-known/lnurlp/{alias}"
    return _bech32_encode("lnurl", url.encode("utf-8"))


# ── Update helpers (file-based, no systemctl) ────────────────────

def _write_update_status(status: str):
    """Write to the status file."""
    try:
        with open(UPDATE_STATUS, "w") as f:
            f.write(status)
    except OSError:
        pass


def _read_update_status() -> str:
    """Read and reconcile the persistent update status.

    ``REBOOT_REQUIRED`` survives Hub/browser restarts before the reboot, but
    it is a CLAIM about live NixOS state, not the source of truth: the boot
    default (``/nix/var/nix/profiles/system``) versus the running
    ``/run/current-system``.  Re-validating on every read keeps the Hub
    correct when the system was updated from a terminal or support session
    (which never writes Hub markers), and lets an old marker that predates
    the reconciliation feature self-heal instead of demanding reboots
    forever.  The stale marker file is removed once cleared.
    """
    try:
        with open(UPDATE_STATUS, "r") as f:
            status = f.read().strip()
    except FileNotFoundError:
        return "IDLE"

    effective = effective_update_status(status)
    if effective != status:
        _write_update_status(effective)
        try:
            os.remove(UPDATE_GENERATION)
        except OSError:
            pass
        return effective

    return status


def _read_log(offset: int = 0) -> tuple[str, int]:
    """Read the update log file from the given byte offset.
    Returns (new_text, new_offset)."""
    try:
        with open(UPDATE_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if offset > size:
                offset = 0
            f.seek(offset)
            chunk = f.read()
            return chunk.decode(errors="replace"), offset + len(chunk)
    except FileNotFoundError:
        return "", 0


# ── Credentials helpers ──────────────────────────────────────────

def _resolve_credential(cred: dict) -> dict | None:
    """Resolve a single credential entry to {label, value, ...}."""
    label = cred.get("label", "")
    prefix = cred.get("prefix", "")
    suffix = cred.get("suffix", "")
    extract = cred.get("extract", "")
    multiline = cred.get("multiline", False)
    qrcode = cred.get("qrcode", False)
    qronly = cred.get("qronly", False)

    # Static value
    if "value" in cred:
        result = {"label": label, "value": prefix + cred["value"] + suffix, "multiline": multiline}
        if qrcode:
            qr_data = _generate_qr_base64(result["value"])
            if qr_data:
                result["qrcode"] = qr_data
            else:
                # Don't hide the URI if we could not render a scannable QR.
                qronly = False
        if qronly:
            result["qronly"] = True
        return result

    # File-based value
    filepath = cred.get("file", "")
    if not filepath:
        return None

    try:
        with open(filepath, "r") as f:
            raw = f.read().strip()
    except (FileNotFoundError, PermissionError):
        return None

    if extract:
        # Extract a key=value from an env file (e.g., ADMIN_TOKEN=...)
        match = re.search(rf'{re.escape(extract)}=(.*)', raw)
        if match:
            raw = match.group(1).strip()
        else:
            return None

    # Detect scrypt hash (salt_hex:hash_hex) — passwords stored securely
    if re.match(r'^[0-9a-f]{32}:[0-9a-f]{64,}$', raw):
        value = "(stored securely — use Security Reset to set a new one)"
    else:
        value = prefix + raw + suffix
    result = {"label": label, "value": value, "multiline": multiline}

    if qrcode:
        qr_data = _generate_qr_base64(value)
        if qr_data:
            result["qrcode"] = qr_data
        else:
            # Don't hide the URI if we could not render a scannable QR.
            qronly = False

    if qronly:
        result["qronly"] = True

    return result


# ── Rebuild helpers (file-based, no systemctl) ───────────────────

def _read_rebuild_status() -> str:
    """Read the rebuild status file. Returns RUNNING, SUCCESS, FAILED, or IDLE."""
    try:
        with open(REBUILD_STATUS, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "IDLE"


def _read_rebuild_log(offset: int = 0) -> tuple[str, int]:
    """Read the rebuild log file from the given byte offset."""
    try:
        with open(REBUILD_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if offset > size:
                offset = 0
            f.seek(offset)
            chunk = f.read()
            return chunk.decode(errors="replace"), offset + len(chunk)
    except FileNotFoundError:
        return "", 0


# ── Backup helpers ────────────────────────────────────────────────

def _read_backup_status() -> str:
    """Read the backup status file. Returns RUNNING, SUCCESS, FAILED, or IDLE."""
    try:
        with open(BACKUP_STATUS, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "IDLE"


def _write_backup_status(value: str) -> None:
    """Write backup status file."""
    with open(BACKUP_STATUS, "w") as f:
        f.write(value)


def _read_backup_log(offset: int = 0) -> tuple[str, int]:
    """Read the backup log file from the given byte offset.
    Returns (new_text, new_offset)."""
    try:
        with open(BACKUP_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if offset > size:
                offset = 0
            f.seek(offset)
            chunk = f.read()
            return chunk.decode(errors="replace"), offset + len(chunk)
    except FileNotFoundError:
        return "", 0


def _append_backup_log(line: str) -> None:
    """Append one line to backup log."""
    with open(BACKUP_LOG, "a") as f:
        f.write(line.rstrip("\n") + "\n")


_INTERNAL_LABELS  = {"BTCEcoandBackup", "sovran_systemsos"}
_INTERNAL_MOUNTS  = {"/", "/boot/efi"}
_INTERNAL_MOUNT_PREFIX = "/run/media/Second_Drive"


def _is_internal_mount(mnt: str) -> bool:
    """Return True if *mnt* is a known internal system path."""
    if mnt in _INTERNAL_MOUNTS:
        return True
    if mnt == _INTERNAL_MOUNT_PREFIX or mnt.startswith(_INTERNAL_MOUNT_PREFIX + "/"):
        return True
    return False


def _is_supported_backup_fstype(path: str, fstype: str) -> bool:
    """Return whether the target filesystem type is supported for manual backup.

    Manual Backup requires ext4 for Linux metadata preservation (ACLs, xattrs,
    hard links). exFAT, FAT32, NTFS, and other filesystems are not supported.
    """
    fstype = (fstype or "").lower()
    return fstype == "ext4"


def _detect_external_drives() -> list[dict]:
    """Scan for mounted external USB drives.

    Uses ``lsblk`` to identify genuinely removable/hotplug devices and
    filters out internal system drives (BTCEcoandBackup, sovran_systemsos,
    /boot/efi, /run/media/Second_Drive).  Falls back to scanning
    /run/media/ directly if lsblk is unavailable, applying the same
    label/path filters.

    Returns:
        list[dict]: Each dict contains name, path, free_gb, total_gb, fstype.
    """
    import json as _json
    import subprocess as _subprocess

    drives: list[dict] = []
    seen_paths: set[str] = set()

    # ── Primary path: lsblk JSON ────────────────────────────────
    try:
        result = _subprocess.run(
            ["lsblk", "-J", "-o", "NAME,LABEL,FSTYPE,MOUNTPOINT,HOTPLUG,RM,TYPE"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = _json.loads(result.stdout)

            def _flatten(devs: list) -> list:
                out = []
                for d in devs:
                    out.append(d)
                    out.extend(_flatten(d.get("children") or []))
                return out

            for dev in _flatten(data.get("blockdevices", [])):
                dev_type   = dev.get("type", "")
                hotplug    = str(dev.get("hotplug", "0"))
                rm         = str(dev.get("rm", "0"))
                label      = dev.get("label") or ""
                fstype     = (dev.get("fstype") or "").lower()
                mountpoint = dev.get("mountpoint") or ""

                if dev_type not in ("part", "disk"):
                    continue
                if hotplug != "1" and rm != "1":
                    continue
                if not mountpoint:
                    continue
                if label in _INTERNAL_LABELS:
                    continue
                if _is_internal_mount(mountpoint):
                    continue
                if mountpoint in seen_paths:
                    continue

                try:
                    st = os.statvfs(mountpoint)
                    total_gb = round((st.f_blocks * st.f_frsize) / (1024 ** 3), 1)
                    free_gb  = round((st.f_bavail * st.f_frsize) / (1024 ** 3), 1)
                    name = label if label else os.path.basename(mountpoint)
                    drives.append({
                        "name":     name,
                        "path":     mountpoint,
                        "free_gb":  free_gb,
                        "total_gb": total_gb,
                        "fstype":   fstype,
                    })
                    seen_paths.add(mountpoint)
                except OSError:
                    pass

            if drives:
                return drives
    except Exception:  # lsblk not available or JSON parse error
        pass

    # ── Fallback: scan /run/media/ ───────────────────────────────
    media_root = "/run/media"
    if not os.path.isdir(media_root):
        return drives
    try:
        for user in os.listdir(media_root):
            user_path = os.path.join(media_root, user)
            if not os.path.isdir(user_path):
                continue
            for drive_name in os.listdir(user_path):
                drive_path = os.path.join(user_path, drive_name)
                if not os.path.isdir(drive_path):
                    continue
                if drive_name in _INTERNAL_LABELS:
                    continue
                if _is_internal_mount(drive_path):
                    continue
                if drive_path in seen_paths:
                    continue
                try:
                    st = os.statvfs(drive_path)
                    total_gb = round((st.f_blocks * st.f_frsize) / (1024 ** 3), 1)
                    free_gb  = round((st.f_bavail * st.f_frsize) / (1024 ** 3), 1)
                    fstype = ""
                    try:
                        fstype = _subprocess.run(
                            ["findmnt", "-n", "-o", "FSTYPE", "-T", drive_path],
                            capture_output=True, text=True, timeout=5
                        ).stdout.strip().lower()
                    except Exception:
                        fstype = ""
                    drives.append({
                        "name":     drive_name,
                        "path":     drive_path,
                        "free_gb":  free_gb,
                        "total_gb": total_gb,
                        "fstype":   fstype,
                    })
                    seen_paths.add(drive_path)
                except OSError:
                    pass
    except OSError:
        pass
    return drives


# ── custom.nix Hub Managed section helpers ────────────────────────

def _read_hub_overrides() -> tuple[dict, str | None, str | None, str | None]:
    """Parse the Hub Managed section inside custom.nix.
    Returns (features_dict, nostr_npub_or_none, timezone_or_none, locale_or_none)."""
    features: dict[str, bool] = {}
    nostr_npub = None
    timezone = None
    locale = None
    try:
        with open(CUSTOM_NIX, "r") as f:
            content = f.read()
        begin = content.find(HUB_BEGIN)
        end = content.find(HUB_END)
        if begin == -1 or end == -1:
            return features, nostr_npub, timezone, locale
        section = content[begin:end]
        for m in re.finditer(
            r'sovran_systemsOS\.features\.([a-zA-Z0-9_-]+)\s*=\s*(?:lib\.mkForce\s+)?(true|false)\s*;',
            section,
        ):
            feat_id = m.group(1)
            if feat_id not in DEPRECATED_FEATURE_IDS:
                features[feat_id] = m.group(2) == "true"
        for m in re.finditer(
            r'sovran_systemsOS\.web\.btcpayserver\s*=\s*(?:lib\.mkForce\s+)?(true|false)\s*;',
            section,
        ):
            features["btcpay-web"] = m.group(1) == "true"
        m2 = re.search(
            r'sovran_systemsOS\.nostr_npub\s*=\s*(?:lib\.mkForce\s+)?"([^"]*)"',
            section,
        )
        if m2:
            nostr_npub = m2.group(1)
        m3 = re.search(
            r'time\.timeZone\s*=\s*(?:lib\.mkForce\s+)?"([^"]*)"',
            section,
        )
        if m3:
            timezone = m3.group(1)
        m4 = re.search(
            r'i18n\.defaultLocale\s*=\s*(?:lib\.mkForce\s+)?"([^"]*)"',
            section,
        )
        if m4:
            locale = m4.group(1)
    except FileNotFoundError:
        pass
    return features, nostr_npub, timezone, locale


def _write_hub_overrides(features: dict, nostr_npub: str | None, timezone: str | None = None, locale: str | None = None) -> None:
    """Write the Hub Managed section inside custom.nix."""
    lines = []
    for feat_id, enabled in features.items():
        if feat_id in DEPRECATED_FEATURE_IDS:
            continue
        val = "true" if enabled else "false"
        if feat_id == "btcpay-web":
            lines.append(f"  sovran_systemsOS.web.btcpayserver = lib.mkForce {val};")
        else:
            lines.append(f"  sovran_systemsOS.features.{feat_id} = lib.mkForce {val};")
    if nostr_npub:
        lines.append(f'  sovran_systemsOS.nostr_npub = lib.mkForce "{_nix_escape(nostr_npub)}";')
    if timezone:
        lines.append(f'  time.timeZone = lib.mkForce "{_nix_escape(timezone)}";')
    if locale:
        lines.append(f'  i18n.defaultLocale = lib.mkForce "{_nix_escape(locale)}";')
    hub_block = (
        HUB_BEGIN + "\n"
        + "\n".join(lines) + ("\n" if lines else "")
        + HUB_END + "\n"
    )

    try:
        with open(CUSTOM_NIX, "r") as f:
            content = f.read()
    except FileNotFoundError:
        return

    begin = content.find(HUB_BEGIN)
    end = content.find(HUB_END)

    if begin != -1 and end != -1:
        # Replace existing hub section (include the HUB_END line itself)
        newline_after_end = content.find("\n", end)
        if newline_after_end == -1:
            end_of_marker = len(content)
        else:
            end_of_marker = newline_after_end + 1
        content = content[:begin] + hub_block + content[end_of_marker:]
    else:
        # Insert hub section just before the final closing }
        last_brace = content.rfind("}")
        if last_brace == -1:
            return
        content = content[:last_brace] + "\n" + hub_block + content[last_brace:]

    # Atomic write: write to a temp file next to custom.nix then rename so the
    # file is never left in a partially-written state if the process is killed.
    nix_dir = os.path.dirname(CUSTOM_NIX) or "."
    fd, tmp_path = tempfile.mkstemp(dir=nix_dir, prefix=".custom_nix_tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, CUSTOM_NIX)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _migrate_strip_deprecated_features() -> None:
    """One-time migration: remove deprecated feature lines from the Hub Managed
    section of custom.nix.  Any feature id in DEPRECATED_FEATURE_IDS is dropped
    while all other Hub-managed settings (other features, nostr_npub, timezone,
    locale) are preserved byte-for-byte in meaning.

    This is a no-op (and never raises) if CUSTOM_NIX is missing, unreadable, or
    contains no deprecated lines.
    """
    try:
        with open(CUSTOM_NIX, "r") as f:
            content = f.read()
    except (FileNotFoundError, OSError):
        return

    # Quick-exit: if none of the deprecated ids appear, nothing to do.
    hub_begin = content.find(HUB_BEGIN)
    hub_end = content.find(HUB_END)
    if hub_begin == -1 or hub_end == -1:
        return
    section = content[hub_begin:hub_end]
    if not any(f"features.{dep_id}" in section for dep_id in DEPRECATED_FEATURE_IDS):
        return

    try:
        features, nostr_npub, timezone, locale = _read_hub_overrides()
        # _read_hub_overrides already excludes DEPRECATED_FEATURE_IDS, so
        # calling _write_hub_overrides with its output drops the stale lines.
        _write_hub_overrides(features, nostr_npub, timezone, locale)
    except Exception:
        # Never let a migration failure break startup.
        logger.exception("_migrate_strip_deprecated_features: unexpected error (non-fatal)")


# ── Feature status helpers ─────────────────────────────────────────

def _is_feature_enabled_in_config(feature_id: str) -> bool | None:
    """Check whether a feature is enabled in the evaluated Hub configuration.

    Most features map directly to a systemd service. Modal-only settings are
    represented separately in ``config.json``. Returns ``None`` only when no
    evaluated state is available.
    """
    if feature_id == "btcpay-web":
        return False  # Default off in Node role; only on via explicit hub toggle

    cfg = load_config()

    if feature_id == "bitcoin-tor-gossip":
        state = cfg.get("feature_states", {}).get(feature_id)
        return bool(state) if state is not None else None

    unit = FEATURE_SERVICE_MAP.get(feature_id)
    if unit is None:
        return None
    for svc in cfg.get("services", []):
        if svc.get("unit") == unit:
            return svc.get("enabled", False)
    return None


def _is_sshd_feature_enabled() -> bool:
    """Check if the sshd feature is enabled via hub overrides or config."""
    overrides, *_ = _read_hub_overrides()
    if "sshd" in overrides:
        return bool(overrides["sshd"])
    config_state = _is_feature_enabled_in_config("sshd")
    return bool(config_state) if config_state is not None else False


# ── Tech Support helpers ──────────────────────────────────────────

def _is_support_active() -> bool:
    """Check if a per-session support key is currently installed."""
    _expire_support_if_stale()
    try:
        with open(SUPPORT_USER_AUTH_KEYS, "r") as f:
            return bool(f.read().strip())
    except FileNotFoundError:
        return False


def _expire_support_if_stale() -> bool:
    """If an active support session has passed its expiry time, disable it.

    Returns ``True`` if a session was expired, ``False`` otherwise.
    This is called automatically from ``_is_support_active()`` and from
    startup, so expiry is enforced even if the user never calls
    ``/api/support/disable``.
    """
    return _support_ops.expire_if_stale(
        SUPPORT_STATUS_FILE,
        clock_fn=time.time,
        disable_fn=_disable_support,
        audit_fn=_log_support_audit,
        max_session_seconds=float(SUPPORT_SESSION_MAX_SECONDS),
    )


def _get_support_session_info() -> dict:
    """Read support session metadata."""
    try:
        with open(SUPPORT_STATUS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _log_support_audit(event: str, details: str = "") -> None:
    """Append a timestamped event to the support audit log."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    line = f"[{timestamp}] {event}"
    if details:
        line += f": {details}"
    line += "\n"
    try:
        os.makedirs(os.path.dirname(SUPPORT_AUDIT_LOG), exist_ok=True)
        with open(SUPPORT_AUDIT_LOG, "a") as f:
            f.write(line)
    except Exception:
        pass


def _get_support_audit_log(max_lines: int = 100) -> list:
    """Return the last N lines from the audit log."""
    try:
        with open(SUPPORT_AUDIT_LOG, "r") as f:
            lines = f.readlines()
        return [l.rstrip("\n") for l in lines[-max_lines:]]
    except FileNotFoundError:
        return []


def _get_existing_wallet_paths() -> list:
    """Return the subset of PROTECTED_WALLET_PATHS that actually exist on disk."""
    return [p for p in PROTECTED_WALLET_PATHS if os.path.exists(p)]


def _ensure_support_user() -> bool:
    """Ensure the sovran-support restricted user exists. Returns True on success."""
    try:
        result = subprocess.run(
            ["id", SUPPORT_USER], capture_output=True, timeout=5,
        )
        if result.returncode == 0:
            return True
    except Exception:
        return False

    try:
        subprocess.run(
            [
                "useradd",
                "--system",
                "--no-create-home",
                "--home-dir", SUPPORT_USER_HOME,
                "--shell", "/bin/bash",
                "--comment", "Sovran Systems Support (restricted)",
                SUPPORT_USER,
            ],
            check=True, capture_output=True, timeout=15,
        )
        os.makedirs(SUPPORT_USER_HOME, mode=0o700, exist_ok=True)
        os.makedirs(SUPPORT_USER_SSH_DIR, mode=0o700, exist_ok=True)
        pw = pwd.getpwnam(SUPPORT_USER)
        os.chown(SUPPORT_USER_HOME, pw.pw_uid, pw.pw_gid)
        os.chown(SUPPORT_USER_SSH_DIR, pw.pw_uid, pw.pw_gid)
        return True
    except Exception:
        return False


def _apply_wallet_acls() -> bool:
    """Apply POSIX ACLs to deny the support user access to wallet directories.

    Sets a deny-all ACL entry (u:sovran-support:---) on each existing protected
    path. Returns True if all existing paths were handled without error.
    setfacl is tried; if it is not available the function returns False without
    raising so callers can warn the user appropriately.
    """
    existing = _get_existing_wallet_paths()
    if not existing:
        return True
    success = True
    for path in existing:
        try:
            result = subprocess.run(
                ["setfacl", "-R", "-m", f"u:{SUPPORT_USER}:---", path],
                capture_output=True, timeout=15,
            )
            if result.returncode != 0:
                success = False
        except FileNotFoundError:
            # setfacl not installed
            return False
        except Exception:
            success = False
    return success


def _revoke_wallet_acls() -> bool:
    """Remove the support user's deny ACL from wallet directories."""
    existing = _get_existing_wallet_paths()
    if not existing:
        return True
    success = True
    for path in existing:
        try:
            result = subprocess.run(
                ["setfacl", "-R", "-x", f"u:{SUPPORT_USER}", path],
                capture_output=True, timeout=15,
            )
            if result.returncode != 0:
                success = False
        except FileNotFoundError:
            return False
        except Exception:
            success = False
    return success


def _is_wallet_unlocked() -> bool:
    """Return True if the user has granted time-limited wallet access and it has not expired."""
    try:
        with open(WALLET_UNLOCK_FILE, "r") as f:
            data = json.load(f)
        return time.time() < data.get("expires_at", 0)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return False


def _get_wallet_unlock_info() -> dict:
    """Read wallet unlock state.  Re-locks and returns {} if the grant has expired."""
    try:
        with open(WALLET_UNLOCK_FILE, "r") as f:
            data = json.load(f)
        if time.time() >= data.get("expires_at", 0):
            try:
                os.remove(WALLET_UNLOCK_FILE)
            except FileNotFoundError:
                pass
            _apply_wallet_acls()
            _log_support_audit("WALLET_RELOCKED", "auto-expired")
            return {}
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# The exact base64 blob of the historical fleet-wide root support key is defined
# in support_ops.LEGACY_ROOT_KEY_BLOB and used by _remove_legacy_root_support_key().


def _remove_legacy_root_support_key() -> bool:
    """One-time upgrade migration: remove the exact historical fleet-wide support key.

    Identifies the key by its exact base64 blob, regardless of algorithm prefix
    or comment field.  All other keys, blank lines, and comment lines are
    preserved.  The file is written atomically.

    Returns ``True`` if the file was updated, ``False`` if unchanged or absent.
    """
    return _support_ops.remove_legacy_root_key(
        AUTHORIZED_KEYS,
        _support_ops.LEGACY_ROOT_KEY_BLOB,
        audit_fn=_log_support_audit,
    )


def _enable_support(pubkey: str) -> bool:
    """Install a per-session SSH public key for the restricted support user.

    The key is written only to the ``sovran-support`` account's
    ``authorized_keys`` (atomically); root's ``authorized_keys`` is never
    modified.  Applies POSIX ACLs to wallet directories to prevent access by
    the support user without explicit user consent.

    Args:
        pubkey: A validated Ed25519/ECDSA OpenSSH public key string (single line).
    """
    try:
        use_restricted_user = _ensure_support_user()

        if use_restricted_user:
            os.makedirs(SUPPORT_USER_SSH_DIR, mode=0o700, exist_ok=True)
            # Atomic write: mkstemp + os.replace
            fd, tmp_keys = tempfile.mkstemp(
                dir=SUPPORT_USER_SSH_DIR, prefix=".authorized_keys_tmp"
            )
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(pubkey.strip() + "\n")
                os.chmod(tmp_keys, 0o600)
                try:
                    pw = pwd.getpwnam(SUPPORT_USER)
                    os.chown(tmp_keys, pw.pw_uid, pw.pw_gid)
                except Exception:
                    pass
                os.replace(tmp_keys, SUPPORT_USER_AUTH_KEYS)
            except Exception:
                try:
                    os.unlink(tmp_keys)
                except OSError:
                    pass
                raise
            try:
                pw = pwd.getpwnam(SUPPORT_USER)
                os.chown(SUPPORT_USER_SSH_DIR, pw.pw_uid, pw.pw_gid)
            except Exception:
                pass
        else:
            # Support user could not be created; fail closed rather than
            # falling back to root's authorized_keys.
            return False

        acl_applied = _apply_wallet_acls() if use_restricted_user else False
        wallet_paths = _get_existing_wallet_paths()

        session_id = str(uuid.uuid4())
        expires_at = time.time() + SUPPORT_SESSION_MAX_SECONDS
        session_info = {
            "session_id": session_id,
            "enabled_at": time.time(),
            "enabled_at_human": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "expires_at": expires_at,
            "use_restricted_user": use_restricted_user,
            "wallet_protected": use_restricted_user,
            "acl_applied": acl_applied,
            "protected_paths": wallet_paths,
        }
        # Atomic write of session metadata
        status_dir = os.path.dirname(SUPPORT_STATUS_FILE)
        os.makedirs(status_dir, exist_ok=True)
        fd2, tmp_status = tempfile.mkstemp(dir=status_dir, prefix=".support-session-tmp")
        try:
            with os.fdopen(fd2, "w") as f:
                json.dump(session_info, f)
            os.replace(tmp_status, SUPPORT_STATUS_FILE)
        except Exception:
            try:
                os.unlink(tmp_status)
            except OSError:
                pass
            raise

        # Schedule server-side independent expiry timer
        _schedule_expiry_timer(session_id, expires_at)

        _log_support_audit(
            "SUPPORT_ENABLED",
            f"restricted_user={use_restricted_user} acl_applied={acl_applied} "
            f"protected_paths={len(wallet_paths)}",
        )
        return True
    except Exception:
        return False


def _schedule_expiry_timer(session_id: str, expires_at: float) -> None:
    """Schedule a server-side timer to expire the support session at ``expires_at``.

    Cancels any previously scheduled timer first.  The timer callback compares
    the stored session_id and expires_at to prevent a stale timer (for an
    older session) from revoking a replacement session.
    """
    global _support_expiry_timer
    delay = max(0.0, expires_at - time.time())
    with _support_expiry_timer_lock:
        if _support_expiry_timer is not None:
            _support_expiry_timer.cancel()
        t = threading.Timer(delay, _auto_expire_support, args=[session_id, expires_at])
        t.daemon = True
        t.start()
        _support_expiry_timer = t


def _cancel_expiry_timer() -> None:
    """Cancel the active server-side support expiry timer if one is running."""
    global _support_expiry_timer
    with _support_expiry_timer_lock:
        if _support_expiry_timer is not None:
            _support_expiry_timer.cancel()
            _support_expiry_timer = None


def _auto_expire_support(session_id: str, expected_expiry: float) -> None:
    """Timer callback: expire the session only if it still matches session_id / expires_at.

    A stale timer for an older session must never revoke a replacement session.
    """
    _support_ops.expire_if_stale(
        SUPPORT_STATUS_FILE,
        clock_fn=time.time,
        disable_fn=_disable_support,
        audit_fn=_log_support_audit,
        session_id=session_id,
        expected_expiry=expected_expiry,
        max_session_seconds=float(SUPPORT_SESSION_MAX_SECONDS),
    )


def _disable_support() -> bool:
    """Remove the per-session support key and restore wallet protection."""
    try:
        # Cancel any pending expiry timer
        _cancel_expiry_timer()

        # Remove from support user's authorized_keys
        try:
            os.remove(SUPPORT_USER_AUTH_KEYS)
        except FileNotFoundError:
            pass

        # Remove the dedicated key file (legacy path, best-effort)
        try:
            os.remove(SUPPORT_KEY_FILE)
        except FileNotFoundError:
            pass

        # Revoke any outstanding wallet unlock
        try:
            os.remove(WALLET_UNLOCK_FILE)
        except FileNotFoundError:
            pass

        # Re-apply deny ACLs to restore wallet protection
        _apply_wallet_acls()

        # Remove session metadata
        try:
            os.remove(SUPPORT_STATUS_FILE)
        except FileNotFoundError:
            pass

        _log_support_audit("SUPPORT_DISABLED")
        return True
    except Exception:
        return False


def _verify_support_removed() -> bool:
    """Verify the support key is truly gone from the support user's authorized_keys."""
    try:
        with open(SUPPORT_USER_AUTH_KEYS, "r") as f:
            if f.read().strip():
                return False
    except FileNotFoundError:
        pass
    return True


# ── Routes ───────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "asset_version": ASSET_VERSION,
        },
    )


@app.get("/auto-login")
async def auto_login_redirect(request: Request):
    """Localhost-only auto-login: create a session, set the cookie, and redirect to /.

    Only requests from 127.0.0.1 or ::1 are accepted so that remote clients on
    the LAN cannot bypass the password prompt by navigating to this URL.
    """
    client_ip = request.client.host if request.client else "unknown"
    if client_ip not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="Forbidden")
    # An explicit logout must take precedence over the desktop launcher's
    # localhost auto-login, including after the Hub window is closed/reopened.
    if request.cookies.get(MANUAL_LOGOUT_COOKIE_NAME) == "1":
        return RedirectResponse(url="/login", status_code=303)
    token = _create_session()
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,  # LAN-only appliance; no TLS on the Hub port
    )
    return response


class LoginRequest(BaseModel):
    password: str


@app.post("/api/login")
async def api_login(req: LoginRequest, request: Request):
    """Validate the Hub password and issue a session cookie."""
    client_ip = request.client.host if request.client else "unknown"
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(None, _check_password, req.password)
    if not ok:
        await loop.run_in_executor(None, _record_failure, client_ip)
        raise HTTPException(status_code=401, detail="Incorrect password")
    token = _create_session()
    response = JSONResponse({"ok": True})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,  # LAN-only appliance; no TLS on the Hub port
    )
    # A successful password login explicitly reverses a prior manual logout.
    response.delete_cookie(key=MANUAL_LOGOUT_COOKIE_NAME)
    return response


@app.post("/api/logout")
async def api_logout(request: Request):
    """Destroy the session and prevent desktop auto-login until password login."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        _destroy_session(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    response.set_cookie(
        key=MANUAL_LOGOUT_COOKIE_NAME,
        value="1",
        max_age=MANUAL_LOGOUT_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,  # LAN-only appliance; no TLS on the Hub port
    )
    return response


def _get_sovran_version() -> str:
    """Read the OS version to display in the Hub header.

    Resolution order (first match wins):
      1. ``sovran_version`` baked into the Nix-generated config.json — this
         is the authoritative, build-time value and is what's used on a
         real Sovran_SystemsOS install.
      2. ``/etc/nixos/VERSION`` — present on an installed system.
      3. A ``VERSION`` file shipped next to this package (installed by the
         Nix build) or in the repo root (local development checkout).
      4. A hard-coded fallback so the badge never renders a broken/empty
         value such as the old "vdev" placeholder.
    """
    try:
        version = load_config().get("sovran_version")
        if version:
            return str(version).strip().lstrip("vV")
    except Exception:
        pass

    for candidate in (
        "/etc/nixos/VERSION",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION"),
        "VERSION",
    ):
        try:
            with open(candidate, "r") as f:
                version = f.read().strip().lstrip("vV")
                if version and version.lower() != "dev":
                    return version
        except (FileNotFoundError, OSError):
            continue

    return "1.0.0"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    sovran_version = _get_sovran_version()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "asset_version": ASSET_VERSION,
            "sovran_version": sovran_version,
        },
    )


@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding(request: Request):
    _ensure_onboarding_reopened_for_migration()
    return templates.TemplateResponse(
        request=request,
        name="onboarding.html",
        context={
            "asset_version": ASSET_VERSION,
            "onboarding_js_hash": _ONBOARDING_JS_HASH,
        },
    )


@app.get("/api/onboarding/status")
async def api_onboarding_status():
    _ensure_onboarding_reopened_for_migration()
    complete = os.path.exists(ONBOARDING_FLAG)
    return {"complete": complete}


@app.post("/api/onboarding/complete")
async def api_onboarding_complete():
    os.makedirs(os.path.dirname(ONBOARDING_FLAG), exist_ok=True)
    try:
        with open(ONBOARDING_FLAG, "w") as f:
            f.write("")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write flag file: {exc}")

    # Trigger a NixOS rebuild now that domains/ports/SSL are configured.
    # This is especially important after a role upgrade (Node → Server+Desktop)
    # where the rebuild was deferred until onboarding collected all required config.
    try:
        open(REBUILD_LOG, "w").close()
    except OSError:
        pass

    await asyncio.create_subprocess_exec(
        "systemctl", "reset-failed", REBUILD_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "start", "--no-block", REBUILD_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()

    return {"ok": True}


@app.get("/api/migration/password-status")
async def api_migration_password_status():
    """Return whether a migration-generated password is awaiting acknowledgement."""
    try:
        with open(MIGRATION_NEWPASS_FILE, "r") as f:
            return {"pending": True, "password": f.read().strip()}
    except FileNotFoundError:
        return {"pending": False}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not read migration password: {exc}")


@app.post("/api/migration/password-acknowledge")
async def api_migration_password_acknowledge():
    """Acknowledge the migration password and update /etc/shadow to match."""
    # Read the new password before deleting the file
    new_password = None
    try:
        with open(MIGRATION_NEWPASS_FILE, "r") as f:
            new_password = f.read().strip()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not read migration password: {exc}")

    # Update /etc/shadow so GDM accepts the new password going forward
    if new_password:
        chpasswd_bin = (
            shutil.which("chpasswd")
            or ("/run/current-system/sw/bin/chpasswd"
                if os.path.isfile("/run/current-system/sw/bin/chpasswd") else None)
        )
        if chpasswd_bin:
            try:
                result = subprocess.run(
                    [chpasswd_bin],
                    input=f"free:{new_password}",
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    logger.warning(
                        "chpasswd failed during migration acknowledge (rc=%d): %s",
                        result.returncode,
                        (result.stderr or result.stdout).strip(),
                    )
            except Exception as exc:
                logger.warning("chpasswd exception during migration acknowledge: %s", exc)

        # Clear only the locked keyring databases, leaving the directory and 'default' pointer intact.
        keyring_dir = "/home/free/.local/share/keyrings"
        keyring_files = glob.glob(os.path.join(keyring_dir, "*.keyring"))
        for kf in keyring_files:
            try:
                os.remove(kf)
            except OSError as exc:
                logger.warning("Could not remove old keyring file %s: %s", kf, exc)

    # Clear the pending marker
    try:
        os.remove(MIGRATION_NEWPASS_FILE)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not clear migration password: {exc}")

    return {"ok": True}


# ── Auto-launch endpoints ─────────────────────────────────────────

@app.get("/api/autolaunch/status")
async def api_autolaunch_status():
    """Check if Hub auto-launch on login is enabled."""
    disabled = os.path.exists(AUTOLAUNCH_DISABLE_FLAG)
    return {"enabled": not disabled}


class AutolaunchToggleRequest(BaseModel):
    enabled: bool


@app.post("/api/autolaunch/toggle")
async def api_autolaunch_toggle(req: AutolaunchToggleRequest):
    """Enable or disable Hub auto-launch on login."""
    if req.enabled:
        # Remove the disable flag to enable auto-launch
        try:
            os.remove(AUTOLAUNCH_DISABLE_FLAG)
        except FileNotFoundError:
            pass
    else:
        # Create the disable flag to suppress auto-launch
        os.makedirs(os.path.dirname(AUTOLAUNCH_DISABLE_FLAG), exist_ok=True)
        try:
            with open(AUTOLAUNCH_DISABLE_FLAG, "w") as f:
                f.write("")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Could not write flag file: {exc}")
    return {"ok": True, "enabled": req.enabled}


@app.get("/api/config")
async def api_config():
    cfg = load_config()
    role = cfg.get("role", "server_plus_desktop")
    allowed_cats = ROLE_CATEGORIES.get(role)
    cats = CATEGORY_ORDER if allowed_cats is None else [
        c for c in CATEGORY_ORDER if c[0] in allowed_cats
    ]
    return {
        "role": role,
        "role_label": ROLE_LABELS.get(role, role),
        "category_order": cats,
        "feature_manager": True,
    }


ROLE_STATE_NIX = """\
# THIS FILE IS AUTO-GENERATED. DO NOT EDIT.
{ config, lib, ... }:
{
  sovran_systemsOS.roles.server_plus_desktop = lib.mkDefault true;
  sovran_systemsOS.roles.desktop = lib.mkDefault false;
  sovran_systemsOS.roles.node = lib.mkDefault false;
}
"""


@app.post("/api/role/upgrade-to-server")
async def api_upgrade_to_server():
    """Upgrade from Node role to Server+Desktop role."""
    cfg = load_config()
    if cfg.get("role", "server_plus_desktop") != "node":
        raise HTTPException(status_code=400, detail="Upgrade is only available for the Node role.")

    try:
        with open("/etc/nixos/role-state.nix", "w") as f:
            f.write(ROLE_STATE_NIX)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write role-state.nix: {exc}")

    # Reset onboarding so the wizard runs for the newly unlocked services
    try:
        os.remove(ONBOARDING_FLAG)
    except FileNotFoundError:
        pass

    # Don't rebuild yet — the user needs to configure domains, SSL email,
    # and ports first via the onboarding wizard. Reboot so onboarding runs.
    try:
        proc = await asyncio.create_subprocess_exec(
            "/run/current-system/sw/bin/systemctl", "start", "--no-block", REBOOT_UNIT,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to initiate reboot: {exc}")

    return {"ok": True, "status": "rebooting_to_onboarding"}


# ── Bitcoin IBD sync helper ───────────────────────────────────────

BITCOIN_DATADIR = "/run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node"

# Simple in-process cache: (timestamp, result)
_btc_sync_cache: tuple[float, dict | None] = (0.0, None)
_BTC_SYNC_CACHE_TTL = 5  # seconds

_BTC_VERSION_CACHE_TTL = 60  # seconds — version doesn't change at runtime

# Cache for ``bitcoind --version`` output (available even before RPC is ready)
_btcd_version_cache: tuple[float, str | None] = (0.0, None)



# ── Generic service version detection (NixOS store path) ─────────

# Regex to extract the version from a Nix store ExecStart path.
# Pattern:  /nix/store/<32-char-hash>-<name-segments>-<version>/...
# Name segments may begin with a letter or digit (e.g. 'python3', 'gtk3',
# 'lib32-foo') and consist of alphanumeric characters only (no underscores,
# since Nix store paths use hyphens as separators).
# The version is identified as the first token starting with digit.digit.
_NIX_STORE_VERSION_RE = re.compile(
    r"/nix/store/[a-z0-9]{32}-"                                         # hash prefix
    r"(?:[a-zA-Z0-9][a-zA-Z0-9]*(?:-[a-zA-Z0-9][a-zA-Z0-9]*)*)+"      # package name
    r"-(\d+\.\d+(?:\.\d+)*(?:[+-][a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*)?)/"  # version (group 1)
)

# Nix path suffixes that indicate a wrapper environment, not a real package version.
_NIX_WRAPPER_SUFFIX_RE = re.compile(
    r"-(?:env|wrapper|wrapped|script|hook|setup|compat)$"
)

# These two applications are downloaded into /var/lib/www at install time, so
# their PHP-FPM pool units identify the runtime but not the deployed application
# release. Read each application's own version file instead of reporting a PHP
# or Nix package version that can be unrelated to what Caddy is serving.
_DEPLOYED_WEB_APPLICATION_VERSION_FILES: dict[str, tuple[str, re.Pattern[str]]] = {
    "phpfpm-nextcloud.service": (
        "/var/lib/www/nextcloud/version.php",
        re.compile(r"^\s*\$OC_VersionString\s*=\s*['\"]([^'\"]+)['\"]\s*;", re.MULTILINE),
    ),
    "phpfpm-wordpress.service": (
        "/var/lib/www/wordpress/wp-includes/version.php",
        re.compile(r"^\s*\$wp_version\s*=\s*['\"]([^'\"]+)['\"]\s*;", re.MULTILINE),
    ),
}


def _get_deployed_web_application_version(unit: str) -> str | None:
    """Return the version embedded in a PHP application deployed under /var/lib/www."""
    spec = _DEPLOYED_WEB_APPLICATION_VERSION_FILES.get(unit)
    if spec is None:
        return None

    path, version_pattern = spec
    try:
        # The version files are short PHP metadata files. Limiting the read makes
        # this safe even if an installation is damaged or has been replaced.
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            contents = fh.read(64 * 1024)
    except OSError:
        return None

    match = version_pattern.search(contents)
    if match is None:
        return None

    version = match.group(1).strip()
    if not version or len(version) > 64:
        return None
    return version if version.startswith("v") else f"v{version}"


# Cache: unit → (monotonic_timestamp, version_str | None)
_svc_version_cache: dict[str, tuple[float, str | None]] = {}
_SVC_VERSION_CACHE_TTL = 300  # 5 minutes — versions only change on system update


def _get_service_version(unit: str) -> str | None:
    """Extract the version of a service.

    PHP applications deployed under /var/lib/www are read from their own version
    files. Other services first use the Nix-generated build-time version reference
    and then fall back to parsing a Nix store path in their systemd ExecStart.
    """
    if unit in _DEPLOYED_WEB_APPLICATION_VERSION_FILES:
        return _get_deployed_web_application_version(unit)

    try:
        versions_ref = load_versions()
        ver = versions_ref.get(unit)
        if ver and ver != "unknown":
            return ver if ver.startswith("v") else f"v{ver}"
    except Exception:
        pass

    now = time.monotonic()
    cached = _svc_version_cache.get(unit)
    if cached is not None:
        cached_at, cached_val = cached
        if now - cached_at < _SVC_VERSION_CACHE_TTL:
            return cached_val

    version: str | None = None
    try:
        result = subprocess.run(
            ["systemctl", "show", unit, "--property=ExecStart", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            m = _NIX_STORE_VERSION_RE.search(result.stdout)
            # Some wrapped systemd commands contain an escaped or nested
            # store path that the strict package-path expression misses. Fall
            # back to scanning each store path segment for the version token.
            if not m:
                for store_path in re.findall(r"/nix/store/[a-z0-9]{32}-[^\\s/\\\"]+", result.stdout):
                    candidates = re.findall(r"(?:^|-)(\\d+\\.\\d+(?:\\.\\d+)*(?:[+-][a-zA-Z0-9]+(?:\\.[a-zA-Z0-9]+)*)?)$", store_path)
                    if candidates:
                        m = type("_VersionMatch", (), {"group": lambda self, n: candidates[-1]})()
                        break
            if m:
                ver = m.group(1)
                # Strip a single trailing period (defensive; shouldn't appear in store paths)
                ver = ver[:-1] if ver.endswith(".") else ver
                # Skip Nix environment/wrapper suffixes that are not real versions
                if not _NIX_WRAPPER_SUFFIX_RE.search(ver):
                    version = ver if ver.startswith("v") else f"v{ver}"
    except Exception:
        pass

    _svc_version_cache[unit] = (now, version)
    return version




def _get_bitcoind_version() -> str | None:
    """Run ``bitcoind --version`` and return the raw version string, or None on error.

    Parses the first output line to extract the token after "version ".
    Works regardless of whether the RPC server is ready (IBD, warmup, etc.).
    Results are cached for 60 seconds (_BTC_VERSION_CACHE_TTL).
    """
    global _btcd_version_cache
    now = time.monotonic()
    cached_at, cached_val = _btcd_version_cache
    if now - cached_at < _BTC_VERSION_CACHE_TTL:
        return cached_val

    try:
        result = subprocess.run(
            ["bitcoind", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            first_line = result.stdout.splitlines()[0]
            m = re.search(r"version\s+(v?\S+)", first_line, re.IGNORECASE)
            if m:
                ver = m.group(1)
                _btcd_version_cache = (now, ver)
                return ver
    except Exception:
        pass

    _btcd_version_cache = (now, None)
    return None


def _format_bitcoin_version(raw_version: str) -> str:
    """Format a raw version string from ``bitcoind --version`` for display."""
    return raw_version


def _get_bitcoin_sync_info() -> dict | None:
    """Call bitcoin-cli getblockchaininfo and return parsed JSON, or None on error.

    Results are cached for _BTC_SYNC_CACHE_TTL seconds to avoid hammering
    bitcoin-cli on every /api/services poll cycle.
    """
    global _btc_sync_cache
    now = time.monotonic()
    cached_at, cached_val = _btc_sync_cache
    if now - cached_at < _BTC_SYNC_CACHE_TTL:
        return cached_val

    try:
        result = subprocess.run(
            ["bitcoin-cli", f"-datadir={BITCOIN_DATADIR}", "getblockchaininfo"],
            capture_output=True,
            text=True,
            # Sync progress is optional tile metadata.  Keep a cold/unavailable
            # node from delaying the initial dashboard response.
            timeout=3,
        )
        if result.returncode != 0:
            _btc_sync_cache = (now, None)
            return None
        info = json.loads(result.stdout)
        _btc_sync_cache = (now, info)
        return info
    except Exception:
        _btc_sync_cache = (now, None)
        return None


@app.get("/api/bitcoin/sync")
async def api_bitcoin_sync():
    """Return Bitcoin blockchain sync status directly from bitcoin-cli."""
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _get_bitcoin_sync_info)
    if info is None:
        return JSONResponse(
            status_code=503,
            content={"error": "bitcoin-cli unavailable or bitcoind not running"},
        )
    return {
        "blocks": info.get("blocks", 0),
        "headers": info.get("headers", 0),
        "verificationprogress": info.get("verificationprogress", 0),
        "initialblockdownload": info.get("initialblockdownload", False),
    }


@app.get("/api/bitcoin/version")
async def api_bitcoin_version():
    """Return the version string of the active bitcoind implementation."""
    loop = asyncio.get_event_loop()
    raw_ver = await loop.run_in_executor(None, _get_bitcoind_version)
    if raw_ver is None:
        return JSONResponse(
            status_code=503,
            content={"error": "bitcoind --version failed or bitcoind not on PATH"},
        )
    return {
        "version": _format_bitcoin_version(raw_ver),
        "raw_version": raw_ver,
    }


@app.get("/api/services")
async def api_services():
    started_at = time.monotonic()
    cfg = load_config()
    services = cfg.get("services", [])

    # Build reverse map: unit → feature_id (for features with a unit)
    unit_to_feature = {
        unit: feat_id
        for feat_id, unit in FEATURE_SERVICE_MAP.items()
        if unit is not None
    }

    loop = asyncio.get_event_loop()

    # Read runtime feature overrides from custom.nix Hub Managed section and
    # calculate each service's effective enabled state once.  The old code did
    # this inside every status coroutine and then launched one systemctl process
    # per tile; batching the state lookup keeps a slow D-Bus from multiplying
    # the dashboard's first-render latency.
    overrides, *_ = await loop.run_in_executor(None, _read_hub_overrides)
    effective_entries: list[tuple[dict, bool]] = []
    active_units_by_scope: dict[str, list[str]] = {}
    domain_names: set[str] = set()
    for entry in services:
        unit = entry.get("unit", "")
        scope = entry.get("type", "system")
        icon = entry.get("icon", "")
        enabled = entry.get("enabled", True)

        feat_id = unit_to_feature.get(unit)
        if feat_id is None:
            feat_id = FEATURE_ICON_MAP.get(icon)
        if feat_id is not None and feat_id in overrides:
            enabled = overrides[feat_id]

        effective_entries.append((entry, enabled))
        if enabled and unit:
            active_units_by_scope.setdefault(scope, []).append(unit)

        if enabled:
            domain_key = SERVICE_DOMAIN_MAP.get(unit)
            if domain_key:
                domain_path = os.path.join(DOMAINS_DIR, domain_key)
                try:
                    with open(domain_path, "r") as f:
                        domain = f.read(512).strip()
                    if domain:
                        domain_names.add(domain)
                except OSError:
                    pass

    async def resolve_domain(domain: str) -> tuple[str, list[str] | None]:
        """Resolve DNS off the event loop with a hard upper bound.

        A broken DNS server must not hold the entire dashboard response hostage.
        ``None`` means the lookup was inconclusive and the background checker can
        fill in the health result later; an empty list means DNS definitively
        returned no address.
        """
        try:
            addresses = await asyncio.wait_for(
                loop.run_in_executor(None, _resolve_all_addresses_cached, domain),
                timeout=2,
            )
            return domain, addresses
        except (asyncio.TimeoutError, OSError):
            return domain, None

    active_states_future = loop.run_in_executor(
        None, sysctl.active_states, active_units_by_scope
    )
    port_states_future = asyncio.gather(
        loop.run_in_executor(None, _get_listening_ports_cached),
        loop.run_in_executor(None, _get_firewall_allowed_ports_cached),
    )
    dns_states_future = asyncio.gather(
        *(resolve_domain(domain) for domain in sorted(domain_names))
    )
    # Bitcoin sync is supplementary tile metadata. Fetch it once alongside
    # the other diagnostics instead of duplicating RPC calls per tile.
    has_enabled_bitcoin = any(
        entry.get("unit") == "bitcoind.service" and enabled
        for entry, enabled in effective_entries
    )
    bitcoin_sync_future = (
        loop.run_in_executor(None, _get_bitcoin_sync_info)
        if has_enabled_bitcoin
        else asyncio.sleep(0, result=None)
    )
    (
        active_states,
        port_states,
        dns_states,
        bitcoin_sync_info,
    ) = await asyncio.gather(
        active_states_future,
        port_states_future,
        dns_states_future,
        bitcoin_sync_future,
    )
    listening_ports, firewall_ports = port_states
    resolved_domains = dict(dns_states)

    async def get_status(item: tuple[dict, bool]):
        entry, enabled = item
        unit = entry.get("unit", "")
        scope = entry.get("type", "system")
        icon = entry.get("icon", "")

        if enabled:
            status = active_states.get((scope, unit), "unknown")
        else:
            status = "disabled"

        creds = entry.get("credentials", [])
        has_credentials = len(creds) > 0

        port_requirements = SERVICE_PORT_REQUIREMENTS.get(unit, [])

        domain_key = SERVICE_DOMAIN_MAP.get(unit)
        needs_domain = domain_key is not None
        domain: str | None = None
        if domain_key:
            domain_path = os.path.join(DOMAINS_DIR, domain_key)
            try:
                with open(domain_path, "r") as f:
                    val = f.read(512).strip()
                    domain = val if val else None
            except OSError:
                domain = None
        cached_reachable: bool | None = None
        domain_reachability = None
        if needs_domain and domain and enabled:
            cached_reachable = _is_domain_reachable_cached(domain)
            if cached_reachable is None:
                domain_reachability = "checking"
            elif cached_reachable:
                domain_reachability = "reachable"
            else:
                domain_reachability = "unreachable"

        # Router-forwarded ports can only be verified from outside the network,
        # so they must not drive local health.
        health_port_requirements = (
            [] if unit in ROUTER_FORWARD_ONLY_UNITS else list(port_requirements)
        )
        if needs_domain:
            health_port_requirements = [
                {"port": "80", "protocol": "TCP"},
                {"port": "443", "protocol": "TCP"},
                *health_port_requirements,
            ]
        has_port_issues = False
        if health_port_requirements:
            for p in health_port_requirements:
                ps = _check_port_status(
                    str(p.get("port", "")),
                    str(p.get("protocol", "TCP")),
                    listening_ports,
                    firewall_ports,
                )
                if ps == "closed":
                    has_port_issues = True
                    break
        has_domain_issues = False
        if needs_domain and domain and enabled:
            # DNS was resolved concurrently above.  A timed-out lookup is
            # treated as unknown rather than as a hard failure; the background
            # reachability checker will refresh the health state without
            # delaying the first tile render.
            addrs = resolved_domains.get(domain)
            dns_ok = True
            if addrs is not None:
                if not addrs:
                    dns_ok = False
                elif all(_is_loopback_address(a) for a in addrs):
                    # Intentional server-local /etc/hosts override — not a mismatch.
                    dns_ok = True
                elif (
                    _cached_external_ip != "unavailable"
                    and not any(a == _cached_external_ip for a in addrs)
                ):
                    dns_ok = False

            if not dns_ok:
                has_domain_issues = True
            elif cached_reachable is False:
                has_domain_issues = True

        # Compute composite health
        sync_progress: float | None = None
        sync_blocks: int | None = None
        sync_headers: int | None = None
        sync_ibd: bool | None = None
        if not enabled:
            health = "disabled"
        elif status == "active":
            if has_port_issues:
                health = "needs_attention"
            elif has_domain_issues:
                health = "needs_attention"
            else:
                if needs_domain and domain:
                    health = "checking_reachability" if cached_reachable is None else "healthy"
                else:
                    health = "healthy"
            # Check Bitcoin IBD state from the single shared lookup above.
            if unit == "bitcoind.service" and enabled:
                if bitcoin_sync_info and bitcoin_sync_info.get("initialblockdownload"):
                    health = "syncing"
                    sync_progress = bitcoin_sync_info.get("verificationprogress", 0)
                    sync_blocks = bitcoin_sync_info.get("blocks", 0)
                    sync_headers = bitcoin_sync_info.get("headers", 0)
                    sync_ibd = True
        elif status == "inactive":
            # For enabled services that are inactive (e.g. socket-activated PHP-FPM),
            # still check domain/port health so status remains consistent with
            # other domain services when there are actionable issues.
            if has_port_issues:
                health = "needs_attention"
            elif has_domain_issues:
                health = "needs_attention"
            elif needs_domain and domain:
                health = "checking_reachability" if cached_reachable is None else "inactive"
            else:
                health = "inactive"
        elif status == "failed":
            health = "failed"
        else:
            health = status  # loading states, etc.

        service_data: dict = {
            "name": entry.get("name", ""),
            "unit": unit,
            "type": scope,
            "icon": icon,
            "enabled": enabled,
            "category": entry.get("category", "other"),
            "status": status,
            "health": health,
            "has_credentials": has_credentials,
            "port_requirements": port_requirements,
            "needs_domain": needs_domain,
            "domain": domain,
            "domain_reachability": domain_reachability,
        }
        if sync_ibd is not None:
            service_data["sync_ibd"] = sync_ibd
            service_data["sync_progress"] = sync_progress
            service_data["sync_blocks"] = sync_blocks
            service_data["sync_headers"] = sync_headers
        if unit == "bitcoind.service" and enabled:
            raw_ver = await loop.run_in_executor(None, _get_bitcoind_version)
            if raw_ver is not None:
                btc_ver = _format_bitcoin_version(raw_ver)
                service_data["bitcoin_version"] = btc_ver  # backwards compat
                service_data["version"] = btc_ver
        # ── Generic version for all services (Nix store path) ──────────
        if enabled and unit and "version" not in service_data:
            ver = await loop.run_in_executor(None, _get_service_version, unit)
            if ver is not None:
                service_data["version"] = ver
        return service_data

    results = await asyncio.gather(*[get_status(item) for item in effective_entries])
    elapsed = time.monotonic() - started_at
    logger.info("/api/services: %d services in %.3fs", len(results), elapsed)
    return list(results)


@app.get("/api/credentials/{unit}")
async def api_credentials(unit: str):
    """Return resolved credentials for a given service unit."""
    cfg = load_config()
    services = cfg.get("services", [])

    # Find the service entry matching this unit
    entry = None
    for s in services:
        if s.get("unit") == unit:
            creds = s.get("credentials", [])
            if creds:
                entry = s
                break

    if not entry:
        raise HTTPException(status_code=404, detail="No credentials for this service")

    loop = asyncio.get_event_loop()
    resolved = []
    for cred in entry.get("credentials", []):
        result = await loop.run_in_executor(None, _resolve_credential, cred)
        if result:
            resolved.append(result)

    return {
        "name": entry.get("name", ""),
        "credentials": resolved,
    }


@app.get("/api/service-detail/{unit}")
async def api_service_detail(unit: str, icon: str | None = None):
    """Return comprehensive details for a single service — status, credentials,
    port health, domain health, description, and IPs — in one API call."""
    cfg = load_config()
    services = cfg.get("services", [])

    # Build reverse map: unit → feature_id
    unit_to_feature = {
        u: feat_id
        for feat_id, u in FEATURE_SERVICE_MAP.items()
        if u is not None
    }

    loop = asyncio.get_event_loop()
    overrides, nostr_npub, *_ = await loop.run_in_executor(None, _read_hub_overrides)

    # Find the service config entry, preferring icon match when provided
    entry = None
    if icon:
        entry = next((s for s in services if s.get("unit") == unit and s.get("icon") == icon), None)
    if entry is None:
        entry = next((s for s in services if s.get("unit") == unit), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Service not found")

    icon = entry.get("icon", "")
    enabled = entry.get("enabled", True)

    feat_id = unit_to_feature.get(unit)
    if feat_id is None:
        feat_id = FEATURE_ICON_MAP.get(icon)
    if feat_id is not None and feat_id in overrides:
        enabled = overrides[feat_id]

    # Service status
    if enabled:
        status = await loop.run_in_executor(
            None, lambda: sysctl.is_active(unit, entry.get("type", "system"))
        )
    else:
        status = "disabled"

    # Credentials
    creds_list = entry.get("credentials", [])
    has_credentials = len(creds_list) > 0
    resolved_creds: list[dict] = []
    if has_credentials:
        for cred in creds_list:
            result = await loop.run_in_executor(None, _resolve_credential, cred)
            if result:
                resolved_creds.append(result)

    # Domain
    domain_key = SERVICE_DOMAIN_MAP.get(unit)
    needs_domain = domain_key is not None
    domain: str | None = None
    if domain_key:
        domain_path = os.path.join(DOMAINS_DIR, domain_key)
        try:
            with open(domain_path, "r") as f:
                val = f.read(512).strip()
                domain = val if val else None
        except OSError:
            domain = None

    # IPs
    internal_ip = await loop.run_in_executor(None, _get_internal_ip)
    external_ip = _cached_external_ip
    _save_internal_ip(internal_ip)

    # Domain diagnostics (sequential checklist)
    domain_status: dict | None = None
    domain_reachable: dict | None = None
    domain_check_steps: list[dict] = []
    has_domain_issues = False
    if needs_domain:
        cached_domain_reachability = (
            _get_domain_reachability_cached(domain) if domain else None
        )
        domain_eval = await loop.run_in_executor(
            None,
            _evaluate_domain_checklist,
            domain,
            external_ip,
            internal_ip,
            cached_domain_reachability,
            True,
        )
        domain_status = domain_eval.get("domain_status")
        domain_reachable = domain_eval.get("domain_reachable")
        domain_check_steps = domain_eval.get("domain_check_steps", [])
        has_domain_issues = bool(domain_eval.get("has_issues"))

    # Port requirements and statuses.
    #
    # For router-forward-only units we deliberately skip the local
    # listening/firewall probe: those ports live on the *router*, and a local
    # probe can neither prove nor disprove that forwarding works.  Reporting a
    # local verdict there confused users more than it helped, so the UI just
    # lists what to forward.
    port_requirements = SERVICE_PORT_REQUIREMENTS.get(unit, [])
    router_forward_only = unit in ROUTER_FORWARD_ONLY_UNITS
    port_statuses: list[dict] = []
    if port_requirements and not router_forward_only:
        listening, allowed = await asyncio.gather(
            loop.run_in_executor(None, _get_listening_ports),
            loop.run_in_executor(None, _get_firewall_allowed_ports),
        )
        for p in port_requirements:
            port_str = str(p.get("port", ""))
            protocol = str(p.get("protocol", "TCP"))
            ps = _check_port_status(port_str, protocol, listening, allowed)
            port_statuses.append({
                "port": port_str,
                "protocol": protocol,
                "status": ps,
                "description": p.get("description", ""),
            })
    # Ports the user must forward in their router (no local status — see above).
    router_ports = (
        [
            {
                "port": str(p.get("port", "")),
                "protocol": str(p.get("protocol", "TCP")),
                "description": p.get("description", ""),
            }
            for p in port_requirements
        ]
        if router_forward_only
        else []
    )

    # Compute composite health
    sync_progress: float | None = None
    sync_blocks: int | None = None
    sync_headers: int | None = None
    sync_ibd: bool | None = None
    if not enabled:
        health = "disabled"
    elif status == "active":
        has_port_issues = any(p["status"] == "closed" for p in port_statuses)
        health = "needs_attention" if (has_port_issues or has_domain_issues) else "healthy"
        # Check Bitcoin IBD state
        if unit == "bitcoind.service" and enabled:
            sync = await loop.run_in_executor(None, _get_bitcoin_sync_info)
            if sync and sync.get("initialblockdownload"):
                health = "syncing"
                sync_progress = sync.get("verificationprogress", 0)
                sync_blocks = sync.get("blocks", 0)
                sync_headers = sync.get("headers", 0)
                sync_ibd = True
    elif status == "inactive":
        # For enabled services that are inactive (e.g. socket-activated PHP-FPM),
        # still check domain/port health so detail health is consistent.
        has_port_issues = any(p["status"] == "closed" for p in port_statuses) if port_statuses else False
        if has_domain_issues or has_port_issues:
            health = "needs_attention"
        else:
            health = "inactive"
    elif status == "failed":
        health = "failed"
    else:
        health = status  # loading states, etc.

    # Build feature entry if this service is an addon feature
    feature_entry: dict | None = None
    if feat_id is not None:
        feat_meta = next((f for f in FEATURE_REGISTRY if f["id"] == feat_id), None)
        if feat_meta is not None:
            domain_name_feat = feat_meta.get("domain_name")
            domain_configured = True
            if domain_name_feat:
                domain_path_feat = os.path.join(DOMAINS_DIR, domain_name_feat)
                try:
                    with open(domain_path_feat, "r") as f:
                        domain_configured = bool(f.read(256).strip())
                except OSError:
                    domain_configured = False
            extra_fields = []
            for ef in feat_meta.get("extra_fields", []):
                ef_copy = dict(ef)
                if ef["id"] == "nostr_npub":
                    ef_copy["current_value"] = nostr_npub or ""
                extra_fields.append(ef_copy)
            feature_entry = {
                "id": feat_id,
                "name": feat_meta["name"],
                "description": feat_meta["description"],
                "category": feat_meta["category"],
                "enabled": enabled,
                "needs_domain": feat_meta.get("needs_domain", False),
                "domain_configured": domain_configured,
                "domain_name": domain_name_feat,
                "needs_ddns": feat_meta.get("needs_ddns", False),
                "extra_fields": extra_fields,
                "conflicts_with": feat_meta.get("conflicts_with", []),
                "port_requirements": feat_meta.get("port_requirements", []),
            }

    # Modal-only settings related to this service. These are intentionally not
    # rendered as standalone feature cards: the user encounters them in the
    # context where their consequences are easiest to understand.
    related_features: list[dict] = []
    if icon == "bitcoin-core":
        related_id = "bitcoin-tor-gossip"
        related_meta = next((f for f in FEATURE_REGISTRY if f["id"] == related_id), None)
        if related_meta is not None:
            if related_id in overrides:
                related_enabled = bool(overrides[related_id])
            else:
                config_state = _is_feature_enabled_in_config(related_id)
                related_enabled = bool(config_state) if config_state is not None else False
            related_features.append({
                "id": related_id,
                "name": related_meta["name"],
                "description": related_meta["description"],
                "details": related_meta.get("details", []),
                "category": related_meta["category"],
                "enabled": related_enabled,
                "available": bool(enabled),
                "needs_domain": False,
                "domain_configured": True,
                "domain_name": None,
                "needs_ddns": False,
                "extra_fields": [],
                "conflicts_with": related_meta.get("conflicts_with", []),
                "requires": related_meta.get("requires", []),
                "port_requirements": [],
            })

    service_detail: dict = {
        "name": entry.get("name", ""),
        "unit": unit,
        "icon": icon,
        "status": status,
        "health": health,
        "enabled": enabled,
        "description": SERVICE_DESCRIPTIONS.get(unit, ""),
        "has_credentials": has_credentials and bool(resolved_creds),
        "credentials": resolved_creds,
        "needs_domain": needs_domain,
        "domain": domain,
        "domain_name": domain_key,
        "domain_status": domain_status,
        "domain_reachable": domain_reachable,
        "domain_check_steps": domain_check_steps,
        "port_requirements": port_requirements,
        "port_statuses": port_statuses,
        "router_ports": router_ports,
        "external_ip": external_ip,
        "internal_ip": internal_ip,
        "feature": feature_entry,
        "related_features": related_features,
    }
    if sync_ibd is not None:
        service_detail["sync_ibd"] = sync_ibd
        service_detail["sync_progress"] = sync_progress
        service_detail["sync_blocks"] = sync_blocks
        service_detail["sync_headers"] = sync_headers
    if unit == "bitcoind.service" and enabled:
        loop = asyncio.get_event_loop()
        raw_ver = await loop.run_in_executor(None, _get_bitcoind_version)
        if raw_ver is not None:
            btc_ver = _format_bitcoin_version(raw_ver)
            service_detail["bitcoin_version"] = btc_ver  # backwards compat
            service_detail["version"] = btc_ver
    # ── Generic version for all services (Nix store path) ──────────
    if enabled and unit and "version" not in service_detail:
        ver = await loop.run_in_executor(None, _get_service_version, unit)
        if ver is not None:
            service_detail["version"] = ver
    return service_detail


@app.get("/api/network")
async def api_network():
    global _cached_external_ip
    loop = asyncio.get_event_loop()
    internal, external = await asyncio.gather(
        loop.run_in_executor(None, _get_internal_ip),
        loop.run_in_executor(None, _get_external_ip),
    )
    # Keep the internal-ip file in sync for credential lookups
    _save_internal_ip(internal)
    _cached_external_ip = external
    return {"internal_ip": internal, "external_ip": external}


class PortCheckRequest(BaseModel):
    ports: list[dict]


@app.post("/api/ports/status")
async def api_ports_status(req: PortCheckRequest):
    """Check port status locally using ss and firewall rules — no external calls."""
    loop = asyncio.get_event_loop()
    internal_ip, listening, allowed = await asyncio.gather(
        loop.run_in_executor(None, _get_internal_ip),
        loop.run_in_executor(None, _get_listening_ports),
        loop.run_in_executor(None, _get_firewall_allowed_ports),
    )

    port_results = []
    for p in req.ports:
        port_str = str(p.get("port", ""))
        protocol = str(p.get("protocol", "TCP"))
        status = _check_port_status(port_str, protocol, listening, allowed)
        port_results.append({
            "port": port_str,
            "protocol": protocol,
            "status": status,
        })

    return {"internal_ip": internal_ip, "ports": port_results}


@app.get("/api/ports/health")
async def api_ports_health():
    """Aggregate port health across all enabled services."""
    cfg = load_config()
    services = cfg.get("services", [])

    # Build reverse map: unit → feature_id (for features with a unit)
    unit_to_feature = {
        unit: feat_id
        for feat_id, unit in FEATURE_SERVICE_MAP.items()
        if unit is not None
    }

    loop = asyncio.get_event_loop()

    # Read runtime feature overrides from custom.nix Hub Managed section
    overrides, *_ = await loop.run_in_executor(None, _read_hub_overrides)

    # Collect port requirements for enabled services only
    enabled_port_requirements: list[tuple[str, str, list[dict]]] = []
    for entry in services:
        unit = entry.get("unit", "")
        icon = entry.get("icon", "")
        enabled = entry.get("enabled", True)

        feat_id = unit_to_feature.get(unit)
        if feat_id is None:
            feat_id = FEATURE_ICON_MAP.get(icon)
        if feat_id is not None and feat_id in overrides:
            enabled = overrides[feat_id]

        if not enabled:
            continue

        # Router-forwarded ports are not locally verifiable — excluded from
        # aggregate health so they can't raise a false alarm.
        if unit in ROUTER_FORWARD_ONLY_UNITS:
            continue

        ports = SERVICE_PORT_REQUIREMENTS.get(unit, [])
        if ports:
            enabled_port_requirements.append((entry.get("name", unit), unit, ports))

    # If no enabled services have port requirements, return ok with zero ports
    if not enabled_port_requirements:
        return {
            "total_ports": 0,
            "open_ports": 0,
            "closed_ports": 0,
            "status": "ok",
            "affected_services": [],
        }

    # Run port checks in parallel
    listening, allowed = await asyncio.gather(
        loop.run_in_executor(None, _get_listening_ports),
        loop.run_in_executor(None, _get_firewall_allowed_ports),
    )

    total_ports = 0
    open_ports = 0
    affected_services = []

    for name, unit, ports in enabled_port_requirements:
        closed = []
        for p in ports:
            port_str = str(p.get("port", ""))
            protocol = str(p.get("protocol", "TCP"))
            status = _check_port_status(port_str, protocol, listening, allowed)
            total_ports += 1
            if status in ("listening", "firewall_open"):
                open_ports += 1
            else:
                closed.append({
                    "port": port_str,
                    "protocol": protocol,
                    "description": p.get("description", ""),
                })
        if closed:
            affected_services.append({
                "name": name,
                "unit": unit,
                "closed_ports": closed,
            })

    closed_ports = total_ports - open_ports

    if closed_ports == 0:
        health_status = "ok"
    elif open_ports == 0:
        health_status = "critical"
    else:
        health_status = "partial"

    return {
        "total_ports": total_ports,
        "open_ports": open_ports,
        "closed_ports": closed_ports,
        "status": health_status,
        "affected_services": affected_services,
    }


@app.get("/api/updates/check")
async def api_updates_check():
    loop = asyncio.get_event_loop()
    status = await loop.run_in_executor(None, _read_update_status)
    if status in {"RUNNING", "REBOOT_REQUIRED"}:
        # Avoid a slow remote update check when there is already an operation
        # the dashboard needs to surface.
        return {"available": True, "status": status.lower()}

    available = await loop.run_in_executor(None, check_for_updates)
    # None means inconclusive (check failed) — report as available so the UI doesn't block
    return {"available": available is not False, "status": status.lower()}


@app.get("/api/ping")
async def api_ping():
    return {"ok": True}


@app.post("/api/service/{unit}/restart")
async def api_service_restart(unit: str):
    cfg = load_config()
    services = cfg.get("services", [])
    allowed_units = {
        str(s.get("unit", "")).strip()
        for s in services
        if s.get("unit")
    }
    if unit not in allowed_units:
        raise HTTPException(status_code=404, detail="Service not found")

    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "restart", unit,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to restart service: {exc}")

    if proc.returncode != 0:
        detail = stderr.decode(errors="ignore").strip() or "systemctl restart failed"
        raise HTTPException(status_code=500, detail=detail)

    return {"ok": True}


@app.post("/api/reboot")
async def api_reboot():
    try:
        proc = await asyncio.create_subprocess_exec(
            "/run/current-system/sw/bin/systemctl", "start", "--no-block", REBOOT_UNIT,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to initiate reboot")
    return {"ok": True}


@app.post("/api/updates/run")
async def api_updates_run():
    """Kick off the detached update systemd unit."""
    loop = asyncio.get_event_loop()

    # Check if the update unit is genuinely running (not just a stale file).
    # Do NOT call _recover_stale_status() here — it appends to the log file
    # which causes stale log content to appear in the frontend modal.
    status = await loop.run_in_executor(None, _read_update_status)
    if status == "RUNNING":
        unit_active = await loop.run_in_executor(
            None, lambda: sysctl.is_active(UPDATE_UNIT, "system")
        )
        if unit_active == "active":
            return {"ok": True, "status": "already_running"}
        # Stale RUNNING — clear it and fall through to the normal flow.
        _write_update_status("IDLE")
        try:
            with open(UPDATE_LOG, "w") as f:
                f.write("")
        except OSError:
            pass

    available = await loop.run_in_executor(None, check_for_updates)
    if available is False:  # only block when positively confirmed no updates
        # Clear stale status/log so they don't contaminate future modal opens.
        _write_update_status("IDLE")
        try:
            with open(UPDATE_LOG, "w") as f:
                f.write("")
        except OSError:
            pass
        return {"ok": True, "status": "no_updates"}

    # Clear stale status and log BEFORE starting the unit
    _write_update_status("RUNNING")
    try:
        with open(UPDATE_LOG, "w") as f:
            f.write("")
    except OSError:
        pass

    # Reset failed state if any
    await asyncio.create_subprocess_exec(
        "systemctl", "reset-failed", UPDATE_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    proc = await asyncio.create_subprocess_exec(
        "systemctl", "start", "--no-block", UPDATE_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()

    return {"ok": True, "status": "started"}


@app.get("/api/updates/status")
async def api_updates_status(offset: int = 0):
    """Poll endpoint: reads status file + log file.

    If the status file says RUNNING but the systemd unit is no longer active
    (e.g. the hub was restarted mid-update), correct the stale state before
    returning so the frontend is never permanently stuck.

    When recovery is detected (either during this call or at startup), the log
    is returned from offset 0 so the frontend receives the complete output.
    """
    global _update_recovery_happened
    loop = asyncio.get_event_loop()

    status = await loop.run_in_executor(None, _read_update_status)

    use_full_log = False

    # Detect and correct stale RUNNING state on every poll.
    if status == "RUNNING":
        corrected = await loop.run_in_executor(
            None, _recover_stale_status, UPDATE_STATUS, UPDATE_LOG, UPDATE_UNIT
        )
        if corrected:
            use_full_log = True
        status = await loop.run_in_executor(None, _read_update_status)

    # Honour a recovery that happened at server startup (stale RUNNING corrected
    # before the frontend had a chance to reconnect).
    if _update_recovery_happened:
        use_full_log = True
        _update_recovery_happened = False

    effective_offset = 0 if use_full_log else offset
    new_log, new_offset = await loop.run_in_executor(None, _read_log, effective_offset)

    running = (status == "RUNNING")
    result = "pending" if running else status.lower()

    return {
        "running": running,
        "result": result,
        "log": new_log,
        "offset": new_offset,
    }


# ── Tech Support endpoints ────────────────────────────────────────

@app.get("/api/support/status")
async def api_support_status():
    """Check if tech support SSH access is currently enabled."""
    loop = asyncio.get_event_loop()
    active = await loop.run_in_executor(None, _is_support_active)
    sshd_enabled = await loop.run_in_executor(None, _is_sshd_feature_enabled)
    session = await loop.run_in_executor(None, _get_support_session_info)
    unlock_info = await loop.run_in_executor(None, _get_wallet_unlock_info)
    wallet_unlocked = bool(unlock_info)
    return {
        "active": active,
        "sshd_enabled": sshd_enabled,
        "enabled_at": session.get("enabled_at"),
        "enabled_at_human": session.get("enabled_at_human"),
        "wallet_protected": session.get("wallet_protected", False),
        "acl_applied": session.get("acl_applied", False),
        "protected_paths": session.get("protected_paths", []),
        "wallet_unlocked": wallet_unlocked,
        "wallet_unlocked_until": unlock_info.get("expires_at") if wallet_unlocked else None,
        "wallet_unlocked_until_human": unlock_info.get("expires_at_human") if wallet_unlocked else None,
    }


class SupportEnableRequest(BaseModel):
    ssh_public_key: str


@app.post("/api/support/enable")
async def api_support_enable(req: SupportEnableRequest):
    """Install a per-session SSH public key for the restricted support account.

    The caller must supply a validated Ed25519 or ECDSA public key.  The key
    is installed only for the ``sovran-support`` restricted user; root's
    ``authorized_keys`` is never modified.  SSH must be enabled first.
    """
    # Validate the submitted public key before doing anything else
    try:
        validated_key = _validate_ssh_pubkey(req.ssh_public_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid SSH public key: {exc}")

    loop = asyncio.get_event_loop()

    # Gate: SSH feature must be enabled before support can be activated
    sshd_on = await loop.run_in_executor(None, _is_sshd_feature_enabled)
    if not sshd_on:
        raise HTTPException(
            status_code=400,
            detail="SSH must be enabled first. Please enable SSH Remote Access, then try again.",
        )

    ok = await loop.run_in_executor(None, _enable_support, validated_key)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to enable support access")
    return {"ok": True, "message": "Support access enabled"}


@app.post("/api/support/disable")
async def api_support_disable():
    """Remove the Sovran support SSH key and end the session."""
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(None, _disable_support)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to disable support access")

    # Verify it's actually gone
    verified = await loop.run_in_executor(None, _verify_support_removed)
    return {"ok": True, "verified": verified, "message": "Support access removed and verified"}


class WalletUnlockRequest(BaseModel):
    duration: int = WALLET_UNLOCK_DURATION_DEFAULT  # seconds


@app.post("/api/support/wallet-unlock")
async def api_support_wallet_unlock(req: WalletUnlockRequest):
    """Grant the support user time-limited access to wallet directories.

    Removes the deny ACL for the support user on all protected wallet paths.
    Access is automatically revoked when the timer expires (checked lazily on
    next status call) or when the support session is ended.
    """

    loop = asyncio.get_event_loop()
    active = await loop.run_in_executor(None, _is_support_active)
    if not active:
        raise HTTPException(status_code=400, detail="No active support session")

    duration = max(300, min(req.duration, 14400))  # clamp: 5 min – 4 hours
    expires_at = time.time() + duration
    expires_human = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(expires_at))

    # Remove ACL restrictions
    await loop.run_in_executor(None, _revoke_wallet_acls)

    unlock_info = {
        "unlocked_at": time.time(),
        "expires_at": expires_at,
        "expires_at_human": expires_human,
        "duration": duration,
    }
    os.makedirs(os.path.dirname(WALLET_UNLOCK_FILE), exist_ok=True)
    with open(WALLET_UNLOCK_FILE, "w") as f:
        json.dump(unlock_info, f)

    _log_support_audit(
        "WALLET_UNLOCKED",
        f"duration={duration}s expires={expires_human}",
    )
    return {
        "ok": True,
        "expires_at": expires_at,
        "expires_at_human": expires_human,
        "message": f"Wallet access granted for {duration // 60} minutes",
    }


@app.post("/api/support/wallet-lock")
async def api_support_wallet_lock():
    """Revoke wallet access and re-apply ACL protections."""
    loop = asyncio.get_event_loop()

    try:
        os.remove(WALLET_UNLOCK_FILE)
    except FileNotFoundError:
        pass

    await loop.run_in_executor(None, _apply_wallet_acls)
    _log_support_audit("WALLET_LOCKED", "user-initiated")
    return {"ok": True, "message": "Wallet access revoked"}


@app.get("/api/support/audit-log")
async def api_support_audit_log(limit: int = 100):
    """Return the last N lines of the support audit log."""
    limit = max(1, min(limit, 500))
    loop = asyncio.get_event_loop()
    lines = await loop.run_in_executor(None, _get_support_audit_log, limit)
    return {"entries": lines}


# ── Backup endpoints ──────────────────────────────────────────────

@app.get("/api/backup/status")
async def api_backup_status(offset: int = 0):
    """Poll endpoint: reads backup status file + log file."""
    loop = asyncio.get_event_loop()
    status = await loop.run_in_executor(None, _read_backup_status)
    new_log, new_offset = await loop.run_in_executor(None, _read_backup_log, offset)
    running = (status == "RUNNING")
    result = "pending" if running else status.lower()
    return {
        "running": running,
        "result":  result,
        "log":     new_log,
        "offset":  new_offset,
    }


@app.get("/api/backup/drives")
async def api_backup_drives():
    """Return a list of detected external drives under /run/media/."""
    loop = asyncio.get_event_loop()
    drives = await loop.run_in_executor(None, _detect_external_drives)
    return {"drives": drives}


async def _monitor_backup_subprocess(proc: asyncio.subprocess.Process) -> None:
    """Drain stderr, then mark status FAILED if backup subprocess exits unexpectedly."""
    stderr_chunks: list[bytes] = []

    async def _drain_stderr() -> None:
        if proc.stderr is not None:
            async for line in proc.stderr:
                stderr_chunks.append(line)

    drain_task = asyncio.create_task(_drain_stderr())
    rc = await proc.wait()
    await drain_task

    if rc == 0:
        return

    loop = asyncio.get_event_loop()
    status = await loop.run_in_executor(None, _read_backup_status)
    if status in {"SUCCESS", "FAILED"}:
        return

    detail = ""
    if stderr_chunks:
        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
        if stderr_text:
            detail = f" — stderr: {stderr_text}"
    msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Backup subprocess exited unexpectedly (code {rc}).{detail}"
    await loop.run_in_executor(None, _append_backup_log, msg)
    await loop.run_in_executor(None, _write_backup_status, "FAILED")


@app.post("/api/backup/run")
async def api_backup_run(target: str = ""):
    """Start the backup script as a background subprocess.
    Returns immediately; progress is read via /api/backup/status.
    """
    loop = asyncio.get_event_loop()
    status = await loop.run_in_executor(None, _read_backup_status)
    if status == "RUNNING":
        return {"ok": True, "status": "already_running"}

    drives = await loop.run_in_executor(None, _detect_external_drives)
    if not drives:
        raise HTTPException(status_code=400, detail="No external backup drive detected.")

    drive_map = {d.get("path", ""): d for d in drives if d.get("path")}
    if target:
        if target not in drive_map:
            raise HTTPException(status_code=400, detail="Selected backup target is not an available external drive.")
        selected = drive_map[target]
    else:
        selected = drives[0]

    selected_target = selected.get("path", "")
    selected_fstype = (selected.get("fstype") or "").lower()
    if selected_fstype and not _is_supported_backup_fstype(selected_target, selected_fstype):
        raise HTTPException(
            status_code=400,
            detail=f"Selected drive filesystem '{selected_fstype}' is not supported for manual backup. Manual Backup requires an ext4-formatted drive.",
        )

    # Clear stale log before starting
    try:
        with open(BACKUP_LOG, "w") as f:
            f.write("")
    except OSError:
        pass

    try:
        await loop.run_in_executor(None, _write_backup_status, "RUNNING")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not set backup status: {exc}")

    await loop.run_in_executor(
        None,
        _append_backup_log,
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting backup process…",
    )

    env = dict(os.environ)
    env["BACKUP_TARGET"] = selected_target

    bash_path = shutil.which("bash")
    if bash_path is None:
        no_bash_msg = (
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Cannot start backup:"
            " interpreter 'bash' not found on PATH."
            " Ensure pkgs.bash is in the sovran-hub-web service PATH."
        )
        await loop.run_in_executor(None, _append_backup_log, no_bash_msg)
        await loop.run_in_executor(None, _write_backup_status, "FAILED")
        raise HTTPException(
            status_code=500,
            detail="Backup interpreter (bash) not available. Check service PATH configuration.",
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            bash_path, BACKUP_SCRIPT,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except Exception as exc:
        await loop.run_in_executor(None, _append_backup_log, f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Failed to launch backup script: {exc}")
        await loop.run_in_executor(None, _write_backup_status, "FAILED")
        raise HTTPException(status_code=500, detail="Failed to launch backup process.")

    asyncio.create_task(_monitor_backup_subprocess(proc))
    return {"ok": True, "status": "started", "target": selected_target}


# ── Feature Manager endpoints ─────────────────────────────────────

@app.get("/api/features")
async def api_features():
    """Return all toggleable features with current state and domain requirements."""
    loop = asyncio.get_event_loop()
    overrides, nostr_npub, *_ = await loop.run_in_executor(None, _read_hub_overrides)

    ssl_email_path = os.path.join(DOMAINS_DIR, "sslemail")
    ssl_email_configured = os.path.exists(ssl_email_path)

    role = load_config().get("role", "server_plus_desktop")
    allowed_features = ROLE_FEATURES.get(role)
    registry = [
        f for f in FEATURE_REGISTRY
        if not f.get("modal_only")
        and (allowed_features is None or f["id"] in allowed_features)
    ]

    features = []
    for feat in registry:
        feat_id = feat["id"]

        # Determine enabled state:
        # 1. Check custom.nix Hub Managed section first (explicit hub toggle)
        # 2. Fall back to config.json services (features enabled in custom.nix)
        if feat_id in overrides:
            enabled = overrides[feat_id]
        else:
            config_state = _is_feature_enabled_in_config(feat_id)
            if config_state is not None:
                enabled = config_state
            else:
                enabled = False

        domain_name = feat.get("domain_name")
        domain_configured = True
        if domain_name:
            domain_path = os.path.join(DOMAINS_DIR, domain_name)
            try:
                with open(domain_path, "r") as f:
                    domain_configured = bool(f.read(256).strip())
            except OSError:
                domain_configured = False

        extra_fields = []
        for ef in feat.get("extra_fields", []):
            ef_copy = dict(ef)
            if ef["id"] == "nostr_npub":
                ef_copy["current_value"] = nostr_npub or ""
            extra_fields.append(ef_copy)

        entry: dict = {
            "id": feat_id,
            "name": feat["name"],
            "description": feat["description"],
            "category": feat["category"],
            "enabled": enabled,
            "needs_domain": feat.get("needs_domain", False),
            "domain_configured": domain_configured,
            "domain_name": domain_name,
            "needs_ddns": feat.get("needs_ddns", False),
            "extra_fields": extra_fields,
            "conflicts_with": feat.get("conflicts_with", []),
            "port_requirements": feat.get("port_requirements", []),
        }
        if "requires" in feat:
            entry["requires"] = feat["requires"]
        features.append(entry)

    return {"features": features, "ssl_email_configured": ssl_email_configured}


class FeatureToggleRequest(BaseModel):
    feature: str
    enabled: bool
    extra: dict = {}


@app.post("/api/features/toggle")
async def api_features_toggle(req: FeatureToggleRequest):
    """Enable or disable a feature and trigger a system rebuild."""
    feat_meta = next((f for f in FEATURE_REGISTRY if f["id"] == req.feature), None)
    if not feat_meta:
        raise HTTPException(status_code=404, detail="Feature not found")

    loop = asyncio.get_event_loop()
    features, nostr_npub, cur_tz, cur_locale = await loop.run_in_executor(None, _read_hub_overrides)

    if req.enabled:
        # Onion-address advertising is only meaningful while the Bitcoin Core
        # service is enabled. The control is shown in that service's modal, but
        # enforce the dependency server-side as well.
        if req.feature == "bitcoin-tor-gossip":
            bitcoin_core_enabled = any(
                svc.get("unit") == "bitcoind.service"
                and svc.get("icon") == "bitcoin-core"
                and bool(svc.get("enabled", False))
                for svc in load_config().get("services", [])
            )
            if not bitcoin_core_enabled:
                raise HTTPException(
                    status_code=400,
                    detail="Enable the Bitcoin service before advertising its Tor IBD service.",
                )

        # Element-calling requires matrix domain
        if req.feature == "element-calling":
            if not os.path.exists(os.path.join(DOMAINS_DIR, "matrix")):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Element Calling requires a Matrix domain to be configured. "
                        "Element Calling requires a Matrix domain to be configured. Please configure it through the Sovran Hub web interface."
                    ),
                )

        # Domain requirement check
        if feat_meta.get("needs_domain") and feat_meta.get("domain_name"):
            domain_path = os.path.join(DOMAINS_DIR, feat_meta["domain_name"])
            if not os.path.exists(domain_path):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "domain_required",
                        "domain_name": feat_meta["domain_name"],
                    },
                )

        # Haven requires nostr_npub
        if req.feature == "haven":
            npub = (req.extra or {}).get("nostr_npub", "").strip()
            if npub:
                if not _validate_npub(npub):
                    raise HTTPException(status_code=400, detail="Invalid Nostr npub (must be npub1 followed by 58 bech32 characters with valid checksum)")
                nostr_npub = npub
            elif not nostr_npub:
                raise HTTPException(status_code=400, detail="nostr_npub is required for Haven")

        # Auto-disable conflicting features
        for conflict_id in feat_meta.get("conflicts_with", []):
            features[conflict_id] = False

        features[req.feature] = True
    else:
        features[req.feature] = False

    # Persist any extra fields (nostr_npub)
    new_npub = (req.extra or {}).get("nostr_npub", "").strip()
    if new_npub:
        if not _validate_npub(new_npub):
            raise HTTPException(status_code=400, detail="Invalid Nostr npub (must be npub1 followed by 58 bech32 characters with valid checksum)")
        nostr_npub = new_npub
        try:
            os.makedirs(os.path.dirname(NOSTR_NPUB_FILE), exist_ok=True)
            with open(NOSTR_NPUB_FILE, "w") as f:
                f.write(nostr_npub)
        except OSError:
            pass

    await loop.run_in_executor(None, _write_hub_overrides, features, nostr_npub, cur_tz, cur_locale)

    # When enabling a feature that relies on dynamic DNS, refresh the Njal.la
    # records right away instead of waiting for the 15-minute timer tick.
    # The newly enabled service needs DNS pointing at this machine as soon as
    # the rebuild finishes (cert issuance, reachability).
    if req.enabled and feat_meta.get("needs_ddns"):
        await loop.run_in_executor(None, _run_njalla_ddns)

    # Clear the old rebuild log so the frontend doesn't pick up stale results
    try:
        open(REBUILD_LOG, "w").close()
    except OSError:
        pass

    # Queue the unit for auto-start once the rebuild succeeds
    unit_to_start = FEATURE_SERVICE_MAP.get(req.feature)
    if req.enabled and unit_to_start is not None:
        with _pending_service_starts_lock:
            _pending_service_starts.add(unit_to_start)

    # Start the rebuild service
    await asyncio.create_subprocess_exec(
        "systemctl", "reset-failed", REBUILD_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "start", "--no-block", REBUILD_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()

    return {"ok": True, "status": "rebuilding"}


@app.get("/api/rebuild/status")
async def api_rebuild_status(offset: int = 0):
    """Poll endpoint for rebuild progress."""
    loop = asyncio.get_event_loop()
    status = await loop.run_in_executor(None, _read_rebuild_status)
    new_log, new_offset = await loop.run_in_executor(None, _read_rebuild_log, offset)
    running = status == "RUNNING"
    result = "pending" if running else status.lower()

    # Auto-start any services that were just enabled by a feature toggle
    if result == "success":
        with _pending_service_starts_lock:
            units_to_start = set(_pending_service_starts)
            _pending_service_starts.clear()
        for unit in units_to_start:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "systemctl", "start", unit,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            except Exception:
                pass

    return {
        "running": running,
        "result": result,
        "log": new_log,
        "offset": new_offset,
    }


# ── Domain endpoints ──────────────────────────────────────────────

class DomainSetRequest(BaseModel):
    domain_name: str
    domain: str
    ddns_url: str = ""


_SAFE_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')


def _ensure_domains_dir() -> None:
    """Create DOMAINS_DIR if needed and ensure it is owned by caddy:root."""
    os.makedirs(DOMAINS_DIR, exist_ok=True)
    try:
        pw = pwd.getpwnam("caddy")
        os.chown(DOMAINS_DIR, pw.pw_uid, 0)
    except KeyError:
        pass


def _chown_to_caddy(path: str) -> None:
    """Set the owner of a file to caddy:root (best-effort)."""
    # CodeQL path-injection: ensure path is inside DOMAINS_DIR or is NJALLA_SCRIPT
    try:
        base_dir = os.path.abspath(DOMAINS_DIR)
        njalla_file = os.path.abspath(NJALLA_SCRIPT)
        abs_path = os.path.abspath(path)
        if abs_path != njalla_file and not abs_path.startswith(base_dir + os.sep):
            return
        pw = pwd.getpwnam("caddy")
        os.chown(abs_path, pw.pw_uid, 0)
    except (KeyError, ValueError, OSError):
        pass


def _validate_safe_name(name: str) -> bool:
    """Return True if name contains only safe path characters (no separators)."""
    return bool(name) and _SAFE_NAME_RE.match(name) is not None


_NJALLA_HEADER_SENTINEL = "# SOVRAN_NJALLA_HEADER"

# Import the migration regex from support_ops so there is a single canonical
# definition used by both the production server and the test suite.
_LEGACY_NJALLA_CURL_RE = _support_ops._LEGACY_NJALLA_CURL_RE


def _migrate_legacy_njalla_script() -> None:
    """Safely migrate legacy curl DDNS lines from ``njalla.sh`` to JSON store.

    Reads ``njalla.sh`` without executing or sourcing it.  Parses only the
    exact narrow curl-pattern lines (quoted or unquoted) written by old Hub
    versions.  Delegates to ``support_ops.migrate_legacy_njalla_script`` so
    tests can exercise the same code path.

    After migration the script is archived with permissions 0o000 so it can
    no longer be executed.  If persistence fails the script is left untouched.
    """
    _support_ops.migrate_legacy_njalla_script(
        NJALLA_SCRIPT,
        _validate_ddns_url,
        _save_ddns_urls,
        _load_ddns_urls,
        audit_fn=_log_support_audit,
    )


def _load_ddns_urls() -> list[str]:
    """Return the list of validated DDNS update URLs from the JSON store."""
    try:
        with open(NJALLA_DDNS_URLS_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [u for u in data if isinstance(u, str)]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_ddns_urls(urls: list[str]) -> None:
    """Persist the list of DDNS update URLs to the JSON store (atomic write)."""
    njalla_dir = os.path.dirname(NJALLA_DDNS_URLS_FILE)
    if njalla_dir:
        os.makedirs(njalla_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=njalla_dir, prefix=".ddns_urls_tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(urls, f)
        os.replace(tmp, NJALLA_DDNS_URLS_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _run_njalla_ddns() -> None:
    """Update Njal.la DDNS records immediately (best-effort).

    Resolves the current public IP once, then invokes ``curl`` directly as a
    subprocess for each stored DDNS update URL.  No shell interpolation is
    performed and no user-controlled value is interpreted as shell syntax.
    Each URL is revalidated through ``_validate_ddns_url()`` after ``${IP}``
    substitution; URLs that fail validation are silently skipped.

    Called when a domain/DDNS entry is saved and when a DDNS-backed feature
    is enabled, so DNS is refreshed right away instead of waiting for the
    15-minute timer tick (see modules/core/njalla.nix).
    """
    urls = _load_ddns_urls()
    if not urls:
        return
    # Resolve current public IP (best-effort; skip if unavailable)
    public_ip = ""
    try:
        ip_result = subprocess.run(
            ["dig", "@resolver4.opendns.com", "myip.opendns.com", "+short", "-4"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        raw_ip = ip_result.stdout.strip().splitlines()[0] if ip_result.stdout.strip() else ""
        # Validate strictly as a proper IPv4/IPv6 address before substitution
        ipaddress.ip_address(raw_ip)
        public_ip = raw_ip
    except Exception:
        public_ip = ""

    if not public_ip:
        return  # skip to avoid sending bare ${IP} to curl

    for raw_url in urls:
        try:
            # Replace the placeholder with the validated IP (safe string replacement)
            url = raw_url.replace("${IP}", public_ip)
            # Revalidate after substitution — enforces /update/ path, no $, etc.
            _validate_ddns_url(url)
            subprocess.run(
                ["curl", "--silent", "--max-time", "15", "--fail", "--no-location", url],
                timeout=20, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def _reload_caddy_for_domain_change() -> None:
    """Regenerate Caddy's runtime Caddyfile and reload it (best-effort).

    The Caddyfile is generated at runtime by caddy-generate-config.service
    from /var/lib/domains/* (see modules/core/caddy.nix). The generator only
    runs before caddy.service starts — nothing re-runs it while Caddy is up.
    So when a domain is saved while Caddy is already running, the new virtual
    host never gets seated: no proxying and no ACME certificate, and the
    Hub's reachability check wrongly reports a "ports 80/443" error until
    the next reboot or a rebuild that happens to start Caddy fresh. Restart
    the generator, then reload Caddy so the change takes effect immediately.

    Entirely skipped when Caddy is not active — e.g. the Node role before
    its first domain-based service is enabled. In that case the rebuild
    that enables the service starts caddy.service for the first time, which
    runs the generator first (requiredBy caddy.service) and seats the
    already-saved domain on its own.
    """
    try:
        if sysctl.is_active(CADDY_UNIT) != "active":
            return
        sysctl.run_action("restart", CADDY_GENERATE_UNIT)
        sysctl.run_action("reload", CADDY_UNIT)
    except Exception:
        pass


# Hostname characters: letters, digits, hyphens only within labels; dots separate labels.
# Each label must start and end with a letter or digit; no consecutive dots.
_HOSTNAME_RE = re.compile(
    r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$'
)

# Managed domain keys that produce Caddy virtual-host blocks (excluding sslemail)
_MANAGED_DOMAIN_KEYS: frozenset[str] = frozenset([
    "matrix", "haven", "element-calling", "vaultwarden",
    "btcpayserver", "nextcloud", "wordpress", "lightning",
])

# Any save involving lightning must be unique across all managed service domains.
_LIGHTNING_DOMAIN_KEY = "lightning"


def _normalize_hostname(raw: str) -> str:
    """Trim, lowercase, and remove exactly one trailing dot."""
    h = raw.strip().lower()
    if h.endswith("."):
        h = h[:-1]
    return h


def _validate_hostname(hostname: str) -> bool:
    """Return True if hostname is a valid safe FQDN-style value."""
    return bool(hostname) and _HOSTNAME_RE.match(hostname) is not None


def _read_managed_domain(key: str) -> str | None:
    """Read the stored hostname for a managed domain key, or None if absent/empty."""
    try:
        with open(os.path.join(DOMAINS_DIR, key), "r") as fh:
            val = fh.read().strip()
        return _normalize_hostname(val) if val else None
    except OSError:
        return None


def _check_domain_conflict(domain_name: str, new_hostname: str) -> str | None:
    """Return the conflicting managed key if new_hostname is already used by another key.

    The uniqueness rule is applied symmetrically: if either the target key or the
    conflicting candidate key is 'lightning', the check is enforced.
    """
    for key in _MANAGED_DOMAIN_KEYS:
        if key == domain_name:
            continue  # skip self; re-saving the same hostname is allowed
        existing = _read_managed_domain(key)
        if existing is None:
            continue
        if existing == new_hostname:
            # Enforce when lightning is involved (either side)
            if domain_name == _LIGHTNING_DOMAIN_KEY or key == _LIGHTNING_DOMAIN_KEY:
                return key
    return None


@app.post("/api/domains/set")
async def api_domains_set(req: DomainSetRequest):
    """Save a domain and optionally register a DDNS URL."""
    if not _validate_safe_name(req.domain_name):
        raise HTTPException(status_code=400, detail="Invalid domain_name")

    # Normalize and validate the submitted hostname before any mutation.
    normalized = _normalize_hostname(req.domain)
    if not _validate_hostname(normalized):
        raise HTTPException(status_code=400, detail="Invalid hostname value")

    # Reject duplicate managed-domain hostnames when lightning is involved.
    if req.domain_name in _MANAGED_DOMAIN_KEYS:
        conflicting_key = _check_domain_conflict(req.domain_name, normalized)
        if conflicting_key is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "domain_conflict",
                    "conflicting_domain_key": conflicting_key,
                    "message": (
                        "Lightning Wallet Connections requires its own unique hostname. "
                        "Choose a new subdomain such as lightning.yourdomain.com. "
                        f"This hostname is already assigned to: {conflicting_key}."
                    ),
                },
            )

    _ensure_domains_dir()
    # --- CodeQL path-injection fix ---
    safe_name = os.path.basename(req.domain_name)
    if safe_name != req.domain_name or not _validate_safe_name(safe_name):
        raise HTTPException(status_code=400, detail="Invalid domain_name")

    base_dir = os.path.abspath(DOMAINS_DIR)
    domain_path = os.path.abspath(os.path.join(base_dir, safe_name))
    if not domain_path.startswith(base_dir + os.sep):
        raise HTTPException(status_code=400, detail="Invalid domain_name")

    with open(domain_path, "w") as f:
        f.write(normalized)
    _chown_to_caddy(domain_path)

    if req.ddns_url:
        ddns_url = req.ddns_url.strip()
        # Strip leading "curl " if user pasted the full command from Njalla's UI
        if ddns_url.lower().startswith("curl "):
            ddns_url = ddns_url[5:].strip()
        # Strip surrounding quotes
        if len(ddns_url) >= 2 and ddns_url[0] in ('"', "'") and ddns_url[-1] == ddns_url[0]:
            ddns_url = ddns_url[1:-1]
        # Replace trailing &auto with the IP placeholder used by _run_njalla_ddns
        if ddns_url.endswith("&auto"):
            ddns_url = ddns_url[:-5] + "&a=${IP}"
        # Validate URL strictly — reject injection attempts before persisting.
        # The placeholder ${IP} is replaced temporarily so the validator sees a
        # real address; the original URL (with the placeholder) is kept for storage.
        try:
            _validate_ddns_url(ddns_url.replace("${IP}", "127.0.0.1"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid DDNS URL: {exc}")
        # Persist the URL in the JSON store (never in executable shell source)
        existing_urls = _load_ddns_urls()
        if ddns_url not in existing_urls:
            existing_urls.append(ddns_url)
        try:
            _save_ddns_urls(existing_urls)
        except OSError:
            pass
        # Run DDNS update immediately
        _run_njalla_ddns()

    # Regenerate the server-local /etc/hosts loopback entries so the newly
    # saved domain is immediately reachable on this computer without NAT
    # loopback support on the router.
    if req.domain_name in _SERVICE_DOMAIN_KEYS:
        _trigger_hosts_update()

    # If Caddy is already running, regenerate its runtime Caddyfile and reload
    # so the saved domain's virtual host is seated immediately. Without this,
    # a domain added to an already-running Caddy never gets its site block
    # (no proxying, no ACME cert) and the Hub's reachability check shows a
    # misleading "ports 80/443" error until reboot. No-op when Caddy is
    # inactive — e.g. Node role pre-enable, where the rebuild seats it anyway.
    if req.domain_name in _SERVICE_DOMAIN_KEYS:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _reload_caddy_for_domain_change)

    return {"ok": True}


class DomainSetEmailRequest(BaseModel):
    email: str


@app.post("/api/domains/set-email")
async def api_domains_set_email(req: DomainSetEmailRequest):
    """Save the SSL certificate email address."""
    _ensure_domains_dir()
    email_path = os.path.join(DOMAINS_DIR, "sslemail")
    with open(email_path, "w") as f:
        f.write(req.email.strip())
    _chown_to_caddy(email_path)

    # The ACME email lives in the Caddyfile's global block — regenerate and
    # reload so a running Caddy picks it up (no-op when Caddy is inactive).
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _reload_caddy_for_domain_change)

    return {"ok": True}


@app.get("/api/domains/status")
async def api_domains_status():
    """Return the value of each known domain file (or null if missing)."""
    known = [
        "matrix", "haven", "element-calling", "sslemail",
        "vaultwarden", "btcpayserver", "nextcloud", "wordpress", "lightning",
    ]
    domains: dict[str, str | None] = {}
    for name in known:
        path = os.path.join(DOMAINS_DIR, name)
        try:
            with open(path, "r") as f:
                domains[name] = f.read().strip()
        except FileNotFoundError:
            domains[name] = None
    return {"domains": domains}


class DomainCheckRequest(BaseModel):
    domains: list[str]


@app.post("/api/domains/check")
async def api_domains_check(req: DomainCheckRequest):
    """Check DNS resolution for each domain and verify it points to this server."""
    loop = asyncio.get_event_loop()
    external_ip = _cached_external_ip

    def check_domain(domain: str) -> dict:
        addrs = _resolve_all_addresses(domain)
        if not addrs:
            return {
                "domain": domain, "status": "unresolvable",
                "resolved_ip": None, "expected_ip": external_ip,
            }
        resolved_ip = addrs[0]
        # Server-local /etc/hosts loopback override — report as such rather
        # than as a DNS mismatch.  Public DNS cannot be verified from this
        # computer when the override is active.
        if all(_is_loopback_address(a) for a in addrs):
            return {
                "domain": domain, "status": "local_override",
                "resolved_ip": resolved_ip, "expected_ip": external_ip,
            }
        if external_ip == "unavailable":
            return {
                "domain": domain, "status": "error",
                "resolved_ip": resolved_ip, "expected_ip": external_ip,
            }
        if any(a == external_ip for a in addrs):
            return {
                "domain": domain, "status": "connected",
                "resolved_ip": resolved_ip, "expected_ip": external_ip,
            }
        return {
            "domain": domain, "status": "dns_mismatch",
            "resolved_ip": resolved_ip, "expected_ip": external_ip,
        }

    check_results = await asyncio.gather(*[
        loop.run_in_executor(None, check_domain, d) for d in req.domains
    ])
    return {"domains": list(check_results)}


# ── Lightning Wallet Connections (NWC) endpoints ────────────────────────────

NWC_DOMAIN_FILE = "/var/lib/domains/lightning"
NWC_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
NWC_MIN_SENDABLE_MSAT = _nwc_mgr.NWC_MIN_SENDABLE_MSAT
NWC_MAX_SENDABLE_MSAT = _nwc_mgr.NWC_MAX_SENDABLE_MSAT


def _nwc_error(status_code: int, error: str, message: str, **extra) -> JSONResponse:
    payload = {"error": error, "message": message}
    payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload)


def _nwc_domain() -> str | None:
    try:
        with open(NWC_DOMAIN_FILE, "r") as f:
            domain = f.read(256).strip().lower()
    except OSError:
        return None
    if not _validate_domain_value(domain):
        return None
    return domain


def _nwc_validate_alias(alias: str) -> bool:
    return bool(NWC_ALIAS_RE.match(alias))


def _nwc_test_address(alias: str) -> dict:
    domain = _nwc_domain()
    if not domain:
        return {"ok": False, "error": "domain_not_configured", "message": "Lightning domain is not configured."}
    url = f"https://{domain}/.well-known/lnurlp/{alias}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if int(resp.status) >= 400:
                return {"ok": False, "error": "public_endpoint_unreachable", "message": f"Public LNURL discovery endpoint returned HTTP {resp.status}."}
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return {"ok": False, "error": "public_endpoint_unreachable", "message": "Public LNURL endpoint verification failed."}
    if payload.get("tag") != "payRequest":
        return {"ok": False, "error": "public_endpoint_unreachable", "message": "Discovery endpoint returned an invalid LNURL response."}
    return {"ok": True}


class NwcWalletCreateRequest(BaseModel):
    name: str
    alias: str
    access_preset: str
    spending_limit_sats: int | None = None


@app.get("/api/nwc/wallets")
async def api_nwc_wallets():
    loop = asyncio.get_event_loop()
    domain = await loop.run_in_executor(None, _nwc_domain)
    try:
        wallets = await loop.run_in_executor(
            None, _nwc_mgr.get_manager().list_wallets, domain
        )
    except _nwc_mgr.AlbyHubError as exc:
        return _nwc_error(503, exc.code, exc.args[0])
    return {"wallets": wallets, "domain": domain}


@app.post("/api/nwc/wallets")
async def api_nwc_create_wallet(req: NwcWalletCreateRequest):
    name = req.name.strip()
    alias = req.alias.strip().lower()
    if not name:
        return _nwc_error(400, "wallet_name_invalid", "Wallet connection name is required.")
    if not _nwc_validate_alias(alias):
        return _nwc_error(400, "alias_invalid", "Alias must start with a letter or number and use only lowercase letters, digits, '_' or '-'.")
    if req.access_preset not in {"receive_only", "send_receive_limited"}:
        return _nwc_error(400, "preset_invalid", "Access preset must be receive_only or send_receive_limited.")

    spending_limit_sats = req.spending_limit_sats if req.access_preset == "send_receive_limited" else None
    if req.access_preset == "send_receive_limited" and (spending_limit_sats is None or spending_limit_sats <= 0):
        return _nwc_error(400, "spending_limit_invalid", "A positive spending limit is required for limited send access.")

    domain = _nwc_domain()
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: _nwc_mgr.get_manager().create_wallet(
                name, alias, req.access_preset, spending_limit_sats, domain
            ),
        )
    except _nwc_mgr.AlbyHubError as exc:
        code_map = {
            "alias_exists": 409,
            "wallet_name_exists": 409,
        }
        status = code_map.get(exc.code, 502)
        return _nwc_error(status, exc.code, exc.args[0])

    pairing_uri: str = result.get("pairing_uri", "")
    pairing_qrcode: str | None = None
    if pairing_uri:
        pairing_qrcode = _generate_qr_base64(pairing_uri)

    verify = await loop.run_in_executor(None, _nwc_test_address, alias)

    response: dict = {
        "wallet": result["wallet"],
        "pairing_uri": pairing_uri,
        "lightning_address": f"{alias}@{domain}" if domain else None,
        "result": {
            **result.get("result", {}),
            "public_endpoint_verification": verify,
        },
    }
    if pairing_qrcode:
        response["pairing_qrcode"] = pairing_qrcode
    return JSONResponse(status_code=201, content=response)


@app.delete("/api/nwc/wallets/{wallet_identifier}")
async def api_nwc_delete_wallet(wallet_identifier: str):
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            _nwc_mgr.get_manager().delete_wallet,
            wallet_identifier,
        )
    except _nwc_mgr.AlbyHubError as exc:
        code_map = {
            "wallet_not_found": 404,
            "pending_transactions": 409,
            "drain_incomplete": 409,
        }
        status = code_map.get(exc.code, 502)
        return _nwc_error(status, exc.code, exc.args[0])
    return result


@app.post("/api/nwc/wallets/{wallet_identifier}/drain")
async def api_nwc_drain_wallet(wallet_identifier: str):
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            _nwc_mgr.get_manager().drain_wallet,
            wallet_identifier,
        )
    except _nwc_mgr.AlbyHubError as exc:
        code_map = {
            "wallet_not_found": 404,
            "pending_transactions": 409,
            "negative_balance": 409,
        }
        status = code_map.get(exc.code, 502)
        return _nwc_error(status, exc.code, exc.args[0])
    return result


@app.post("/api/nwc/wallets/{wallet_identifier}/rotate-secret")
async def api_nwc_rotate_wallet_secret(wallet_identifier: str):
    """Rotate the NWC pairing secret for a wallet connection.

    Revokes the old Nostr key and generates a new pairing URI.
    Returns the new pairing URI (shown ONCE).
    """
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            _nwc_mgr.get_manager().rotate_wallet_secret,
            wallet_identifier,
        )
    except _nwc_mgr.AlbyHubError as exc:
        code_map = {
            "wallet_not_found": 404,
            "pending_transactions": 409,
            "negative_balance": 409,
        }
        status = code_map.get(exc.code, 502)
        return _nwc_error(status, exc.code, exc.args[0])

    pairing_uri: str = result.get("pairing_uri", "")
    pairing_qrcode: str | None = None
    if pairing_uri:
        pairing_qrcode = _generate_qr_base64(pairing_uri)

    response: dict = {
        "wallet_id": result.get("wallet_id", ""),
        "pairing_uri": pairing_uri,
        "message": result.get("message", "New NWC connection secret generated. Save it now — it will not be shown again."),
    }
    if pairing_qrcode:
        response["pairing_qrcode"] = pairing_qrcode
    return JSONResponse(status_code=200, content=response)


@app.post("/api/nwc/addresses/{alias}/test")
async def api_nwc_test(alias: str):
    normalized_alias = alias.strip().lower()
    if not _nwc_validate_alias(normalized_alias):
        return _nwc_error(400, "alias_invalid", "Invalid alias.")
    loop = asyncio.get_event_loop()
    try:
        app = await loop.run_in_executor(
            None,
            _nwc_mgr.get_manager().find_app_by_alias,
            normalized_alias,
        )
    except _nwc_mgr.AlbyHubError as exc:
        return _nwc_error(503, exc.code, exc.args[0])
    if app is None:
        return _nwc_error(404, "wallet_not_found", "No wallet connection exists for this alias.")
    result = await loop.run_in_executor(None, _nwc_test_address, normalized_alias)
    if not result.get("ok"):
        return _nwc_error(502, result.get("error", "public_endpoint_unreachable"), result.get("message", "Public endpoint verification failed."))
    return {"ok": True}


# ── LNURL QR sharing (download / print) ───────────────────────────


def _nwc_lnurl_context(wallet_identifier: str) -> tuple[dict | None, str | None, JSONResponse | None]:
    """Resolve a wallet connection + domain for the LNURL QR endpoints.

    Returns ``(wallet, domain, error_response)``. On success the error is
    ``None``; on failure the wallet is ``None`` and the error is a ready-made
    ``JSONResponse``. Blocking — call via ``loop.run_in_executor``.
    """
    domain = _nwc_domain()
    if not domain:
        return None, None, _nwc_error(503, "domain_not_configured", "Lightning Address domain is not configured.")
    needle = wallet_identifier.strip().lower()
    try:
        wallets = _nwc_mgr.get_manager().list_wallets(domain)
    except _nwc_mgr.AlbyHubError as exc:
        return None, domain, _nwc_error(503, exc.code, exc.args[0])
    for wallet in wallets:
        wid = str(wallet.get("id", "")).lower()
        wpk = str(wallet.get("pubkey", "")).lower()
        if needle and needle in (wid, wpk):
            if not wallet.get("alias"):
                return None, domain, _nwc_error(404, "wallet_not_found", "Wallet connection has no Lightning Address alias.")
            return wallet, domain, None
    return None, domain, _nwc_error(404, "wallet_not_found", "Wallet connection not found.")


def _nwc_lnurl_error_png() -> JSONResponse:
    return _nwc_error(500, "qr_unavailable", "QR code generation failed on this system.")


@app.get("/api/nwc/wallets/{wallet_identifier}/lnurl")
async def api_nwc_wallet_lnurl(wallet_identifier: str):
    """Return the bech32 LNURL + Lightning Address for a wallet connection."""
    loop = asyncio.get_event_loop()
    wallet, domain, err = await loop.run_in_executor(None, _nwc_lnurl_context, wallet_identifier)
    if err:
        return err
    return {
        "alias": wallet["alias"],
        "lightning_address": wallet.get("lightning_address"),
        "lnurl": _nwc_lnurl_bech32(wallet["alias"], domain),
    }


@app.get("/api/nwc/wallets/{wallet_identifier}/lnurl-qr.png")
async def api_nwc_wallet_lnurl_qr_png(wallet_identifier: str, download: bool = False, scale: int = 10):
    """Serve the LNURL QR code as a PNG (uppercase LNURL for scannability).

    ``?download=1`` switches Content-Disposition to attachment so the browser
    saves it with a meaningful filename. ``scale`` (qrencode pixel size) may be
    raised for high-resolution display, e.g. the print page.
    """
    loop = asyncio.get_event_loop()
    wallet, domain, err = await loop.run_in_executor(None, _nwc_lnurl_context, wallet_identifier)
    if err:
        return err
    scale = max(1, min(scale, 40))
    lnurl_qr = _nwc_lnurl_bech32(wallet["alias"], domain).upper()
    png = await loop.run_in_executor(None, lambda: _generate_qr_png_bytes(lnurl_qr, scale=scale, margin=4))
    if png is None:
        return _nwc_lnurl_error_png()
    filename = f"lightning-{wallet['alias']}-{domain}.png"
    disposition = "attachment" if download else "inline"
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/nwc/wallets/{wallet_identifier}/lnurl-qr.svg")
async def api_nwc_wallet_lnurl_qr_svg(wallet_identifier: str, download: bool = False):
    """Serve the LNURL QR code as an SVG — resolution-independent, so it stays
    perfectly sharp when printed at any size or embedded on a website."""
    loop = asyncio.get_event_loop()
    wallet, domain, err = await loop.run_in_executor(None, _nwc_lnurl_context, wallet_identifier)
    if err:
        return err
    lnurl_qr = _nwc_lnurl_bech32(wallet["alias"], domain).upper()
    svg = await loop.run_in_executor(None, lambda: _generate_qr_svg(lnurl_qr, margin=4))
    if svg is None:
        return _nwc_error(500, "qr_unavailable", "QR code generation failed on this system.")
    filename = f"lightning-{wallet['alias']}-{domain}.svg"
    disposition = "attachment" if download else "inline"
    return Response(
        content=svg.encode("utf-8"),
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/nwc/wallets/{wallet_identifier}/lnurl-qr/print")
async def api_nwc_wallet_lnurl_qr_print(wallet_identifier: str):
    """Print-ready LNURL payment card — opens the browser print dialog."""
    loop = asyncio.get_event_loop()
    wallet, domain, err = await loop.run_in_executor(None, _nwc_lnurl_context, wallet_identifier)
    if err:
        return err
    address = wallet.get("lightning_address") or f"{wallet['alias']}@{domain}"
    name = _html_escape(str(wallet.get("name") or "Wallet"), quote=True)
    addr_html = _html_escape(address, quote=True)
    # ── XSS FIX: do not reflect raw wallet_identifier (attacker-controlled) ──
    # Use canonical ID from the resolved wallet (DB = trusted), then
    # URL-encode for URL context + HTML-escape for HTML attribute context.
    # urllib.parse.quote alone is NOT recognized by CodeQL as an HTML sanitizer.
    canonical_id = str(wallet.get("id") or wallet.get("pubkey") or wallet_identifier)
    safe_id = urllib.parse.quote(canonical_id, safe="")
    img_src_raw = f"/api/nwc/wallets/{safe_id}/lnurl-qr.png?scale=24"
    img_src = _html_escape(img_src_raw, quote=True)
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{addr_html}</title>
<style>
  body {{ font-family: system-ui, sans-serif; display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:95vh; margin:0; color:#111; }}
  .card {{ text-align:center; padding:28px 36px; border:2px solid #111; border-radius:18px; max-width:90vw; }}
  h1 {{ font-size:20px; margin:0 0 18px; font-weight:700; }}
  img {{ width:64mm; max-width:70vw; image-rendering:pixelated; }}
  .addr {{ font-family:ui-monospace, monospace; font-size:15px; margin-top:18px; word-break:break-all; }}
  .hint {{ font-size:12px; color:#555; margin-top:10px; }}
  .actions {{ margin-top:22px; display:flex; gap:12px; }}
  .actions button {{ font:inherit; padding:10px 22px; border-radius:10px; border:1px solid #111; background:#111; color:#fff; cursor:pointer; }}
  .actions button.secondary {{ background:#fff; color:#111; }}
  @media print {{ .actions {{ display:none; }} body {{ min-height:auto; }} }}
</style>
</head>
<body>
  <div class="card">
    <h1>Pay {name} with Bitcoin ⚡</h1>
    <img src="{img_src}" alt="LNURL QR code for {addr_html}">
    <div class="addr">{addr_html}</div>
    <div class="hint">Scan with any Lightning wallet — this QR never expires.</div>
  </div>
  <div class="actions">
    <button onclick="window.print()">🖨 Print</button>
    <button class="secondary" onclick="window.close()">Close</button>
  </div>
  <script>
    window.addEventListener("load", function () {{
      var img = document.querySelector("img");
      function go() {{ setTimeout(function () {{ window.print(); }}, 250); }}
      if (img && !img.complete) {{ img.addEventListener("load", go); img.addEventListener("error", go); }}
      else {{ go(); }}
    }});
  </script>
</body>
</html>"""
    return HTMLResponse(
        content=html_doc,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
            "X-Content-Type-Options": "nosniff",
        },
    )



# ── Security endpoints ────────────────────────────────────────────


@app.get("/api/security/banner-status")
async def api_security_banner_status():
    """Return whether the first-login security banner should be shown.

    The banner is shown only when:
    1. The machine has completed onboarding (ONBOARDING_FLAG exists).
    2. The banner has not been dismissed yet (SECURITY_BANNER_DISMISSED_FLAG absent).

    Legacy machines (no ONBOARDING_FLAG) will never see the banner.
    """
    onboarded = os.path.isfile(ONBOARDING_FLAG)
    dismissed = os.path.isfile(SECURITY_BANNER_DISMISSED_FLAG)
    return {"show": onboarded and not dismissed}


@app.post("/api/security/banner-dismiss")
async def api_security_banner_dismiss():
    """Mark the first-login security banner as dismissed."""
    try:
        os.makedirs(os.path.dirname(SECURITY_BANNER_DISMISSED_FLAG), exist_ok=True)
        open(SECURITY_BANNER_DISMISSED_FLAG, "w").close()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write dismiss flag: {exc}")
    return {"ok": True}


@app.post("/api/security/reset")
async def api_security_reset():
    """Perform a full security reset.

    Wipes secrets, LND wallet, SSH keys, drops databases, removes app configs,
    clears Vaultwarden data, removes the onboarding-complete flag so onboarding
    re-runs.  Generates a new diceware password for the 'free' and 'root' users,
    deletes the GNOME Keyring so a fresh one is created on next GDM login, and
    returns the new password to the caller.  Does NOT reboot — the caller must
    trigger a separate POST /api/reboot after showing the password to the user.
    """
    wipe_paths = [
        "/var/lib/secrets",
        "/var/lib/sovran",
        "/root/.ssh",
        "/home/free/.ssh",
        "/var/lib/lnd",
        "/var/lib/vaultwarden",
        "/etc/nix-bitcoin-secrets",
        "/home/free/.local/share/Bisq",
        "/home/free/.bisq",
    ]

    errors: list[str] = []

    # Wipe filesystem paths
    for path in wipe_paths:
        if os.path.exists(path):
            try:
                import shutil as _shutil
                _shutil.rmtree(path, ignore_errors=True)
            except Exception as exc:
                logger.warning("Failed to wipe path %s: %s", path, exc)
                errors.append("wipe_path_failed")

    # Drop PostgreSQL databases (matrix-synapse, nextcloud, etc.)
    try:
        result = subprocess.run(
            ["sudo", "-u", "postgres", "psql", "-c",
             "SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres')"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                dbname = line.strip()
                if dbname and not dbname.startswith("-") and dbname != "datname":
                    subprocess.run(
                        ["sudo", "-u", "postgres", "dropdb", "--if-exists", dbname],
                        capture_output=True, text=True, timeout=30,
                    )
    except Exception as exc:
        logger.warning("Postgres wipe failed: %s", exc)
        errors.append("postgres_wipe_failed")

    # Drop MariaDB databases
    try:
        result = subprocess.run(
            ["mysql", "-u", "root", "-e",
             "SHOW DATABASES"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            skip = {"Database", "information_schema", "performance_schema", "mysql", "sys"}
            for line in result.stdout.splitlines():
                dbname = line.strip()
                if dbname and dbname not in skip:
                    subprocess.run(
                        ["mysql", "-u", "root", "-e", f"DROP DATABASE IF EXISTS `{dbname}`"],
                        capture_output=True, text=True, timeout=30,
                    )
    except Exception as exc:
        logger.warning("MariaDB wipe failed: %s", exc)
        errors.append("mariadb_wipe_failed")

    # Generate new diceware passwords
    new_free_password = _generate_diceware_password()
    new_root_password = _generate_diceware_password()

    # Locate chpasswd
    chpasswd_bin = (
        shutil.which("chpasswd")
        or ("/run/current-system/sw/bin/chpasswd"
            if os.path.isfile("/run/current-system/sw/bin/chpasswd") else None)
    )

    if chpasswd_bin:
        # Set free user password
        try:
            result = subprocess.run(
                [chpasswd_bin],
                input=f"free:{new_free_password}",
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                logger.warning("chpasswd free failed: %s", (result.stderr or result.stdout).strip())
                errors.append("chpasswd_free_failed")
        except Exception as exc:
            logger.warning("chpasswd free error: %s", exc)
            errors.append("chpasswd_free_failed")

        # Set root password
        try:
            result = subprocess.run(
                [chpasswd_bin],
                input=f"root:{new_root_password}",
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                logger.warning("chpasswd root failed: %s", (result.stderr or result.stdout).strip())
                errors.append("chpasswd_root_failed")
        except Exception as exc:
            logger.warning("chpasswd root error: %s", exc)
            errors.append("chpasswd_root_failed")
    else:
        logger.warning("chpasswd not found; passwords not reset")
        errors.append("chpasswd_not_found")

    # Write new passwords to secrets files
    try:
        os.makedirs("/var/lib/secrets", exist_ok=True)
        try:
            import subprocess
            subprocess.run(
                ["chpasswd"],
                input=f"free:{new_free_password}\n".encode(),
                check=True,
                capture_output=True,
            )
        except Exception:
            pass
        try:
            with open(FREE_PASSWORD_FILE_WEB, "w") as f:
                f.write(_hash_password(new_free_password))
            os.chmod(FREE_PASSWORD_FILE_WEB, 0o600)
        except Exception:
            pass
    except Exception as exc:
        logger.warning("write free-password error: %s", exc)
        errors.append("write_free_password_failed")

    try:
        os.makedirs("/var/lib/secrets", exist_ok=True)
        with open("/var/lib/secrets/root-password", "w") as f:
            f.write(_hash_password(new_root_password))
        os.chmod("/var/lib/secrets/root-password", 0o600)
    except Exception as exc:
        logger.warning("write root-password error: %s", exc)
        errors.append("write_root_password_failed")

    # Clear only the locked keyring databases, leaving the directory and 'default' pointer intact.
    keyring_dir = "/home/free/.local/share/keyrings"
    keyring_files = glob.glob(os.path.join(keyring_dir, "*.keyring"))
    for kf in keyring_files:
        try:
            os.remove(kf)
        except OSError as exc:
            logger.warning("keyring wipe error for %s: %s", kf, exc)
            errors.append("keyring_wipe_failed")

    # The user performed a full security reset — the banner's purpose is served.
    try:
        os.makedirs(os.path.dirname(SECURITY_BANNER_DISMISSED_FLAG), exist_ok=True)
        with open(SECURITY_BANNER_DISMISSED_FLAG, "w"):
            pass
    except OSError:
        pass  # Non-fatal

    return {"ok": True, "new_password": new_free_password, "new_root_password": new_root_password, "errors": errors}


@app.post("/api/security/verify-integrity")
async def api_security_verify_integrity():
    """Verify system integrity using NixOS reproducibility features.

    Reads /etc/nixos/flake.lock for the current commit hash, runs
    `nix store verify --all` to check binary integrity, and compares the
    current running system to what the flake says it should be.
    """
    import json as _json

    # ── 1. Read flake commit ──────────────────────────────────────
    flake_commit = ""
    repo_url = ""
    try:
        with open("/etc/nixos/flake.lock", "r") as f:
            lock_data = _json.load(f)
        # The root node's inputs → find the first locked input with a rev
        nodes = lock_data.get("nodes", {})
        root_inputs = nodes.get("root", {}).get("inputs", {})
        for input_name in root_inputs.values():
            node_name = input_name if isinstance(input_name, str) else (input_name[0] if input_name else "")
            node = nodes.get(node_name, {})
            locked = node.get("locked", {})
            if locked.get("rev"):
                flake_commit = locked["rev"]
                # Build repo URL from locked info if available
                owner = locked.get("owner", "")
                repo = locked.get("repo", "")
                if owner and repo:
                    repo_url = f"https://github.com/{owner}/{repo}/commit/{flake_commit}"
                break
    except Exception:
        pass

    # ── 2. Verify Nix store ───────────────────────────────────────
    store_verified = False
    store_errors: list[str] = []
    try:
        result = subprocess.run(
            ["/run/current-system/sw/bin/nix", "store", "verify", "--all", "--no-trust"],
            capture_output=True, text=True, timeout=300,
        )
        combined = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            store_verified = True
        else:
            store_errors = [line for line in combined.splitlines() if line.strip()]
    except subprocess.TimeoutExpired:
        store_errors = ["Verification timed out after 5 minutes."]
    except Exception as exc:
        logger.warning("Nix store verification failed: %s", exc)
        store_errors = ["Verification failed unexpectedly."]

    # ── 3. Compare running system to flake build ──────────────────
    system_matches = False
    current_system_path = ""
    expected_system_path = ""
    try:
        current_system_path = os.path.realpath("/run/current-system")
        # Use a temp directory so the ./result symlink doesn't pollute anything
        tmpdir = tempfile.mkdtemp(prefix="sovran-verify-")
        try:
            result_link = os.path.join(tmpdir, "result")
            result = subprocess.run(
                ["/run/current-system/sw/bin/nix", "build",
                 "/etc/nixos#nixosConfigurations.nixos.config.system.build.toplevel",
                 "--out-link", result_link],
                capture_output=True, text=True, timeout=600,
                cwd=tmpdir,
            )
            if result.returncode == 0:
                if os.path.islink(result_link):
                    expected_system_path = os.path.realpath(result_link)
                    system_matches = (current_system_path == expected_system_path)
                else:
                    expected_system_path = "Build succeeded but no result symlink found"
            else:
                # Surface the error so the UI can show what went wrong
                logger.warning("System verification build failed: %s", (result.stderr or result.stdout).strip()[:500])
                expected_system_path = "Build failed"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    except subprocess.TimeoutExpired:
        expected_system_path = "Build timed out"
    except Exception as exc:
        logger.warning("System verification failed: %s", exc)
        expected_system_path = "Verification failed"

    return {
        "flake_commit": flake_commit,
        "repo_url": repo_url,
        "store_verified": store_verified,
        "store_errors": store_errors,
        "system_matches": system_matches,
        "current_system_path": current_system_path,
        "expected_system_path": expected_system_path,
    }


# ── System password change ────────────────────────────────────────


class ChangePasswordRequest(BaseModel):
    new_password: str
    confirm_password: str


@app.post("/api/change-password")
async def api_change_password(req: ChangePasswordRequest):
    """Change the system 'free' user password.

    Updates /etc/shadow via chpasswd and writes the new password to
    /var/lib/secrets/free-password so the Hub credentials view stays in sync.
    """
    if not req.new_password:
        raise HTTPException(status_code=400, detail="New password must not be empty.")
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

    # Locate chpasswd binary (NixOS puts it in the Nix store, not /usr/bin)
    chpasswd_bin = (
        shutil.which("chpasswd")
        or ("/run/current-system/sw/bin/chpasswd"
            if os.path.isfile("/run/current-system/sw/bin/chpasswd") else None)
    )
    if chpasswd_bin is None:
        raise HTTPException(
            status_code=500,
            detail="chpasswd binary not found. Cannot update system password.",
        )

    # Update /etc/shadow via chpasswd
    try:
        result = subprocess.run(
            [chpasswd_bin],
            input=f"free:{req.new_password}",
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip() or "chpasswd failed."
            raise HTTPException(status_code=500, detail=detail)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update system password: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update system password.")

    # Write new password to secrets file so Hub credentials stay in sync
    try:
        os.makedirs(os.path.dirname(FREE_PASSWORD_FILE), exist_ok=True)
        # Write secure web-only hash; sync system shadow via chpasswd (memory)
        try:
            import subprocess
            subprocess.run(
                ["chpasswd"],
                input=f"free:{req.new_password}\n".encode(),
                check=True,
                capture_output=True,
            )
        except Exception as exc:
            # Log but do not block; web hash is the critical fix
            pass
        with open(FREE_PASSWORD_FILE_WEB, "w") as f:
            f.write(_hash_password(req.new_password))
        os.chmod(FREE_PASSWORD_FILE_WEB, 0o600)
    except Exception as exc:
        logger.error("Failed to write secrets file: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to write secrets file.")

    # Clear only the locked keyring databases, leaving the directory and 'default' pointer intact.
    keyring_dir = "/home/free/.local/share/keyrings"
    for kf in glob.glob(os.path.join(keyring_dir, "*.keyring")):
        try:
            os.remove(kf)
        except OSError:
            pass  # Non-fatal: keyring will be re-created on next login regardless

    return {"ok": True}


# ── Timezone / Locale endpoints ───────────────────────────────────

SUPPORTED_LOCALES = [
    "en_US.UTF-8",
    "en_GB.UTF-8",
    "es_ES.UTF-8",
    "fr_FR.UTF-8",
    "de_DE.UTF-8",
    "pt_BR.UTF-8",
    "ja_JP.UTF-8",
    "zh_CN.UTF-8",
    "ko_KR.UTF-8",
    "ru_RU.UTF-8",
    "ar_SA.UTF-8",
    "hi_IN.UTF-8",
]


def _get_current_timezone() -> str | None:
    """Return the currently configured timezone string, or None if unset."""
    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        tz = result.stdout.strip()
        if tz and tz != "n/a":
            return tz
    except Exception:
        pass
    # Fallback: check the Hub Managed section of custom.nix for a pending change
    _, _, timezone, _ = _read_hub_overrides()
    return timezone


def _get_current_locale() -> str | None:
    """Return the currently configured LANG locale, or None if unset."""
    try:
        result = subprocess.run(
            ["localectl", "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if "LANG=" in line:
                return line.split("LANG=", 1)[1].strip()
    except Exception:
        pass
    # Fallback: check the Hub Managed section of custom.nix for a pending change
    _, _, _, locale = _read_hub_overrides()
    return locale


@app.get("/api/system/timezones")
async def api_system_timezones():
    """Return list of available timezones and the currently configured one."""
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["timedatectl", "list-timezones"],
                capture_output=True,
                text=True,
                timeout=15,
            ),
        )
        timezones = [tz for tz in result.stdout.splitlines() if tz.strip()]
    except Exception:
        # Fallback: read from /usr/share/zoneinfo
        timezones = []
        zoneinfo_dir = "/usr/share/zoneinfo"
        if os.path.isdir(zoneinfo_dir):
            for root, dirs, files in os.walk(zoneinfo_dir):
                # Skip posix/right sub-directories and non-timezone files
                dirs[:] = [d for d in dirs if d not in ("posix", "right")]
                for fname in files:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, zoneinfo_dir)
                    if "/" in rel:
                        timezones.append(rel)
            timezones.sort()

    current_tz = await loop.run_in_executor(None, _get_current_timezone)
    return {"timezones": timezones, "current": current_tz}


class TimezoneRequest(BaseModel):
    timezone: str


@app.post("/api/system/timezone")
async def api_system_set_timezone(req: TimezoneRequest):
    """Set the system timezone declaratively via custom.nix and trigger a rebuild."""
    tz = req.timezone.strip()
    if not tz:
        raise HTTPException(status_code=400, detail="Timezone must not be empty.")
    # Basic validation: only allow characters valid in timezone names
    if not re.match(r'^[A-Za-z0-9/_\-+]+$', tz):
        raise HTTPException(status_code=400, detail="Invalid timezone format.")

    loop = asyncio.get_event_loop()
    features, nostr_npub, _, cur_locale = await loop.run_in_executor(None, _read_hub_overrides)
    await loop.run_in_executor(None, _write_hub_overrides, features, nostr_npub, tz, cur_locale)

    try:
        open(REBUILD_LOG, "w").close()
    except OSError:
        pass
    await asyncio.create_subprocess_exec(
        "systemctl", "reset-failed", REBUILD_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "start", "--no-block", REBUILD_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()

    return {"ok": True, "timezone": tz, "status": "rebuilding"}


@app.get("/api/system/locales")
async def api_system_locales():
    """Return the list of supported locales and the currently configured one."""
    loop = asyncio.get_event_loop()
    current_locale = await loop.run_in_executor(None, _get_current_locale)
    return {"locales": SUPPORTED_LOCALES, "current": current_locale}


class LocaleRequest(BaseModel):
    locale: str


@app.post("/api/system/locale")
async def api_system_set_locale(req: LocaleRequest):
    """Set the system locale declaratively via custom.nix and trigger a rebuild."""
    locale = req.locale.strip()
    if not locale:
        raise HTTPException(status_code=400, detail="Locale must not be empty.")
    if locale not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=400, detail=f"Unsupported locale: {locale}")

    loop = asyncio.get_event_loop()
    features, nostr_npub, cur_tz, _ = await loop.run_in_executor(None, _read_hub_overrides)
    await loop.run_in_executor(None, _write_hub_overrides, features, nostr_npub, cur_tz, locale)

    try:
        open(REBUILD_LOG, "w").close()
    except OSError:
        pass
    await asyncio.create_subprocess_exec(
        "systemctl", "reset-failed", REBUILD_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    proc = await asyncio.create_subprocess_exec(
        "systemctl", "start", "--no-block", REBUILD_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()

    return {"ok": True, "locale": locale, "status": "rebuilding"}


# ── Matrix user management ────────────────────────────────────────

MATRIX_HUB_ADMIN_FILE = "/var/lib/secrets/matrix-hub-admin"
MATRIX_DOMAINS_FILE = "/var/lib/domains/matrix"

_SAFE_USERNAME_RE = re.compile(r'^[a-z0-9._\-]+$')


def _validate_matrix_username(username: str) -> bool:
    """Return True if username is a valid Matrix localpart."""
    return bool(username) and len(username) <= 255 and bool(_SAFE_USERNAME_RE.match(username))


def _parse_matrix_hub_admin_creds() -> tuple[str, str]:
    """Read the private Matrix service-admin credentials used by the Hub.

    These credentials are provisioned independently from the visible bootstrap
    admin, so user management also works on systems where that account existed
    before Sovran and its password is unavailable.
    """
    with open(MATRIX_HUB_ADMIN_FILE, "r") as f:
        values = dict(
            line.strip().split("=", 1)
            for line in f
            if "=" in line
        )

    username = values.get("username", "")
    password = values.get("password", "")
    if not _validate_matrix_username(username) or not password:
        raise ValueError("Matrix Hub service credentials are invalid.")
    return username, password


class MatrixAdminAPIError(Exception):
    """An HTTP error returned by Synapse's local Admin API."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _matrix_error_detail(exc: urllib.error.HTTPError) -> str:
    """Extract Synapse's non-sensitive error description from an HTTP error."""
    body = exc.read().decode(errors="replace")
    try:
        return str(json.loads(body).get("error", body))
    except (ValueError, TypeError):
        return body or f"Synapse returned HTTP {exc.code}"


def _matrix_get_admin_token(admin_user: str, admin_pass: str) -> str:
    """Log in to the local Synapse instance and return an access token."""
    url = "http://[::1]:8008/_matrix/client/v3/login"
    payload = json.dumps({
        "type": "m.login.password",
        "identifier": {"type": "m.id.user", "user": admin_user},
        "password": admin_pass,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise MatrixAdminAPIError(exc.code, _matrix_error_detail(exc)) from exc
    token: str = body.get("access_token", "")
    if not token:
        raise ValueError("No access_token in Synapse login response")
    return token


def _matrix_update_user(
    domain: str, admin_user: str, admin_pass: str, username: str, payload: dict
) -> None:
    """Update a Matrix user through Synapse without blocking the web event loop."""
    token = _matrix_get_admin_token(admin_user, admin_pass)
    target_user_id = f"@{username}:{domain}"
    url = (
        "http://[::1]:8008/_synapse/admin/v2/users/"
        f"{urllib.parse.quote(target_user_id, safe='@:')}"
    )
    api_req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(api_req, timeout=15) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        raise MatrixAdminAPIError(exc.code, _matrix_error_detail(exc)) from exc


async def _matrix_update_user_async(domain: str, username: str, payload: dict) -> None:
    """Load Hub service credentials and make a local Synapse Admin API call."""
    try:
        admin_user, admin_pass = _parse_matrix_hub_admin_creds()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Matrix user management is still being provisioned. Try again shortly.",
        )
    except ValueError as exc:
        logger.error("Invalid Matrix Hub service credentials: %s", exc)
        raise HTTPException(status_code=500, detail="Matrix Hub service credentials are invalid.")

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None, _matrix_update_user, domain, admin_user, admin_pass, username, payload
        )
    except MatrixAdminAPIError as exc:
        if exc.status_code == 409:
            raise HTTPException(status_code=400, detail=exc.detail)
        if exc.status_code in (401, 403):
            logger.error("Matrix Hub service account was rejected by Synapse: HTTP %s", exc.status_code)
            raise HTTPException(status_code=502, detail="Matrix Hub service account was rejected by Synapse.")
        if 400 <= exc.status_code < 500:
            raise HTTPException(status_code=400, detail=exc.detail)
        raise HTTPException(status_code=502, detail="Synapse could not complete the request.")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Matrix Synapse Admin API is unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Matrix Synapse is temporarily unavailable.")
    except Exception:
        logger.exception("Unexpected Matrix Synapse Admin API failure")
        raise HTTPException(status_code=502, detail="Matrix Synapse user-management request failed.")


class MatrixCreateUserRequest(BaseModel):
    username: str
    password: str
    admin: bool = False


@app.post("/api/matrix/create-user")
async def api_matrix_create_user(req: MatrixCreateUserRequest):
    """Create a new Matrix user via the Synapse Admin API."""
    if not _validate_matrix_username(req.username):
        raise HTTPException(status_code=400, detail="Invalid username. Use only lowercase letters, digits, '.', '_', '-'.")
    if not req.password:
        raise HTTPException(status_code=400, detail="Password must not be empty.")

    # Read domain
    try:
        with open(MATRIX_DOMAINS_FILE, "r") as f:
            domain = f.read().strip()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Matrix domain not configured.")

    await _matrix_update_user_async(
        domain, req.username, {"password": req.password, "admin": req.admin}
    )

    return {"ok": True, "username": req.username}


class MatrixChangePasswordRequest(BaseModel):
    username: str
    new_password: str


@app.post("/api/matrix/change-password")
async def api_matrix_change_password(req: MatrixChangePasswordRequest):
    """Change a Matrix user's password via the Synapse Admin API."""
    if not _validate_matrix_username(req.username):
        raise HTTPException(status_code=400, detail="Invalid username. Use only lowercase letters, digits, '.', '_', '-'.")
    if not req.new_password:
        raise HTTPException(status_code=400, detail="New password must not be empty.")

    # Read domain
    try:
        with open(MATRIX_DOMAINS_FILE, "r") as f:
            domain = f.read().strip()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Matrix domain not configured.")

    await _matrix_update_user_async(
        domain, req.username, {"password": req.new_password}
    )

    return {"ok": True, "username": req.username}


# ── Startup: seed the internal IP file immediately ───────────────

@app.on_event("startup")
async def _startup_save_ip():
    """Write internal IP to file on server start so credentials work immediately."""
    loop = asyncio.get_event_loop()
    ip = await loop.run_in_executor(None, _get_internal_ip)
    _save_internal_ip(ip)


@app.on_event("startup")
async def _startup_session_secret():
    """Ensure the session secret exists on disk at startup."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _get_or_create_session_secret)
    # Preload persisted sessions so browser logins survive this restart (the
    # Hub service is restarted by nixos-rebuild switch during every rebuild).
    await loop.run_in_executor(None, _load_sessions_once)


# ── Startup: recover stale RUNNING status files ──────────────────

_SAFE_UNIT_RE = re.compile(r'^[a-zA-Z0-9@._\-]+\.service$')


def _recover_stale_status(status_file: str, log_file: str, unit_name: str) -> bool:
    """If status_file says RUNNING but the systemd unit is not active, correct the status.

    Uses MainPID to confirm the process is truly gone before correcting, and
    checks ExecMainStatus (actual exit code) instead of Result (which may
    reflect a prior run) to determine SUCCESS vs FAILED.

    Returns True if a correction was made, False otherwise.
    """
    if not _SAFE_UNIT_RE.match(unit_name):
        return False

    try:
        with open(status_file, "r") as f:
            status = f.read().strip()
    except FileNotFoundError:
        return False

    if status != "RUNNING":
        return False

    # Check if the unit is actively running
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit_name],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip() == "active":
            return False  # Still genuinely running — nothing to recover
    except Exception:
        return False  # Can't determine state — don't touch anything

    # Double-check: if MainPID is still alive, the unit is still running
    # (systemctl is-active can transiently lie during daemon-reload)
    try:
        show = subprocess.run(
            ["systemctl", "show", unit_name, "--property=MainPID"],
            capture_output=True, text=True, timeout=10,
        )
        if show.returncode == 0:
            pid_line = show.stdout.strip()  # "MainPID=12345"
            pid_str = pid_line.split("=", 1)[-1] if "=" in pid_line else "0"
            pid = int(pid_str)
            if pid > 0:
                try:
                    os.kill(pid, 0)  # Signal 0 = check if process exists
                    return False  # PID is still alive — unit is still running
                except ProcessLookupError:
                    pass  # PID is gone — unit truly finished
                except PermissionError:
                    return False  # Process exists but we can't signal it — assume running
    except Exception:
        pass

    # Unit is truly not running. Determine outcome from ExecMainStatus
    # (the actual exit code), NOT Result (which may be stale from a prior run).
    unit_result = "failed"
    try:
        show = subprocess.run(
            ["systemctl", "show", unit_name, "--property=ExecMainStatus"],
            capture_output=True, text=True, timeout=10,
        )
        if show.returncode == 0:
            # Output is "ExecMainStatus=0" for success, non-zero for failure
            val = show.stdout.strip().split("=", 1)[-1] if "=" in show.stdout.strip() else ""
            if val == "0":
                unit_result = "success"
    except Exception:
        pass

    if unit_result == "success":
        new_status = "REBOOT_REQUIRED" if unit_name == UPDATE_UNIT else "SUCCESS"
    else:
        new_status = "FAILED"
    try:
        with open(status_file, "w") as f:
            f.write(new_status)
    except OSError:
        pass
    if new_status == "REBOOT_REQUIRED":
        msg = "\n[Update staged successfully while the server was restarting. Reboot required.]\n"
    elif new_status == "SUCCESS":
        msg = "\n[Update completed successfully while the server was restarting.]\n"
    else:
        msg = "\n[Update encountered an error. See log above for details.]\n"
    try:
        with open(log_file, "a") as f:
            f.write(msg)
    except OSError:
        pass
    return True


@app.on_event("startup")
async def _startup_recover_stale_status():
    """Reset stale RUNNING status files left by interrupted update/rebuild jobs."""
    global _update_recovery_happened
    loop = asyncio.get_event_loop()
    corrected = await loop.run_in_executor(None, _recover_stale_status, UPDATE_STATUS, UPDATE_LOG, UPDATE_UNIT)
    if corrected:
        _update_recovery_happened = True
    await loop.run_in_executor(None, _recover_stale_status, REBUILD_STATUS, REBUILD_LOG, REBUILD_UNIT)


@app.on_event("startup")
async def _startup_migrate_deprecated_features():
    """Strip deprecated feature lines from the Hub Managed section of custom.nix."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _migrate_strip_deprecated_features)


async def _background_domain_reachability_checker():
    """Periodically curl configured domains and cache reachability results."""
    await asyncio.sleep(_DOMAIN_REACHABILITY_STARTUP_DELAY)
    consecutive_failures = 0
    while True:
        try:
            cfg = load_config()
            services = cfg.get("services", [])

            unit_to_feature = {
                unit: feat_id
                for feat_id, unit in FEATURE_SERVICE_MAP.items()
                if unit is not None
            }

            loop = asyncio.get_event_loop()
            overrides, *_ = await loop.run_in_executor(None, _read_hub_overrides)

            domains_to_check: list[str] = []
            for entry in services:
                unit = entry.get("unit", "")
                icon = entry.get("icon", "")
                enabled = entry.get("enabled", True)

                feat_id = unit_to_feature.get(unit)
                if feat_id is None:
                    feat_id = FEATURE_ICON_MAP.get(icon)
                if feat_id is not None and feat_id in overrides:
                    enabled = overrides[feat_id]
                if not enabled:
                    continue

                domain_key = SERVICE_DOMAIN_MAP.get(unit)
                if not domain_key:
                    continue
                domain_path = os.path.join(DOMAINS_DIR, domain_key)
                try:
                    with open(domain_path, "r") as f:
                        domain = f.read(512).strip()
                    if domain:
                        domains_to_check.append(domain)
                except OSError:
                    continue

            if domains_to_check:
                # Preserve domain order while removing duplicates.
                unique_domains = list(dict.fromkeys(domains_to_check))
                results = await asyncio.gather(*[
                    loop.run_in_executor(None, _check_domain_reachable, domain)
                    for domain in unique_domains
                ])
                checked_at = time.time()
                with _domain_reachability_cache_lock:
                    for domain, result in zip(unique_domains, results):
                        result["checked_at"] = checked_at
                        _domain_reachability_cache[domain] = result
            consecutive_failures = 0
        except asyncio.CancelledError:
            raise
        except Exception:
            consecutive_failures += 1
            logger.exception("Background domain reachability checker error")
            if consecutive_failures >= 3:
                logger.warning(
                    "Background domain reachability checker has failed %d consecutive times",
                    consecutive_failures,
                )

        await asyncio.sleep(_DOMAIN_REACHABILITY_TTL)


@app.on_event("startup")
async def _startup_domain_reachability():
    """Start the background domain reachability checker."""
    global _domain_reachability_task
    async with _domain_reachability_task_lock:
        if _domain_reachability_task is None or _domain_reachability_task.done():
            _domain_reachability_task = asyncio.create_task(_background_domain_reachability_checker())


@app.on_event("startup")
async def _startup_security_migrations():
    """Run one-time security upgrade migrations on every server start."""
    loop = asyncio.get_event_loop()
    # Migrate legacy njalla.sh DDNS lines to JSON store and archive the script
    await loop.run_in_executor(None, _migrate_legacy_njalla_script)
    # Remove the legacy fleet-wide support key from /root/.ssh/authorized_keys
    await loop.run_in_executor(None, _remove_legacy_root_support_key)
    # Expire any support session that has passed its deadline
    await loop.run_in_executor(None, _expire_support_if_stale)
    # Reconcile the expiry timer: if a valid session survived startup expiry,
    # schedule the server-side timer so expiry occurs even without user activity.
    await loop.run_in_executor(None, _reconcile_expiry_timer)


def _reconcile_expiry_timer() -> None:
    """Reschedule the expiry timer from persisted session metadata on startup.

    Called after ``_expire_support_if_stale`` so only still-valid sessions are
    rescheduled.  Cancels any previously running timer first.
    """
    try:
        with open(SUPPORT_STATUS_FILE, "r") as f:
            info = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _cancel_expiry_timer()
        return
    session_id = info.get("session_id")
    expires_at = info.get("expires_at")
    if session_id and expires_at and time.time() < expires_at:
        _schedule_expiry_timer(session_id, expires_at)
    else:
        _cancel_expiry_timer()


@app.on_event("shutdown")
async def _shutdown_domain_reachability():
    """Stop the background domain reachability checker and cancel expiry timer."""
    global _domain_reachability_task
    async with _domain_reachability_task_lock:
        task = _domain_reachability_task
        _domain_reachability_task = None
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    _cancel_expiry_timer()
