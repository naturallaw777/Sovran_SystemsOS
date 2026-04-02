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
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from .config import load_config
from . import systemctl as sysctl

# ── Constants ──────────────────────────────��─────────────────────

FLAKE_LOCK_PATH = "/etc/nixos/flake.lock"
FLAKE_INPUT_NAME = "Sovran_Systems"
GITEA_API_BASE = "https://git.sovransystems.com/api/v1/repos/Sovran_Systems/Sovran_SystemsOS/commits"

UPDATE_LOG    = "/var/log/sovran-hub-update.log"
UPDATE_STATUS = "/var/log/sovran-hub-update.status"
UPDATE_UNIT   = "sovran-hub-update.service"

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
]

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

# ── Update check helpers ──────────────────��──────────────────────

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


# ── Startup: seed the internal IP file immediately ───────────────

@app.on_event("startup")
async def _startup_save_ip():
    """Write internal IP to file on server start so credentials work immediately."""
    loop = asyncio.get_event_loop()
    ip = await loop.run_in_executor(None, _get_internal_ip)
    _save_internal_ip(ip)
