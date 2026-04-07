"""Sovran_SystemsOS Hub — FastAPI web server."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import pwd
import re
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel

from .config import load_config
from . import systemctl as sysctl

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

# ── Tunnel (VPS WireGuard) constants ─────────────────────────────

TUNNEL_STATE_DIR       = "/var/lib/sovran-tunnel"
TUNNEL_CONFIG_FILE     = "/var/lib/sovran-tunnel/tunnel.json"
TUNNEL_WG_PRIVKEY_FILE = "/var/lib/sovran-tunnel/wg-privatekey"
TUNNEL_WG_PUBKEY_FILE  = "/var/lib/sovran-tunnel/wg-publickey"
TUNNEL_HUB_SSH_KEY     = "/var/lib/sovran-tunnel/hub-mgmt-key"  # private key for Hub→VPS mgmt SSH
TUNNEL_SETUP_SCRIPT    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "vps-tunnel-setup.sh")
VPS_MGMT_USER          = "sovran-mgmt"

REBOOT_COMMAND = ["reboot"]

ONBOARDING_FLAG = "/var/lib/sovran/onboarding-complete"

# ── Tech Support constants ────────────────────────────────────────

SUPPORT_KEY_FILE = "/root/.ssh/sovran_support_authorized"
AUTHORIZED_KEYS  = "/root/.ssh/authorized_keys"
SUPPORT_STATUS_FILE = "/var/lib/secrets/support-session-status"

# Sovran Systems tech support public key
SOVRAN_SUPPORT_PUBKEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFLY8hjksaWzQmIQVutTBLkTYuXQbnPF03dFQnUV+PJF sovransystemsos-support"

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
}

# ── App setup ────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Sovran_SystemsOS Hub")

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


def check_for_updates() -> bool:
    locked_rev, branch = _get_locked_info()
    remote_rev = _get_remote_rev(branch)
    if locked_rev and remote_rev:
        return locked_rev != remote_rev
    return False


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

# ── QR code helper ────────────────────────────────────────────────

def _generate_qr_base64(data: str) -> str | None:
    """Generate a QR code PNG and return it as a base64-encoded data URI.
    Uses qrencode CLI (available on the system via credentials-pdf.nix)."""
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

def _read_hub_overrides() -> tuple[dict, str | None]:
    """Parse the Hub Managed section inside custom.nix.
    Returns (features_dict, nostr_npub_or_none)."""
    features: dict[str, bool] = {}
    nostr_npub = None
    try:
        with open(CUSTOM_NIX, "r") as f:
            content = f.read()
        begin = content.find(HUB_BEGIN)
        end = content.find(HUB_END)
        if begin == -1 or end == -1:
            return features, nostr_npub
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
    except FileNotFoundError:
        pass
    return features, nostr_npub


def _write_hub_overrides(features: dict, nostr_npub: str | None) -> None:
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
    overrides, _ = _read_hub_overrides()
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


# ── Tunnel (VPS WireGuard) helpers ───────────────────────────────

def _read_tunnel_config() -> dict | None:
    """Read tunnel configuration from TUNNEL_CONFIG_FILE. Returns None if not set up."""
    try:
        with open(TUNNEL_CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _get_vps_ip() -> str | None:
    """Return the VPS public IP from tunnel config, or None if not configured."""
    cfg = _read_tunnel_config()
    if cfg:
        return cfg.get("vps_ip") or cfg.get("vps_endpoint", "").split(":")[0] or None
    return None


def _tunnel_ssh(command: str, timeout: int = 15) -> tuple[int, str]:
    """Run a management command on the VPS via SSH using the Hub management key.

    Returns (returncode, output_str).
    """
    cfg = _read_tunnel_config()
    if not cfg:
        return (1, "Tunnel not configured")

    vps_ip = cfg.get("vps_ip") or cfg.get("vps_endpoint", "").split(":")[0]
    mgmt_user = cfg.get("mgmt_user", VPS_MGMT_USER)

    if not vps_ip or not os.path.exists(TUNNEL_HUB_SSH_KEY):
        return (1, "Tunnel SSH key or VPS IP not available")

    try:
        result = subprocess.run(
            [
                "ssh",
                "-i", TUNNEL_HUB_SSH_KEY,
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                "-o", "BatchMode=yes",
                f"{mgmt_user}@{vps_ip}",
                command,
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        return (result.returncode, (result.stdout + result.stderr).strip())
    except subprocess.TimeoutExpired:
        return (1, "SSH connection timed out")
    except Exception as exc:
        return (1, str(exc))


def _vps_enable_ssh_forward() -> bool:
    """Enable port 22 forwarding on the VPS through the tunnel."""
    cfg = _read_tunnel_config()
    if not cfg:
        return False  # No tunnel configured — SSH access is local only
    wan_iface = cfg.get("wan_iface", "eth0")
    home_wg_ip = cfg.get("home_wg_ip", "10.99.0.2")
    rc, out = _tunnel_ssh(f"sudo /etc/sovran/ssh-forward.sh enable {wan_iface} {home_wg_ip}")
    return rc == 0


def _vps_disable_ssh_forward() -> bool:
    """Disable port 22 forwarding on the VPS."""
    cfg = _read_tunnel_config()
    if not cfg:
        return False  # No tunnel configured
    wan_iface = cfg.get("wan_iface", "eth0")
    home_wg_ip = cfg.get("home_wg_ip", "10.99.0.2")
    rc, out = _tunnel_ssh(f"sudo /etc/sovran/ssh-forward.sh disable {wan_iface} {home_wg_ip}")
    return rc == 0


def _get_tunnel_status() -> dict:
    """Return current WireGuard tunnel health information."""
    cfg = _read_tunnel_config()
    if not cfg:
        return {"configured": False, "connected": False}

    vps_ip = cfg.get("vps_ip", "")
    wg_iface = "wg0"

    # Check WireGuard handshake age (seconds since last handshake)
    connected = False
    handshake_age: int | None = None
    bytes_rx: int | None = None
    bytes_tx: int | None = None

    try:
        result = subprocess.run(
            ["wg", "show", wg_iface, "dump"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split("\t")
                # Peer line: pubkey, preshared, endpoint, allowed-ips, last-handshake, rx, tx, keepalive
                if len(parts) >= 7:
                    last_hs = int(parts[4]) if parts[4].isdigit() else 0
                    if last_hs > 0:
                        handshake_age = int(time.time()) - last_hs
                        connected = handshake_age < 180  # < 3 minutes = connected
                    rx_raw = parts[5]
                    tx_raw = parts[6]
                    bytes_rx = int(rx_raw) if rx_raw.isdigit() else None
                    bytes_tx = int(tx_raw) if tx_raw.isdigit() else None
                    break
    except Exception:
        pass

    return {
        "configured": True,
        "connected": connected,
        "vps_ip": vps_ip,
        "handshake_age_seconds": handshake_age,
        "bytes_received": bytes_rx,
        "bytes_sent": bytes_tx,
        "wg_interface": wg_iface,
    }


def _enable_support() -> bool:
    """Add the Sovran support public key to the restricted support user's authorized_keys.

    Falls back to root's authorized_keys if the support user cannot be created.
    Applies POSIX ACLs to wallet directories to prevent access by the support
    user without explicit user consent.
    Also enables port 22 forwarding through the VPS tunnel if configured.
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

        # Enable VPS SSH forwarding if tunnel is configured
        vps_ssh_forwarding = False
        if _read_tunnel_config():
            vps_ssh_forwarding = _vps_enable_ssh_forward()

        session_info = {
            "enabled_at": time.time(),
            "enabled_at_human": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "use_restricted_user": use_restricted_user,
            "wallet_protected": use_restricted_user,
            "acl_applied": acl_applied,
            "protected_paths": wallet_paths,
            "vps_ssh_forwarding": vps_ssh_forwarding,
        }
        os.makedirs(os.path.dirname(SUPPORT_STATUS_FILE), exist_ok=True)
        with open(SUPPORT_STATUS_FILE, "w") as f:
            json.dump(session_info, f)

        _log_support_audit(
            "SUPPORT_ENABLED",
            f"restricted_user={use_restricted_user} acl_applied={acl_applied} "
            f"protected_paths={len(wallet_paths)} vps_ssh_forward={vps_ssh_forwarding}",
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

        # Disable VPS SSH forwarding if tunnel is configured
        if _read_tunnel_config():
            _vps_disable_ssh_forward()

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
    return {"ok": True}


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
    """Upgrade from Node role to Server+Desktop role by writing role-state.nix and rebuilding."""
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

    # Clear stale rebuild log
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

    return {"ok": True, "status": "rebuilding"}


# ── Bitcoin IBD sync helper ───────────────────────────────────────

BITCOIN_DATADIR = "/run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node"

# Simple in-process cache: (timestamp, result)
_btc_sync_cache: tuple[float, dict | None] = (0.0, None)
_BTC_SYNC_CACHE_TTL = 5  # seconds


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
    overrides, _ = await loop.run_in_executor(None, _read_hub_overrides)

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
            has_domain_issues = False
            if needs_domain:
                if not domain:
                    has_domain_issues = True
            health = "needs_attention" if has_domain_issues else "healthy"
            # Check Bitcoin IBD state
            if unit == "bitcoind.service":
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
            "needs_domain": needs_domain,
            "domain": domain,
        }
        if sync_ibd is not None:
            service_data["sync_ibd"] = sync_ibd
            service_data["sync_progress"] = sync_progress
            service_data["sync_blocks"] = sync_blocks
            service_data["sync_headers"] = sync_headers
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
    overrides, nostr_npub = await loop.run_in_executor(None, _read_hub_overrides)

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

    # Compute composite health
    sync_progress: float | None = None
    sync_blocks: int | None = None
    sync_headers: int | None = None
    sync_ibd: bool | None = None
    if not enabled:
        health = "disabled"
    elif status == "active":
        has_domain_issues = False
        if needs_domain:
            if not domain:
                has_domain_issues = True
            elif domain_status and domain_status.get("status") not in ("connected", None):
                has_domain_issues = True
        health = "needs_attention" if has_domain_issues else "healthy"
        # Check Bitcoin IBD state
        if unit == "bitcoind.service":
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
        "domain_status": domain_status,
        "external_ip": external_ip,
        "internal_ip": internal_ip,
        "feature": feature_entry,
    }
    if sync_ibd is not None:
        service_detail["sync_ibd"] = sync_ibd
        service_detail["sync_progress"] = sync_progress
        service_detail["sync_blocks"] = sync_blocks
        service_detail["sync_headers"] = sync_headers
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
    # Return VPS IP if tunnel is configured (used by domain setup UI)
    vps_ip = await loop.run_in_executor(None, _get_vps_ip)
    return {"internal_ip": internal, "external_ip": external, "vps_ip": vps_ip}


