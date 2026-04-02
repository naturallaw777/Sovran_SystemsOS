"""Sovran_SystemsOS Hub — FastAPI web server."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import socket
import subprocess
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

HUB_OVERRIDES_NIX = "/etc/nixos/hub-overrides.nix"
DOMAINS_DIR       = "/var/lib/domains"
NOSTR_NPUB_FILE   = "/var/lib/secrets/nostr_npub"
NJALLA_SCRIPT     = "/var/lib/njalla/njalla.sh"

INTERNAL_IP_FILE = "/var/lib/secrets/internal-ip"
ZEUS_CONNECT_FILE = "/var/lib/secrets/zeus-connect-url"

REBOOT_COMMAND = ["reboot"]

# ── Tech Support constants ────────────────────────────────────────

SUPPORT_KEY_FILE = "/root/.ssh/sovran_support_authorized"
AUTHORIZED_KEYS  = "/root/.ssh/authorized_keys"
SUPPORT_STATUS_FILE = "/var/lib/secrets/support-session-status"

# Sovran Systems tech support public key
SOVRAN_SUPPORT_PUBKEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFLY8hjksaWzQmIQVutTBLkTYuXQbnPF03dFQnUV+PJF sovransystemsos-support"

SUPPORT_KEY_COMMENT = "sovransystemsos-support"

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
        "name": "BIP-110 (Bitcoin Better Money)",
        "description": "Bitcoin Knots with BIP-110 consensus changes",
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
        "description": "Use Bitcoin Core instead of Bitcoin Knots",
        "category": "bitcoin",
        "needs_domain": False,
        "domain_name": None,
        "needs_ddns": False,
        "extra_fields": [],
        "conflicts_with": ["bip110"],
    },
]

# Map feature IDs to their systemd units in config.json
FEATURE_SERVICE_MAP = {
    "rdp": "gnome-remote-desktop.service",
    "haven": "haven-relay.service",
    "element-calling": "livekit.service",
    "mempool": "mempool-frontend.service",
    "bip110": None,
    "bitcoin-core": None,
}

ROLE_LABELS = {
    "server_plus_desktop": "Server + Desktop",
    "desktop":             "Desktop Only",
    "node":                "Bitcoin Node",
}

# ── App setup ────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Sovran_SystemsOS Hub")

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(_BASE_DIR, "static")),
    name="static",
)

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


# ── hub-overrides.nix helpers ─────────────────────────────────────

def _read_hub_overrides() -> tuple[dict, str | None]:
    """Parse hub-overrides.nix. Returns (features_dict, nostr_npub_or_none)."""
    features: dict[str, bool] = {}
    nostr_npub = None
    try:
        with open(HUB_OVERRIDES_NIX, "r") as f:
            content = f.read()
        for m in re.finditer(
            r'sovran_systemsOS\.features\.([a-zA-Z0-9_-]+)\s*=\s*(true|false)\s*;',
            content,
        ):
            features[m.group(1)] = m.group(2) == "true"
        m2 = re.search(r'sovran_systemsOS\.nostr_npub\s*=\s*"([^"]*)"', content)
        if m2:
            nostr_npub = m2.group(1)
    except FileNotFoundError:
        pass
    return features, nostr_npub


def _write_hub_overrides(features: dict, nostr_npub: str | None) -> None:
    """Write a complete hub-overrides.nix from the given state."""
    lines = []
    for feat_id, enabled in features.items():
        val = "true" if enabled else "false"
        lines.append(f"  sovran_systemsOS.features.{feat_id} = {val};")
    if nostr_npub:
        lines.append(f'  sovran_systemsOS.nostr_npub = "{nostr_npub}";')
    body = "\n".join(lines) + "\n" if lines else ""
    content = (
        "# Auto-generated by Sovran Hub — do not edit manually\n"
        "{ ... }:\n"
        "{\n"
        + body
        + "}\n"
    )
    nix_dir = os.path.dirname(HUB_OVERRIDES_NIX)
    if nix_dir:
        os.makedirs(nix_dir, exist_ok=True)
    with open(HUB_OVERRIDES_NIX, "w") as f:
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
    """Check if the support key is currently in authorized_keys."""
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


def _enable_support() -> bool:
    """Add the Sovran support public key to root's authorized_keys."""
    try:
        os.makedirs("/root/.ssh", mode=0o700, exist_ok=True)

        # Write the key to the dedicated support key file
        with open(SUPPORT_KEY_FILE, "w") as f:
            f.write(SOVRAN_SUPPORT_PUBKEY + "\n")
        os.chmod(SUPPORT_KEY_FILE, 0o600)

        # Append to authorized_keys if not already present
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

        # Write session metadata
        import time
        session_info = {
            "enabled_at": time.time(),
            "enabled_at_human": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        }
        os.makedirs(os.path.dirname(SUPPORT_STATUS_FILE), exist_ok=True)
        with open(SUPPORT_STATUS_FILE, "w") as f:
            json.dump(session_info, f)

        return True
    except Exception:
        return False


def _disable_support() -> bool:
    """Remove the Sovran support public key from authorized_keys."""
    try:
        # Remove from authorized_keys
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

        # Remove session metadata
        try:
            os.remove(SUPPORT_STATUS_FILE)
        except FileNotFoundError:
            pass

        return True
    except Exception:
        return False


def _verify_support_removed() -> bool:
    """Verify the support key is truly gone from authorized_keys."""
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


@app.get("/api/config")
async def api_config():
    cfg = load_config()
    role = cfg.get("role", "server_plus_desktop")
    return {
        "role": role,
        "role_label": ROLE_LABELS.get(role, role),
        "category_order": CATEGORY_ORDER,
    }


@app.get("/api/services")
async def api_services():
    cfg = load_config()
    services = cfg.get("services", [])

    loop = asyncio.get_event_loop()

    async def get_status(entry):
        unit = entry.get("unit", "")
        scope = entry.get("type", "system")
        enabled = entry.get("enabled", True)
        if enabled:
            status = await loop.run_in_executor(
                None, lambda: sysctl.is_active(unit, scope)
            )
        else:
            status = "disabled"

        creds = entry.get("credentials", [])
        has_credentials = len(creds) > 0

        return {
            "name": entry.get("name", ""),
            "unit": unit,
            "type": scope,
            "icon": entry.get("icon", ""),
            "enabled": enabled,
            "category": entry.get("category", "other"),
            "status": status,
            "has_credentials": has_credentials,
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
    return {
        "active": active,
        "enabled_at": session.get("enabled_at"),
        "enabled_at_human": session.get("enabled_at_human"),
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
        # 1. Check hub-overrides.nix first (explicit hub toggle)
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
            domain_configured = os.path.exists(os.path.join(DOMAINS_DIR, domain_name))

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


# ── Startup: seed the internal IP file immediately ───────────────

@app.on_event("startup")
async def _startup_save_ip():
    """Write internal IP to file on server start so credentials work immediately."""
    loop = asyncio.get_event_loop()
    ip = await loop.run_in_executor(None, _get_internal_ip)
    _save_internal_ip(ip)