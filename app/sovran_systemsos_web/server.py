"""Sovran_SystemsOS Hub — FastAPI web server."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
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
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from .config import load_config
from . import systemctl as sysctl

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────

FLAKE_LOCK_PATH = "/etc/nixos/flake.lock"
FLAKE_INPUT_NAME = "Sovran_Systems"
GITEA_API_BASE = "https://git.sovransystems.com/api/v1/repos/Sovran_Systems/Sovran_SystemsOS/commits"

UPDATE_LOG    = "/var/log/sovran-hub-update.log"
UPDATE_STATUS = "/var/log/sovran-hub-update.status"
UPDATE_UNIT   = "sovran-hub-update.service"

REBUILD_LOG    = "/var/log/sovran-hub-rebuild.log"
REBUILD_STATUS = "/var/log/sovran-hub-rebuild.status"
REBUILD_UNIT   = "sovran-hub-rebuild.service"

# Set to True by _startup_recover_stale_status() when it corrects a stale
# RUNNING → SUCCESS/FAILED for the update unit.  Consumed by the first call
# to api_updates_status() so that the full log is returned to the frontend
# even when the frontend's offset is pointing past the pre-restart content.
_update_recovery_happened: bool = False

BACKUP_LOG    = "/var/log/sovran-hub-backup.log"
BACKUP_STATUS = "/var/log/sovran-hub-backup.status"
BACKUP_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "sovran-hub-backup.sh")

CUSTOM_NIX  = "/etc/nixos/custom.nix"
HUB_BEGIN   = "  # ── Hub Managed (do not edit) ──────────────"
HUB_END     = "  # ── End Hub Managed ────────────────────────"
DOMAINS_DIR = "/var/lib/domains"
NOSTR_NPUB_FILE   = "/var/lib/secrets/nostr_npub"
NJALLA_SCRIPT     = "/var/lib/njalla/njalla.sh"

INTERNAL_IP_FILE = "/var/lib/secrets/internal-ip"
ZEUS_CONNECT_FILE = "/var/lib/secrets/zeus-connect-url"

REBOOT_COMMAND = ["reboot"]

ONBOARDING_FLAG = "/var/lib/sovran/onboarding-complete"
AUTOLAUNCH_DISABLE_FLAG = "/var/lib/sovran/hub-autolaunch-disabled"

# ── Hub web authentication ────────────────────────────────────────

FREE_PASSWORD_FILE      = "/var/lib/secrets/free-password"
HUB_SESSION_SECRET_FILE = "/var/lib/secrets/hub-session-secret"
SESSION_COOKIE_NAME     = "hub_session"
SESSION_MAX_AGE         = 86400  # 24 hours

# In-memory session store: token → expiry timestamp (float)
_sessions: dict[str, float] = {}

# Failed login tracking: ip → list of failure timestamps
_login_failures: dict[str, list[float]] = {}
LOGIN_FAIL_DELAY  = 2.0   # seconds to sleep after a failed attempt
LOGIN_FAIL_WINDOW = 60.0  # rolling window (seconds) for counting failures
LOGIN_FAIL_MAX    = 10    # max failures in window before extra delay

# Public paths that are accessible without a valid session
_AUTH_EXEMPT_PATHS = {"/login", "/api/login", "/api/updates/status", "/api/rebuild/status", "/auto-login", "/api/ping"}
# Prefixes for static assets required by the login page
_AUTH_EXEMPT_PREFIXES = ("/static/css/", "/static/sovran-hub-icon.svg")

# ── Security constants ────────────────────────────────────────────

SECURITY_BANNER_DISMISSED_FLAG = "/var/lib/sovran/security-banner-dismissed"

# ── Tech Support constants ────────────────────────────────────────

SUPPORT_KEY_FILE = "/root/.ssh/sovran_support_authorized"
AUTHORIZED_KEYS  = "/root/.ssh/authorized_keys"
SUPPORT_STATUS_FILE = "/var/lib/secrets/support-session-status"

# Sovran Systems tech support public key
SOVRAN_SUPPORT_PUBKEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPxPF2Qm11FQxC20wydKtlmn/Bo07YnDda3b9/CyXxQP free@nixos"

SUPPORT_KEY_COMMENT = "sovransystemsos-support"

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
            {"port": "7882-7894",   "protocol": "UDP",     "description": "LiveKit media streams"},
            {"port": "5349",        "protocol": "TCP",     "description": "TURN over TLS"},
            {"port": "3478",        "protocol": "UDP",     "description": "TURN (STUN/relay)"},
            {"port": "30000-40000", "protocol": "TCP/UDP", "description": "TURN relay (WebRTC)"},
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
        "id": "bip110",
        "name": "Bitcoin Knots + BIP110",
        "description": "Only one Bitcoin node implementation can be active at a time: Bitcoin Knots (default), Bitcoin Knots + BIP110, or Bitcoin Core. Enabling this option replaces the default Bitcoin Knots with Bitcoin Knots + BIP110 consensus changes. It will disable the currently active alternative.",
        "category": "bitcoin",
        "needs_domain": False,
        "domain_name": None,
        "needs_ddns": False,
        "extra_fields": [],
        "conflicts_with": ["bitcoin-core"],
        "port_requirements": [],
    },
    {
        "id": "bitcoin-core",
        "name": "Bitcoin Core",
        "description": "Only one Bitcoin node implementation can be active at a time: Bitcoin Knots (default), Bitcoin Knots + BIP110, or Bitcoin Core. Enabling this option replaces the default Bitcoin Knots with Bitcoin Core. It will disable the currently active alternative.",
        "category": "bitcoin",
        "needs_domain": False,
        "domain_name": None,
        "needs_ddns": False,
        "extra_fields": [],
        "conflicts_with": ["bip110"],
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

# Map feature IDs to their systemd units in config.json
FEATURE_SERVICE_MAP = {
    "rdp": "gnome-remote-desktop.service",
    "haven": "haven-relay.service",
    "element-calling": "livekit.service",
    "mempool": "mempool.service",
    "bip110": None,
    "bitcoin-core": None,
    "btcpay-web": "btcpayserver.service",
    "sshd": "sshd.service",
}

# Port requirements for service tiles (keyed by unit name or icon)
# Services using only 80/443 for domain access share the same base list.
_PORTS_WEB = [
    {"port": "80",  "protocol": "TCP", "description": "HTTP (redirect to HTTPS)"},
    {"port": "443", "protocol": "TCP", "description": "HTTPS"},
]
_PORTS_MATRIX_FEDERATION = _PORTS_WEB + [
    {"port": "8448", "protocol": "TCP", "description": "Matrix server-to-server federation"},
]
_PORTS_ELEMENT_CALLING = _PORTS_WEB + [
    {"port": "7881",        "protocol": "TCP",     "description": "LiveKit WebRTC signalling"},
    {"port": "7882-7894",   "protocol": "UDP",     "description": "LiveKit media streams"},
    {"port": "5349",        "protocol": "TCP",     "description": "TURN over TLS"},
    {"port": "3478",        "protocol": "UDP",     "description": "TURN (STUN/relay)"},
    {"port": "30000-40000", "protocol": "TCP/UDP", "description": "TURN relay (WebRTC)"},
]

SERVICE_PORT_REQUIREMENTS: dict[str, list[dict]] = {
    # Infrastructure
    "caddy.service":                    [],
    # Communication
    "matrix-synapse.service":           _PORTS_MATRIX_FEDERATION,
    "livekit.service":                  _PORTS_ELEMENT_CALLING,
    # Domain-based apps (80/443)
    "btcpayserver.service":             _PORTS_WEB,
    "vaultwarden.service":              _PORTS_WEB,
    "phpfpm-nextcloud.service":         _PORTS_WEB,
    "phpfpm-wordpress.service":         _PORTS_WEB,
    "haven-relay.service":              _PORTS_WEB,
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
}

# For features that share a unit, disambiguate by icon field
FEATURE_ICON_MAP = {
    "bip110": "bip110",
    "bitcoin-core": "bitcoin-core",
}

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
    "node":                {"rdp", "bip110", "bitcoin-core", "mempool", "btcpay-web", "sshd"},
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
        "LND powers your Zeus wallet, Ride The Lightning dashboard, and BTCPayServer's "
        "Lightning capabilities. With Sovran_SystemsOS, it's always connected and ready."
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
        "Connect the Zeus mobile wallet to your Lightning node. Send and receive "
        "Lightning payments from your phone, backed by your own infrastructure. "
        "Scan the QR code and your phone becomes a sovereign wallet."
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
    "bisq-autoconnect.service": (
        "Bisq is a decentralized, peer-to-peer Bitcoin exchange — buy and sell Bitcoin "
        "with no KYC and no middleman. Sovran_SystemsOS automatically connects it to your "
        "local Bitcoin node on first boot, routing all traffic through Tor. Your trades are "
        "verified by your own node, keeping you fully sovereign.\n\n"
        "To use Bisq, open it directly from your desktop — it's already installed and "
        "auto-configured to connect to your local Bitcoin node."
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


def _create_session() -> str:
    """Create a new opaque session token and register it in the store."""
    _purge_expired_sessions()
    token = secrets.token_hex(32)
    _sessions[token] = time.time() + SESSION_MAX_AGE
    return token


def _destroy_session(token: str) -> None:
    """Remove a session token from the store."""
    _sessions.pop(token, None)


def _purge_expired_sessions() -> None:
    """Remove all expired sessions from the in-memory store."""
    now = time.time()
    expired = [tok for tok, exp in _sessions.items() if exp <= now]
    for tok in expired:
        del _sessions[tok]


def _is_authenticated(request: Request) -> bool:
    """Return True if the request carries a valid, unexpired session cookie."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return False
    expiry = _sessions.get(token)
    if expiry is None or time.time() >= expiry:
        _sessions.pop(token, None)
        return False
    # Slide the expiry window on activity
    _sessions[token] = time.time() + SESSION_MAX_AGE
    return True