@app.get("/api/updates/check")
async def api_updates_check():
    loop = asyncio.get_event_loop()
    available = await loop.run_in_executor(None, check_for_updates)
    return {"available": available}


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

    status = await loop.run_in_executor(None, _read_update_status)
    if status == "RUNNING":
        return {"ok": True, "status": "already_running"}

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
    """Poll endpoint: reads status file + log file. No systemctl needed."""
    loop = asyncio.get_event_loop()

    status = await loop.run_in_executor(None, _read_update_status)
    new_log, new_offset = await loop.run_in_executor(None, _read_log, offset)

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

    # If tunnel is configured, report the VPS IP as the SSH address
    vps_ip = await loop.run_in_executor(None, _get_vps_ip)

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
        "ssh_address": vps_ip,  # VPS IP when tunnel is active, None otherwise
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


# ── Tunnel endpoints ──────────────────────────────────────────────

class TunnelSetupRequest(BaseModel):
    vps_ip: str
    vps_password: str


def _run_tunnel_setup(vps_ip: str, vps_password: str) -> None:
    """SSH into the VPS and run the bootstrap script.  Writes progress to the
    rebuild log so the frontend can stream it via /api/rebuild/status.
    """
    import shlex

    log_file = REBUILD_LOG
    status_file = REBUILD_STATUS

    def log(msg: str) -> None:
        with open(log_file, "a") as f:
            f.write(msg + "\n")

    try:
        with open(status_file, "w") as f:
            f.write("RUNNING")
        with open(log_file, "w") as f:
            f.write("")

        log("══════════════════════════════════════════════")
        log(f"  Sovran VPS Tunnel Setup — {time.strftime('%Y-%m-%d %H:%M:%S')}")
        log("══════════════════════════════════════════════")
        log("")

        # Ensure tunnel state directory exists
        os.makedirs(TUNNEL_STATE_DIR, mode=0o700, exist_ok=True)

        # Generate local WireGuard keypair if not already present
        home_privkey: str
        home_pubkey: str
        if os.path.exists(TUNNEL_WG_PRIVKEY_FILE) and os.path.exists(TUNNEL_WG_PUBKEY_FILE):
            log("── Reusing existing local WireGuard keypair")
            with open(TUNNEL_WG_PRIVKEY_FILE, "r") as f:
                home_privkey = f.read().strip()
            with open(TUNNEL_WG_PUBKEY_FILE, "r") as f:
                home_pubkey = f.read().strip()
        else:
            log("── Generating local WireGuard keypair…")
            priv_result = subprocess.run(
                ["wg", "genkey"], capture_output=True, text=True, timeout=10
            )
            if priv_result.returncode != 0:
                raise RuntimeError("wg genkey failed: " + priv_result.stderr)
            home_privkey = priv_result.stdout.strip()
            pub_result = subprocess.run(
                ["wg", "pubkey"], input=home_privkey, capture_output=True, text=True, timeout=10
            )
            if pub_result.returncode != 0:
                raise RuntimeError("wg pubkey failed: " + pub_result.stderr)
            home_pubkey = pub_result.stdout.strip()
            with open(TUNNEL_WG_PRIVKEY_FILE, "w") as f:
                f.write(home_privkey + "\n")
            os.chmod(TUNNEL_WG_PRIVKEY_FILE, 0o600)
            with open(TUNNEL_WG_PUBKEY_FILE, "w") as f:
                f.write(home_pubkey + "\n")
            log(f"   Local pubkey: {home_pubkey}")

        # Read the bootstrap script
        if not os.path.exists(TUNNEL_SETUP_SCRIPT):
            raise RuntimeError(f"Bootstrap script not found: {TUNNEL_SETUP_SCRIPT}")
        with open(TUNNEL_SETUP_SCRIPT, "r") as f:
            script_content = f.read()

        log(f"── Connecting to VPS at {vps_ip}…")

        # Use sshpass + ssh to run the bootstrap script on the VPS
        # sshpass is used only for the initial setup; afterwards Hub uses SSH key
        home_wg_ip = "10.99.0.2"
        remote_cmd = (
            f"bash -s -- {shlex.quote(home_pubkey)} {shlex.quote(home_wg_ip)}"
        )

        ssh_cmd = [
            "sshpass", "-p", vps_password,
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=15",
            f"root@{vps_ip}",
            remote_cmd,
        ]

        log("── Running VPS bootstrap script…")
        proc = subprocess.Popen(
            ssh_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        assert proc.stdout is not None
        raw_output_lines: list[str] = []
        for line in proc.stdout:
            line = line.rstrip("\n")
            raw_output_lines.append(line)
            if not line.startswith("---SOVRAN-TUNNEL-OUTPUT"):
                log(line)

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"VPS bootstrap script failed (exit {proc.returncode})")

        # Parse structured output
        output_block = "\n".join(raw_output_lines)
        begin_marker = "---SOVRAN-TUNNEL-OUTPUT-BEGIN---"
        end_marker = "---SOVRAN-TUNNEL-OUTPUT-END---"
        parsed: dict[str, str] = {}
        if begin_marker in output_block and end_marker in output_block:
            block = output_block.split(begin_marker, 1)[1].split(end_marker, 1)[0]
            for kv_line in block.strip().splitlines():
                kv_line = kv_line.strip()
                if "=" in kv_line:
                    k, v = kv_line.split("=", 1)
                    parsed[k.strip()] = v.strip()
        else:
            raise RuntimeError("VPS bootstrap output not found in script output")

        vps_pubkey = parsed.get("VPS_PUBKEY", "")
        vps_endpoint = parsed.get("VPS_ENDPOINT", f"{vps_ip}:51820")
        vps_wg_ip = parsed.get("VPS_WG_IP", "10.99.0.1")
        wan_iface = parsed.get("WAN_IFACE", "eth0")
        mgmt_user = parsed.get("MGMT_USER", VPS_MGMT_USER)
        hub_mgmt_privkey_b64 = parsed.get("HUB_MGMT_PRIVKEY_B64", "")

        if not vps_pubkey:
            raise RuntimeError("VPS public key not found in bootstrap output")

        log(f"   VPS WireGuard public key: {vps_pubkey}")
        log(f"   VPS endpoint: {vps_endpoint}")

        # Save Hub management SSH private key
        if hub_mgmt_privkey_b64:
            hub_mgmt_privkey = base64.b64decode(hub_mgmt_privkey_b64).decode("utf-8")
            with open(TUNNEL_HUB_SSH_KEY, "w") as f:
                f.write(hub_mgmt_privkey)
            os.chmod(TUNNEL_HUB_SSH_KEY, 0o600)
            log("   Hub management SSH key saved")

        # Write tunnel config
        tunnel_cfg = {
            "vps_ip": vps_ip,
            "vps_endpoint": vps_endpoint,
            "vps_pubkey": vps_pubkey,
            "vps_wg_ip": vps_wg_ip,
            "home_wg_ip": home_wg_ip,
            "wan_iface": wan_iface,
            "mgmt_user": mgmt_user,
            "setup_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        }
        with open(TUNNEL_CONFIG_FILE, "w") as f:
            json.dump(tunnel_cfg, f, indent=2)
        os.chmod(TUNNEL_CONFIG_FILE, 0o600)
        log("   Tunnel configuration saved")

        log("")
        log("── Writing local NixOS WireGuard configuration…")
        # The tunnel.nix module reads TUNNEL_CONFIG_FILE at build time;
        # trigger a rebuild to activate the WireGuard interface.
        log("")
        log("══════════════════════════════════════════════")
        log("  ✓ Tunnel setup completed successfully")
        log(f"  VPS IP: {vps_ip}")
        log(f"  WireGuard peer: {vps_endpoint}")
        log("══════════════════════════════════════════════")

        with open(status_file, "w") as f:
            f.write("SUCCESS")

        # Trigger a NixOS rebuild to activate the WireGuard interface
        subprocess.Popen(
            ["systemctl", "start", "--no-block", REBUILD_UNIT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    except Exception as exc:
        log(f"\n[ERROR] {exc}")
        log("══════════════════════════════════════════════")
        log("  ✗ Tunnel setup failed — see errors above")
        log("══════════════════════════════════════════════")
        with open(status_file, "w") as f:
            f.write("FAILED")


@app.post("/api/tunnel/setup")
async def api_tunnel_setup(req: TunnelSetupRequest):
    """SSH into the VPS and run the WireGuard bootstrap script.
    Progress is streamed via /api/rebuild/status (same log pattern as rebuilds)."""
    if not req.vps_ip.strip():
        raise HTTPException(status_code=400, detail="VPS IP address is required")
    if not req.vps_password.strip():
        raise HTTPException(status_code=400, detail="VPS root password is required")

    # Fire and forget — progress is read via /api/rebuild/status
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_tunnel_setup, req.vps_ip.strip(), req.vps_password.strip())

    return {"ok": True, "status": "running"}


@app.get("/api/tunnel/status")
async def api_tunnel_status():
    """Return current VPS WireGuard tunnel health."""
    loop = asyncio.get_event_loop()
    status = await loop.run_in_executor(None, _get_tunnel_status)
    return status


@app.post("/api/tunnel/ssh-forward/enable")
async def api_tunnel_ssh_forward_enable():
    """Enable port 22 forwarding through the VPS tunnel (called by Tech Support enable)."""
    loop = asyncio.get_event_loop()
    cfg = await loop.run_in_executor(None, _read_tunnel_config)
    if not cfg:
        raise HTTPException(status_code=404, detail="No tunnel configured")
    ok = await loop.run_in_executor(None, _vps_enable_ssh_forward)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to enable SSH forwarding on VPS")
    return {"ok": True, "message": "SSH port 22 forwarding enabled on VPS"}


@app.post("/api/tunnel/ssh-forward/disable")
async def api_tunnel_ssh_forward_disable():
    """Disable port 22 forwarding through the VPS tunnel."""
    loop = asyncio.get_event_loop()
    cfg = await loop.run_in_executor(None, _read_tunnel_config)
    if not cfg:
        raise HTTPException(status_code=404, detail="No tunnel configured")
    ok = await loop.run_in_executor(None, _vps_disable_ssh_forward)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to disable SSH forwarding on VPS")
    return {"ok": True, "message": "SSH port 22 forwarding disabled on VPS"}


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
    overrides, nostr_npub = await loop.run_in_executor(None, _read_hub_overrides)

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
    features, nostr_npub = await loop.run_in_executor(None, _read_hub_overrides)

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

    await loop.run_in_executor(None, _write_hub_overrides, features, nostr_npub)

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


def _validate_safe_name(name: str) -> bool:
    """Return True if name contains only safe path characters (no separators)."""
    return bool(name) and _SAFE_NAME_RE.match(name) is not None


@app.post("/api/domains/set")
async def api_domains_set(req: DomainSetRequest):
    """Save a domain and optionally register a DDNS URL."""
    if not _validate_safe_name(req.domain_name):
        raise HTTPException(status_code=400, detail="Invalid domain_name")
    os.makedirs(DOMAINS_DIR, exist_ok=True)
    domain_path = os.path.join(DOMAINS_DIR, req.domain_name)
    with open(domain_path, "w") as f:
        f.write(req.domain.strip())

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
    os.makedirs(DOMAINS_DIR, exist_ok=True)
    with open(os.path.join(DOMAINS_DIR, "sslemail"), "w") as f:
        f.write(req.email.strip())
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
