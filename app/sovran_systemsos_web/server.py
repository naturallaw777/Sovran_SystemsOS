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
        "name": "BIP-110 (Bitcoin Better Money)",
        "description": "Bitcoin Knots with BIP-110 consensus changes",
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
        "description": "Use Bitcoin Core instead of Bitcoin Knots",
        "category": "bitcoin",
        "needs_domain": False,
        "domain_name": None,
        "needs_ddns": False,
        "extra_fields": [],
        "conflicts_with": ["bip110"],
        "port_requirements": [],
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
    "caddy.service":                    _PORTS_WEB,
    # Communication
    "matrix-synapse.service":           _PORTS_MATRIX_FEDERATION,
    "livekit.service":                  _PORTS_ELEMENT_CALLING,
    # Domain-based apps (80/443)
    "btcpayserver.service":             _PORTS_WEB,
    "vaultwarden.service":              _PORTS_WEB,
    "phpfpm-nextcloud.service":         _PORTS_WEB,
    "phpfpm-wordpress.service":         _PORTS_WEB,
    "haven-relay.service":              _PORTS_WEB,
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

_APP_JS_HASH  = _file_hash("app.js")
_STYLE_CSS_HASH = _file_hash("style.css")
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

def _get_listening_ports() -> dict[str, set[int]]:
    """Return sets of TCP and UDP ports that have services actively listening.

    Uses ``ss -tlnp`` for TCP and ``ss -ulnp`` for UDP.  Returns a dict with
    keys ``"tcp"`` and ``"udp"`` whose values are sets of integer port numbers.
    """
    result: dict[str, set[int]] = {"tcp": set(), "udp": set()}
    for proto, flag in (("tcp", "-tlnp"), ("udp", "-ulnp")):
        try:
            proc = subprocess.run(
                ["ss", flag],
                capture_output=True, text=True, timeout=10,
            )
            for line in proc.stdout.splitlines():
                # Column 4 is the local address:port (e.g. "0.0.0.0:443" or "[::]:443")
                parts = line.split()
                if len(parts) < 5:
                    continue
                addr = parts[4]
                # strip IPv6 brackets and extract port after last ":"
                port_str = addr.rsplit(":", 1)[-1]
                try:
                    result[proto].add(int(port_str))
                except ValueError:
                    pass
        except Exception:
            pass
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
        if proc.returncode == 0:
            text = proc.stdout
            # Match patterns like: tcp dport 443 accept  or  tcp dport { 80, 443 }
            for proto in ("tcp", "udp"):
                for m in re.finditer(
                    rf'{proto}\s+dport\s+\{{?([^}};\n]+)\}}?', text
                ):
                    raw = m.group(1)
                    for token in re.split(r'[\s,]+', raw):
                        token = token.strip()
                        if re.match(r'^\d+$', token):
                            result[proto].add(int(token))
                        elif re.match(r'^(\d+)-(\d+)$', token):
                            lo, hi = token.split("-")
                            result[proto].update(range(int(lo), int(hi) + 1))
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
        pt in ports_set
        for proto_key in protos
        for pt in listening.get(proto_key, set())
    )
    is_allowed = any(
        pt in allowed.get(proto_key, set())
        for proto_key in protos
        for pt in ports_set
    )

    if is_listening and is_allowed:
        return "listening"
    if is_allowed:
        return "firewall_open"
    return "closed"


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
    unit = FEATURE_SERVICE_MAP.get(feature_id)
    if unit is None:
        return None  # bip110, bitcoin-core — can't determine from config
    cfg = load_config()
    for svc in cfg.get("services", []):
        if svc.get("unit") == unit:
            return svc.get("enabled", False)
    return None


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

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "app_js_hash": _APP_JS_HASH,
        "style_css_hash": _STYLE_CSS_HASH,
    })


@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding(request: Request):
    return templates.TemplateResponse("onboarding.html", {
        "request": request,
        "onboarding_js_hash": _ONBOARDING_JS_HASH,
        "style_css_hash": _STYLE_CSS_HASH,
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
    return {
        "role": role,
        "role_label": ROLE_LABELS.get(role, role),
        "category_order": CATEGORY_ORDER,
        "feature_manager": True,
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

        port_requirements = SERVICE_PORT_REQUIREMENTS.get(unit, [])

        return {
            "name": entry.get("name", ""),
            "unit": unit,
            "type": scope,
            "icon": icon,
            "enabled": enabled,
            "category": entry.get("category", "other"),
            "status": status,
            "has_credentials": has_credentials,
            "port_requirements": port_requirements,
        }

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
    overrides, _ = await loop.run_in_executor(None, _read_hub_overrides)

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
    session = await loop.run_in_executor(None, _get_support_session_info)
    unlock_info = await loop.run_in_executor(None, _get_wallet_unlock_info)
    wallet_unlocked = bool(unlock_info)
    return {
        "active": active,
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
    """Add the Sovran support SSH key to allow remote tech support."""
    loop = asyncio.get_event_loop()
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


# ── Feature Manager endpoints ─────────────────────────────────────

@app.get("/api/features")
async def api_features():
    """Return all toggleable features with current state and domain requirements."""
    loop = asyncio.get_event_loop()
    overrides, nostr_npub = await loop.run_in_executor(None, _read_hub_overrides)

    ssl_email_path = os.path.join(DOMAINS_DIR, "sslemail")
    ssl_email_configured = os.path.exists(ssl_email_path)

    features = []
    for feat in FEATURE_REGISTRY:
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
    features, nostr_npub = await loop.run_in_executor(None, _read_hub_overrides)

    if req.enabled:
        # Element-calling requires matrix domain
        if req.feature == "element-calling":
            if not os.path.exists(os.path.join(DOMAINS_DIR, "matrix")):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Element Calling requires a Matrix domain to be configured. "
                        "Please run `sovran-setup-domains` first or configure the Matrix domain."
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