def _read_free_password() -> str | None:
    """Return the contents of the free-password secrets file, or None."""
    try:
        with open(FREE_PASSWORD_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return None


def _check_password(submitted: str) -> bool:
    """Constant-time comparison of submitted password against the stored one."""
    stored = _read_free_password()
    if stored is None:
        return False
    return hmac.compare_digest(submitted.encode(), stored.encode())


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
                capture_output=True, text=True, timeout=10,
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
            capture_output=True, text=True, timeout=10,
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
            capture_output=True, text=True, timeout=10,
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


def _port_range_to_ints(port_str: str) -> list[int]:
    """Convert a port string like ``"443"``, ``"7882-7894"`` to a list of ints."""
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


# ── QR code helper ────────────────────────────────────────────────

def _generate_qr_base64(data: str) -> str | None:
    """Generate a QR code PNG and return it as a base64-encoded data URI.
    Uses qrencode CLI (available on the system via credentials.nix)."""
    try:
        result = subprocess.run(
            ["qrencode", "-o", "-", "-t", "PNG", "-s", "6", "-m", "2", "-l", "H", data],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            b64 = base64.b64encode(result.stdout).decode("ascii")
            return f"data:image/png;base64,{b64}"
    except Exception:
        pass
    return None


# ── Update helpers (file-based, no systemctl) ────────────────────

def _read_update_status() -> str:
    """Read the status file. Returns RUNNING, SUCCESS, FAILED, or IDLE."""
    try:
        with open(UPDATE_STATUS, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "IDLE"


def _write_update_status(status: str):
    """Write to the status file."""
    try:
        with open(UPDATE_STATUS, "w") as f:
            f.write(status)
    except OSError:
        pass


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

    # Static value
    if "value" in cred:
        result = {"label": label, "value": prefix + cred["value"] + suffix, "multiline": multiline}
        if qrcode:
            qr_data = _generate_qr_base64(result["value"])
            if qr_data:
                result["qrcode"] = qr_data
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

    value = prefix + raw + suffix
    result = {"label": label, "value": value, "multiline": multiline}

    if qrcode:
        qr_data = _generate_qr_base64(value)
        if qr_data:
            result["qrcode"] = qr_data

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


def _detect_external_drives() -> list[dict]:
    """Scan for mounted external USB drives.

    Uses ``lsblk`` to identify genuinely removable/hotplug devices and
    filters out internal system drives (BTCEcoandBackup, sovran_systemsos,
    /boot/efi, /run/media/Second_Drive).  Falls back to scanning
    /run/media/ directly if lsblk is unavailable, applying the same
    label/path filters.

    Returns a list of dicts with name, path, free_gb, total_gb.
    """
    import json as _json
    import subprocess as _subprocess

    drives: list[dict] = []
    seen_paths: set[str] = set()

    # ── Primary path: lsblk JSON ────────────────────────────────
    try:
        result = _subprocess.run(
            ["lsblk", "-J", "-o", "NAME,LABEL,MOUNTPOINT,HOTPLUG,RM,TYPE"],
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
                    drives.append({
                        "name":     drive_name,
                        "path":     drive_path,
                        "free_gb":  free_gb,
                        "total_gb": total_gb,
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
            features[m.group(1)] = m.group(2) == "true"
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
        val = "true" if enabled else "false"
        if feat_id == "btcpay-web":
            lines.append(f"  sovran_systemsOS.web.btcpayserver = lib.mkForce {val};")
        else:
            lines.append(f"  sovran_systemsOS.features.{feat_id} = lib.mkForce {val};")
    if nostr_npub:
        lines.append(f'  sovran_systemsOS.nostr_npub = lib.mkForce "{nostr_npub}";')
    if timezone:
        lines.append(f'  time.timeZone = lib.mkForce "{timezone}";')
    if locale:
        lines.append(f'  i18n.defaultLocale = lib.mkForce "{locale}";')
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

    with open(CUSTOM_NIX, "w") as f:
        f.write(content)


# ── Feature status helpers ─────────────────────────────────────────

def _is_feature_enabled_in_config(feature_id: str) -> bool | None:
    """Check if a feature's service appears as enabled in the running config.json.
    Returns True/False if found, None if the feature has no mapped service."""
    if feature_id == "btcpay-web":
        return False  # Default off in Node role; only on via explicit hub toggle
    unit = FEATURE_SERVICE_MAP.get(feature_id)
    if unit is None:
        return None  # bip110, bitcoin-core — can't determine from config
    cfg = load_config()
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
    """Check if the support key is currently in authorized_keys or support user's authorized_keys."""
    # Check support user's authorized_keys first
    try:
        with open(SUPPORT_USER_AUTH_KEYS, "r") as f:
            if SUPPORT_KEY_COMMENT in f.read():
                return True
    except FileNotFoundError:
        pass
    # Fall back to root authorized_keys
    try:
        with open(AUTHORIZED_KEYS, "r") as f:
            content = f.read()
        return SUPPORT_KEY_COMMENT in content
    except FileNotFoundError:
        return False


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


def _enable_support() -> bool:
    """Add the Sovran support public key to the restricted support user's authorized_keys.

    Falls back to root's authorized_keys if the support user cannot be created.
    Applies POSIX ACLs to wallet directories to prevent access by the support
    user without explicit user consent.
    """
    try:
        use_restricted_user = _ensure_support_user()

        if use_restricted_user:
            os.makedirs(SUPPORT_USER_SSH_DIR, mode=0o700, exist_ok=True)
            with open(SUPPORT_USER_AUTH_KEYS, "w") as f:
                f.write(SOVRAN_SUPPORT_PUBKEY + "\n")
            os.chmod(SUPPORT_USER_AUTH_KEYS, 0o600)
            try:
                pw = pwd.getpwnam(SUPPORT_USER)
                os.chown(SUPPORT_USER_AUTH_KEYS, pw.pw_uid, pw.pw_gid)
                os.chown(SUPPORT_USER_SSH_DIR, pw.pw_uid, pw.pw_gid)
            except Exception:
                pass
        else:
            # Fallback: add key to root's authorized_keys
            os.makedirs("/root/.ssh", mode=0o700, exist_ok=True)
            with open(SUPPORT_KEY_FILE, "w") as f:
                f.write(SOVRAN_SUPPORT_PUBKEY + "\n")
            os.chmod(SUPPORT_KEY_FILE, 0o600)

            existing = ""
            try:
                with open(AUTHORIZED_KEYS, "r") as f:
                    existing = f.read()
            except FileNotFoundError:
                pass

            if SUPPORT_KEY_COMMENT not in existing:
                with open(AUTHORIZED_KEYS, "a") as f:
                    f.write(SOVRAN_SUPPORT_PUBKEY + "\n")
                os.chmod(AUTHORIZED_KEYS, 0o600)

        acl_applied = _apply_wallet_acls() if use_restricted_user else False
        wallet_paths = _get_existing_wallet_paths()

        session_info = {
            "enabled_at": time.time(),
            "enabled_at_human": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "use_restricted_user": use_restricted_user,
            "wallet_protected": use_restricted_user,
            "acl_applied": acl_applied,
            "protected_paths": wallet_paths,
        }
        os.makedirs(os.path.dirname(SUPPORT_STATUS_FILE), exist_ok=True)
        with open(SUPPORT_STATUS_FILE, "w") as f:
            json.dump(session_info, f)

        _log_support_audit(
            "SUPPORT_ENABLED",
            f"restricted_user={use_restricted_user} acl_applied={acl_applied} "
            f"protected_paths={len(wallet_paths)}",
        )
        return True
    except Exception:
        return False


def _disable_support() -> bool:
    """Remove the Sovran support public key and revoke all wallet access."""
    try:
        # Remove from support user's authorized_keys
        try:
            os.remove(SUPPORT_USER_AUTH_KEYS)
        except FileNotFoundError:
            pass

        # Remove from root's authorized_keys (fallback / legacy)
        try:
            with open(AUTHORIZED_KEYS, "r") as f:
                lines = f.readlines()
            filtered = [l for l in lines if SUPPORT_KEY_COMMENT not in l]
            with open(AUTHORIZED_KEYS, "w") as f:
                f.writelines(filtered)
            os.chmod(AUTHORIZED_KEYS, 0o600)
        except FileNotFoundError:
            pass

        # Remove the dedicated key file
        try:
            os.remove(SUPPORT_KEY_FILE)
        except FileNotFoundError:
            pass

        # Revoke any outstanding wallet unlock
        try:
            os.remove(WALLET_UNLOCK_FILE)
        except FileNotFoundError:
            pass

        # Re-apply ACLs to ensure wallet access is revoked
        _revoke_wallet_acls()

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
    """Verify the support key is truly gone from all authorized_keys files."""
    try:
        with open(SUPPORT_USER_AUTH_KEYS, "r") as f:
            if SUPPORT_KEY_COMMENT in f.read():
                return False
    except FileNotFoundError:
        pass
    try:
        with open(AUTHORIZED_KEYS, "r") as f:
            content = f.read()
        return SUPPORT_KEY_COMMENT not in content
    except FileNotFoundError:
        return True  # No file = no key = removed


# ── Routes ───────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/auto-login")
async def auto_login_redirect(request: Request):
    """Localhost-only auto-login: create a session, set the cookie, and redirect to /.

    Only requests from 127.0.0.1 or ::1 are accepted so that remote clients on
    the LAN cannot bypass the password prompt by navigating to this URL.
    """
    client_ip = request.client.host if request.client else "unknown"
    if client_ip not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="Forbidden")
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
    return response


@app.post("/api/logout")
async def api_logout(request: Request):
    """Clear the session cookie and destroy the server-side session."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        _destroy_session(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
    })


@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding(request: Request):
    return templates.TemplateResponse("onboarding.html", {
        "request": request,
        "onboarding_js_hash": _ONBOARDING_JS_HASH,
    })


@app.get("/api/onboarding/status")
async def api_onboarding_status():
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
        await asyncio.create_subprocess_exec(*REBOOT_COMMAND)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to initiate reboot: {exc}")

    return {"ok": True, "status": "rebooting_to_onboarding"}


# ── Bitcoin IBD sync helper ───────────────────────────────────────

BITCOIN_DATADIR = "/run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node"

# Simple in-process cache: (timestamp, result)
_btc_sync_cache: tuple[float, dict | None] = (0.0, None)
_BTC_SYNC_CACHE_TTL = 5  # seconds

_btc_version_cache: tuple[float, dict | None] = (0.0, None)
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

# Cache: unit → (monotonic_timestamp, version_str | None)
_svc_version_cache: dict[str, tuple[float, str | None]] = {}
_SVC_VERSION_CACHE_TTL = 300  # 5 minutes — versions only change on system update


def _get_service_version(unit: str) -> str | None:
    """Extract the version of a service from its Nix store ExecStart path.

    Runs ``systemctl show <unit> --property=ExecStart --value`` and parses
    the Nix store path embedded in the output to obtain the package version.

    Results are cached for _SVC_VERSION_CACHE_TTL seconds so that repeated
    /api/services polls don't spawn extra processes on every request.
    Returns None if the version cannot be determined.
    """
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


def _parse_bitcoin_subversion(subversion: str) -> str:
    """Parse a subversion string like '/Bitcoin Knots:27.1.0/' into 'v27.1.0'.

    Examples:
      '/Bitcoin Knots:27.1.0/'          → 'v27.1.0'
      '/Satoshi:27.0.0/'                → 'v27.0.0'
      '/Bitcoin Knots:27.1.0(bip110)/'  → 'v27.1.0 (bip110)'
    Falls back to the raw subversion string if parsing fails.
    """
    m = re.search(r":(\d+\.\d+(?:\.\d+)*)", subversion)
    if m:
        ver = "v" + m.group(1)
        if "(bip110)" in subversion.lower():
            ver += " (bip110)"
        return ver
    return subversion


def _get_bitcoin_version_info() -> dict | None:
    """Call bitcoin-cli getnetworkinfo and return parsed JSON, or None on error.

    Results are cached for _BTC_VERSION_CACHE_TTL seconds since the version
    does not change while the service is running.
    """
    global _btc_version_cache
    now = time.monotonic()
    cached_at, cached_val = _btc_version_cache
    if now - cached_at < _BTC_VERSION_CACHE_TTL:
        return cached_val

    try:
        result = subprocess.run(
            ["bitcoin-cli", f"-datadir={BITCOIN_DATADIR}", "getnetworkinfo"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            _btc_version_cache = (now, None)
            return None
        info = json.loads(result.stdout)
        _btc_version_cache = (now, info)
        return info
    except Exception:
        _btc_version_cache = (now, None)
        return None


def _get_bitcoind_version() -> str | None:
    """Run ``bitcoind --version`` and return the raw version string, or None on error.

    Parses the first output line to extract the token after "version ".
    For example: "Bitcoin Knots daemon version v29.3.knots20260210+bip110-v0.4.1"
    returns "v29.3.knots20260210+bip110-v0.4.1".

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


def _format_bitcoin_version(raw_version: str, icon: str = "") -> str:
    """Format a raw version string from ``bitcoind --version`` for tile display.

    Strips the ``+bip110-vX.Y.Z`` patch suffix so the base version is shown
    cleanly (e.g. "v29.3.knots20260210+bip110-v0.4.1" → "v29.3.knots20260210").
    For the BIP110 tile (icon == "bip110") a " (bip110 vX.Y.Z)" tag is appended
    including the patch version.
    """
    # Extract the BIP110 patch version before stripping the suffix
    bip110_ver = ""
    bip_match = re.search(r"\+bip110-v(\S+)", raw_version)
    if bip_match:
        bip110_ver = bip_match.group(1)

    # Strip the +bip110... suffix for the base Knots version
    display = re.sub(r"\+bip110\S*", "", raw_version)

    # For BIP110 tile, append both the tag and the patch version
    if icon == "bip110":
        if bip110_ver:
            display += f" (bip110 v{bip110_ver})"
        elif "(bip110)" not in display.lower():
            display += " (bip110)"
    return display


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
            timeout=10,
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

    # Cache port/firewall data once for the entire /api/services request
    listening_ports, firewall_ports = await asyncio.gather(
        loop.run_in_executor(None, _get_listening_ports),
        loop.run_in_executor(None, _get_firewall_allowed_ports),
    )

    async def get_status(entry):
        unit = entry.get("unit", "")
        scope = entry.get("type", "system")
        icon = entry.get("icon", "")
        enabled = entry.get("enabled", True)

        # Overlay runtime feature state from custom.nix Hub Managed section
        feat_id = unit_to_feature.get(unit)
        if feat_id is None:
            feat_id = FEATURE_ICON_MAP.get(icon)
        if feat_id is not None and feat_id in overrides:
            enabled = overrides[feat_id]

        if enabled:
            status = await loop.run_in_executor(
                None, lambda: sysctl.is_active(unit, scope)
            )
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

        # Compute composite health
        sync_progress: float | None = None
        sync_blocks: int | None = None
        sync_headers: int | None = None
        sync_ibd: bool | None = None
        if not enabled:
            health = "disabled"
        elif status == "active":
            has_port_issues = False
            if port_requirements:
                for p in port_requirements:
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
            if needs_domain:
                if not domain:
                    has_domain_issues = True
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
        }
        if sync_ibd is not None:
            service_data["sync_ibd"] = sync_ibd
            service_data["sync_progress"] = sync_progress
            service_data["sync_blocks"] = sync_blocks
            service_data["sync_headers"] = sync_headers
        if unit == "bitcoind.service" and enabled:
            raw_ver = await loop.run_in_executor(None, _get_bitcoind_version)
            if raw_ver is not None:
                btc_ver = _format_bitcoin_version(raw_ver, icon=icon)
                service_data["bitcoin_version"] = btc_ver  # backwards compat
                service_data["version"] = btc_ver
        return service_data

    results = await asyncio.gather(*[get_status(s) for s in services])
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
    internal_ip, external_ip = await asyncio.gather(
        loop.run_in_executor(None, _get_internal_ip),
        loop.run_in_executor(None, _get_external_ip),
    )
    _save_internal_ip(internal_ip)

    # Domain status check
    domain_status: dict | None = None
    if needs_domain:
        if domain:
            def _check_one_domain(d: str) -> dict:
                try:
                    results = socket.getaddrinfo(d, None)
                    if not results:
                        return {
                            "status": "unresolvable",
                            "resolved_ip": None,
                            "expected_ip": external_ip,
                        }
                    resolved_ip = results[0][4][0]
                    if external_ip == "unavailable":
                        return {
                            "status": "error",
                            "resolved_ip": resolved_ip,
                            "expected_ip": external_ip,
                        }
                    if resolved_ip == external_ip:
                        return {
                            "status": "connected",
                            "resolved_ip": resolved_ip,
                            "expected_ip": external_ip,
                        }
                    return {
                        "status": "dns_mismatch",
                        "resolved_ip": resolved_ip,
                        "expected_ip": external_ip,
                    }
                except socket.gaierror:
                    return {
                        "status": "unresolvable",
                        "resolved_ip": None,
                        "expected_ip": external_ip,
                    }
                except Exception:
                    return {
                        "status": "error",
                        "resolved_ip": None,
                        "expected_ip": external_ip,
                    }

            domain_status = await loop.run_in_executor(None, _check_one_domain, domain)
        else:
            domain_status = {
                "status": "not_set",
                "resolved_ip": None,
                "expected_ip": external_ip,
            }

    # Port requirements and statuses
    port_requirements = SERVICE_PORT_REQUIREMENTS.get(unit, [])
    port_statuses: list[dict] = []
    if port_requirements:
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

    # Compute composite health
    sync_progress: float | None = None
    sync_blocks: int | None = None
    sync_headers: int | None = None
    sync_ibd: bool | None = None
    if not enabled:
        health = "disabled"
    elif status == "active":
        has_port_issues = any(p["status"] == "closed" for p in port_statuses)
        has_domain_issues = False
        if needs_domain:
            if not domain:
                has_domain_issues = True
            elif domain_status and domain_status.get("status") not in ("connected", None):
                has_domain_issues = True
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
        "port_requirements": port_requirements,
        "port_statuses": port_statuses,
        "external_ip": external_ip,
        "internal_ip": internal_ip,
        "feature": feature_entry,
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
            btc_ver = _format_bitcoin_version(raw_ver, icon=icon)
            service_detail["bitcoin_version"] = btc_ver  # backwards compat
            service_detail["version"] = btc_ver
    return service_detail


@app.get("/api/network")
async def api_network():
    loop = asyncio.get_event_loop()
    internal, external = await asyncio.gather(
        loop.run_in_executor(None, _get_internal_ip),
        loop.run_in_executor(None, _get_external_ip),
    )
    # Keep the internal-ip file in sync for credential lookups
    _save_internal_ip(internal)
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
    available = await loop.run_in_executor(None, check_for_updates)
    # None means inconclusive (check failed) — report as available so the UI doesn't block
    return {"available": available is not False}


@app.get("/api/ping")
async def api_ping():
    return {"ok": True}


@app.post("/api/reboot")
async def api_reboot():
    try:
        await asyncio.create_subprocess_exec(*REBOOT_COMMAND)
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


@app.post("/api/support/enable")
async def api_support_enable():
    """Add the Sovran support SSH key to allow remote tech support.
    Requires the sshd feature to be enabled first."""
    loop = asyncio.get_event_loop()

    # Gate: SSH feature must be enabled before support can be activated
    sshd_on = await loop.run_in_executor(None, _is_sshd_feature_enabled)
    if not sshd_on:
        raise HTTPException(
            status_code=400,
            detail="SSH must be enabled first. Please enable SSH Remote Access, then try again.",
        )

    ok = await loop.run_in_executor(None, _enable_support)
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


@app.post("/api/backup/run")
async def api_backup_run(target: str = ""):
    """Start the backup script as a background subprocess.
    Returns immediately; progress is read via /api/backup/status.
    """
    loop = asyncio.get_event_loop()
    status = await loop.run_in_executor(None, _read_backup_status)
    if status == "RUNNING":
        return {"ok": True, "status": "already_running"}

    # Clear stale log before starting
    try:
        with open(BACKUP_LOG, "w") as f:
            f.write("")
    except OSError:
        pass

    env = dict(os.environ)
    if target:
        env["BACKUP_TARGET"] = target

    # Fire-and-forget: the script writes its own status/log files.
    # Progress is read by the client via /api/backup/status (same pattern
    # as /api/updates/run and the rebuild feature).
    await asyncio.create_subprocess_exec(
        "/usr/bin/env", "bash", BACKUP_SCRIPT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
    )

    return {"ok": True, "status": "started"}


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
    registry = FEATURE_REGISTRY if allowed_features is None else [
        f for f in FEATURE_REGISTRY if f["id"] in allowed_features
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
        nostr_npub = new_npub
        try:
            os.makedirs(os.path.dirname(NOSTR_NPUB_FILE), exist_ok=True)
            with open(NOSTR_NPUB_FILE, "w") as f:
                f.write(nostr_npub)
        except OSError:
            pass

    await loop.run_in_executor(None, _write_hub_overrides, features, nostr_npub, cur_tz, cur_locale)

    # Clear the old rebuild log so the frontend doesn't pick up stale results
    try:
        open(REBUILD_LOG, "w").close()
    except OSError:
        pass

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
    try:
        pw = pwd.getpwnam("caddy")
        os.chown(path, pw.pw_uid, 0)
    except KeyError:
        pass


def _validate_safe_name(name: str) -> bool:
    """Return True if name contains only safe path characters (no separators)."""
    return bool(name) and _SAFE_NAME_RE.match(name) is not None


@app.post("/api/domains/set")
async def api_domains_set(req: DomainSetRequest):
    """Save a domain and optionally register a DDNS URL."""
    if not _validate_safe_name(req.domain_name):
        raise HTTPException(status_code=400, detail="Invalid domain_name")
    _ensure_domains_dir()
    domain_path = os.path.join(DOMAINS_DIR, req.domain_name)
    with open(domain_path, "w") as f:
        f.write(req.domain.strip())
    _chown_to_caddy(domain_path)

    if req.ddns_url:
        ddns_url = req.ddns_url.strip()
        # Strip leading "curl " if present
        if ddns_url.lower().startswith("curl "):
            ddns_url = ddns_url[5:].strip()
        # Strip surrounding quotes
        if len(ddns_url) >= 2 and ddns_url[0] in ('"', "'") and ddns_url[-1] == ddns_url[0]:
            ddns_url = ddns_url[1:-1]
        # Replace trailing &auto with &a=${IP}
        if ddns_url.endswith("&auto"):
            ddns_url = ddns_url[:-5] + "&a=${IP}"
        # Append curl line to njalla.sh
        njalla_dir = os.path.dirname(NJALLA_SCRIPT)
        if njalla_dir:
            os.makedirs(njalla_dir, exist_ok=True)
        with open(NJALLA_SCRIPT, "a") as f:
            f.write(f'curl "{ddns_url}"\n')
        try:
            os.chmod(NJALLA_SCRIPT, 0o755)
        except OSError:
            pass
        # Run njalla.sh immediately to update DNS
        try:
            subprocess.run([NJALLA_SCRIPT], timeout=30, check=False)
        except Exception:
            pass

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
    return {"ok": True}


@app.get("/api/domains/status")
async def api_domains_status():
    """Return the value of each known domain file (or null if missing)."""
    known = [
        "matrix", "haven", "element-calling", "sslemail",
        "vaultwarden", "btcpayserver", "nextcloud", "wordpress",
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
    external_ip = await loop.run_in_executor(None, _get_external_ip)

    def check_domain(domain: str) -> dict:
        try:
            results = socket.getaddrinfo(domain, None)
            if not results:
                return {
                    "domain": domain, "status": "unresolvable",
                    "resolved_ip": None, "expected_ip": external_ip,
                }
            resolved_ip = results[0][4][0]
            if external_ip == "unavailable":
                return {
                    "domain": domain, "status": "error",
                    "resolved_ip": resolved_ip, "expected_ip": external_ip,
                }
            if resolved_ip == external_ip:
                return {
                    "domain": domain, "status": "connected",
                    "resolved_ip": resolved_ip, "expected_ip": external_ip,
                }
            return {
                "domain": domain, "status": "dns_mismatch",
                "resolved_ip": resolved_ip, "expected_ip": external_ip,
            }
        except socket.gaierror:
            return {
                "domain": domain, "status": "unresolvable",
                "resolved_ip": None, "expected_ip": external_ip,
            }
        except Exception:
            return {
                "domain": domain, "status": "error",
                "resolved_ip": None, "expected_ip": external_ip,
            }

    check_results = await asyncio.gather(*[
        loop.run_in_executor(None, check_domain, d) for d in req.domains
    ])
    return {"domains": list(check_results)}


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
    ]

    errors: list[str] = []

    # Wipe filesystem paths
    for path in wipe_paths:
        if os.path.exists(path):
            try:
                import shutil as _shutil
                _shutil.rmtree(path, ignore_errors=True)
            except Exception as exc:
                errors.append(f"rm {path}: {exc}")

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
        errors.append(f"postgres wipe: {exc}")

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
        errors.append(f"mariadb wipe: {exc}")

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
                errors.append(f"chpasswd free: {(result.stderr or result.stdout).strip()}")
        except Exception as exc:
            errors.append(f"chpasswd free: {exc}")

        # Set root password
        try:
            result = subprocess.run(
                [chpasswd_bin],
                input=f"root:{new_root_password}",
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                errors.append(f"chpasswd root: {(result.stderr or result.stdout).strip()}")
        except Exception as exc:
            errors.append(f"chpasswd root: {exc}")
    else:
        errors.append("chpasswd not found; passwords not reset")

    # Write new passwords to secrets files
    try:
        os.makedirs("/var/lib/secrets", exist_ok=True)
        with open("/var/lib/secrets/free-password", "w") as f:
            f.write(new_free_password)
        os.chmod("/var/lib/secrets/free-password", 0o600)
    except Exception as exc:
        errors.append(f"write free-password: {exc}")

    try:
        os.makedirs("/var/lib/secrets", exist_ok=True)
        with open("/var/lib/secrets/root-password", "w") as f:
            f.write(new_root_password)
        os.chmod("/var/lib/secrets/root-password", 0o600)
    except Exception as exc:
        errors.append(f"write root-password: {exc}")

    # Delete GNOME Keyring files so a fresh keyring is created with the new
    # password on the next GDM login (PAM unlocks it automatically).
    keyring_dir = "/home/free/.local/share/keyrings"
    try:
        if os.path.isdir(keyring_dir):
            for entry in os.listdir(keyring_dir):
                entry_path = os.path.join(keyring_dir, entry)
                try:
                    if os.path.isfile(entry_path) or os.path.islink(entry_path):
                        os.unlink(entry_path)
                    elif os.path.isdir(entry_path):
                        shutil.rmtree(entry_path, ignore_errors=True)
                except Exception:
                    pass
    except Exception as exc:
        errors.append(f"keyring wipe: {exc}")

    # The user performed a full security reset — the banner's purpose is served.
    try:
        os.makedirs(os.path.dirname(SECURITY_BANNER_DISMISSED_FLAG), exist_ok=True)
        with open(SECURITY_BANNER_DISMISSED_FLAG, "w"):
            pass
    except OSError:
        pass  # Non-fatal

    return {"ok": True, "new_password": new_free_password, "errors": errors}


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
        store_errors = [str(exc)]

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
                expected_system_path = f"Build failed: {(result.stderr or result.stdout).strip()[:500]}"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    except subprocess.TimeoutExpired:
        expected_system_path = "Build timed out"
    except Exception as exc:
        expected_system_path = str(exc)

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
        raise HTTPException(status_code=500, detail=f"Failed to update system password: {exc}")

    # Write new password to secrets file so Hub credentials stay in sync
    try:
        os.makedirs(os.path.dirname(FREE_PASSWORD_FILE), exist_ok=True)
        with open(FREE_PASSWORD_FILE, "w") as f:
            f.write(req.new_password)
        os.chmod(FREE_PASSWORD_FILE, 0o600)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write secrets file: {exc}")

    # Delete GNOME Keyring files so a fresh keyring is created with the new
    # password on the next GDM login (PAM will unlock it automatically).
    keyring_dir = "/home/free/.local/share/keyrings"
    try:
        if os.path.isdir(keyring_dir):
            for entry in os.listdir(keyring_dir):
                entry_path = os.path.join(keyring_dir, entry)
                try:
                    if os.path.isfile(entry_path) or os.path.islink(entry_path):
                        os.unlink(entry_path)
                    elif os.path.isdir(entry_path):
                        shutil.rmtree(entry_path, ignore_errors=True)
                except Exception:
                    pass
    except Exception:
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

MATRIX_USERS_FILE = "/var/lib/secrets/matrix-users"
MATRIX_DOMAINS_FILE = "/var/lib/domains/matrix"

_SAFE_USERNAME_RE = re.compile(r'^[a-z0-9._\-]+$')


def _validate_matrix_username(username: str) -> bool:
    """Return True if username is a valid Matrix localpart."""
    return bool(username) and len(username) <= 255 and bool(_SAFE_USERNAME_RE.match(username))


def _parse_matrix_admin_creds() -> tuple[str, str]:
    """Parse admin username and password from the matrix-users credentials file.

    Returns (localpart, password) for the admin account.
    Raises FileNotFoundError if the file does not exist.
    Raises ValueError if the file cannot be parsed.
    """
    with open(MATRIX_USERS_FILE, "r") as f:
        content = f.read()

    admin_user: str | None = None
    admin_pass: str | None = None
    in_admin_section = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[ Admin Account ]":
            in_admin_section = True
            continue
        if stripped.startswith("[ ") and in_admin_section:
            break
        if in_admin_section:
            if stripped.startswith("Username:"):
                raw = stripped[len("Username:"):].strip()
                # Format is @localpart:domain — extract localpart
                if raw.startswith("@") and ":" in raw:
                    admin_user = raw[1:raw.index(":")]
                else:
                    admin_user = raw
            elif stripped.startswith("Password:"):
                admin_pass = stripped[len("Password:"):].strip()

    if not admin_user or not admin_pass:
        raise ValueError("Could not parse admin credentials from matrix-users file")
    if "(pre-existing" in admin_pass:
        raise ValueError(
            "Admin password is not stored (user was pre-existing). "
            "Please reset the admin password manually before using this feature."
        )
    return admin_user, admin_pass


def _matrix_get_admin_token(domain: str, admin_user: str, admin_pass: str) -> str:
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
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    token: str = body.get("access_token", "")
    if not token:
        raise ValueError("No access_token in Synapse login response")
    return token


class MatrixCreateUserRequest(BaseModel):
    username: str
    password: str
    admin: bool = False


@app.post("/api/matrix/create-user")
async def api_matrix_create_user(req: MatrixCreateUserRequest):
    """Create a new Matrix user via register_new_matrix_user."""
    if not _validate_matrix_username(req.username):
        raise HTTPException(status_code=400, detail="Invalid username. Use only lowercase letters, digits, '.', '_', '-'.")
    if not req.password:
        raise HTTPException(status_code=400, detail="Password must not be empty.")

    admin_flag = ["-a"] if req.admin else ["--no-admin"]
    cmd = [
        "register_new_matrix_user",
        "-c", "/run/matrix-synapse/runtime-config.yaml",
        "-u", req.username,
        "-p", req.password,
        *admin_flag,
        "http://localhost:8008",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="register_new_matrix_user not found on this system.")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Command timed out.")

    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        # Surface the actual error from the tool (e.g. "User ID already taken")
        raise HTTPException(status_code=400, detail=output or "Failed to create user.")

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

    # Parse admin credentials
    try:
        admin_user, admin_pass = _parse_matrix_admin_creds()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Matrix credentials file not found.")
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Obtain admin access token
    loop = asyncio.get_event_loop()
    try:
        token = await loop.run_in_executor(
            None, _matrix_get_admin_token, domain, admin_user, admin_pass
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not authenticate as admin: {exc}")

    # Call Synapse Admin API to reset the password
    target_user_id = f"@{req.username}:{domain}"
    url = f"http://[::1]:8008/_synapse/admin/v2/users/{urllib.parse.quote(target_user_id, safe='@:')}"
    payload = json.dumps({"password": req.new_password}).encode()
    api_req = urllib.request.Request(
        url, data=payload,
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
        body = exc.read().decode(errors="replace")
        try:
            detail = json.loads(body).get("error", body)
        except Exception:
            detail = body
        raise HTTPException(status_code=400, detail=detail)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Admin API call failed: {exc}")

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

    new_status = "SUCCESS" if unit_result == "success" else "FAILED"
    try:
        with open(status_file, "w") as f:
            f.write(new_status)
    except OSError:
        pass
    msg = (
        "\n[Update completed successfully while the server was restarting.]\n"
        if new_status == "SUCCESS"
        else "\n[Update encountered an error. See log above for details.]\n"
    )
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
