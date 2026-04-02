"""Sovran_SystemsOS Hub — FastAPI web server."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import time
import urllib.request

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from .config import load_config
from . import systemctl as sysctl

# ── Constants ────────────────────────────────────────────────────

FLAKE_LOCK_PATH = "/etc/nixos/flake.lock"
FLAKE_INPUT_NAME = "Sovran_Systems"
GITEA_API_BASE = "https://git.sovransystems.com/api/v1/repos/Sovran_Systems/Sovran_SystemsOS/commits"

UPDATE_UNIT = "sovran-hub-update.service"
UPDATE_LOG  = "/var/log/sovran-hub-update.log"

REBOOT_COMMAND = ["reboot"]

CATEGORY_ORDER = [
    ("infrastructure", "Infrastructure"),
    ("bitcoin-base",   "Bitcoin Base"),
    ("bitcoin-apps",   "Bitcoin Apps"),
    ("communication",  "Communication"),
    ("apps",           "Self-Hosted Apps"),
    ("nostr",          "Nostr"),
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

# ── Track when we started an update ──────────────────────────────
# This timestamp lets us know that an update was recently kicked off,
# so we don't prematurely declare it finished if the unit hasn't
# transitioned to "active" yet.
_update_started_at: float = 0.0

# ── Update check helpers ─────────────────────────────────────────

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


# ── Update unit helpers ──────────────────────────────────────────

def _update_is_active() -> bool:
    """Return True if the update unit is currently running."""
    r = subprocess.run(
        ["systemctl", "is-active", "--quiet", UPDATE_UNIT],
        capture_output=True,
    )
    return r.returncode == 0


def _update_state() -> str:
    """Return the ActiveState of the update unit."""
    r = subprocess.run(
        ["systemctl", "show", "-p", "ActiveState", "--value", UPDATE_UNIT],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def _update_result() -> str:
    """Return 'success', 'failed', or 'unknown'."""
    r = subprocess.run(
        ["systemctl", "show", "-p", "Result", "--value", UPDATE_UNIT],
        capture_output=True, text=True,
    )
    val = r.stdout.strip()
    if val == "success":
        return "success"
    elif val:
        return "failed"
    return "unknown"


def _read_log(offset: int = 0) -> tuple[str, int]:
    """Read the update log file from the given byte offset.
    Returns (new_text, new_offset)."""
    try:
        with open(UPDATE_LOG, "rb") as f:
            f.seek(0, 2)  # seek to end
            size = f.tell()
            if offset > size:
                # Log was truncated (new run), start over
                offset = 0
            f.seek(offset)
            chunk = f.read()
            return chunk.decode(errors="replace"), offset + len(chunk)
    except FileNotFoundError:
        return "", 0


# ── Routes ───────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


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
    method = cfg.get("command_method", "systemctl")
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
        return {
            "name": entry.get("name", ""),
            "unit": unit,
            "type": scope,
            "icon": entry.get("icon", ""),
            "enabled": enabled,
            "category": entry.get("category", "other"),
            "status": status,
        }

    results = await asyncio.gather(*[get_status(s) for s in services])
    return list(results)


def _get_allowed_units() -> set[str]:
    cfg = load_config()
    return {s.get("unit", "") for s in cfg.get("services", []) if s.get("unit")}


@app.post("/api/services/{unit}/start")
async def service_start(unit: str):
    if unit not in _get_allowed_units():
        raise HTTPException(status_code=403, detail=f"Unit {unit!r} is not in the allowed service list")
    cfg = load_config()
    method = cfg.get("command_method", "systemctl")
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(
        None, lambda: sysctl.run_action("start", unit, "system", method)
    )
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to start {unit}")
    return {"ok": True}


@app.post("/api/services/{unit}/stop")
async def service_stop(unit: str):
    if unit not in _get_allowed_units():
        raise HTTPException(status_code=403, detail=f"Unit {unit!r} is not in the allowed service list")
    cfg = load_config()
    method = cfg.get("command_method", "systemctl")
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(
        None, lambda: sysctl.run_action("stop", unit, "system", method)
    )
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to stop {unit}")
    return {"ok": True}


@app.post("/api/services/{unit}/restart")
async def service_restart(unit: str):
    if unit not in _get_allowed_units():
        raise HTTPException(status_code=403, detail=f"Unit {unit!r} is not in the allowed service list")
    cfg = load_config()
    method = cfg.get("command_method", "systemctl")
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(
        None, lambda: sysctl.run_action("restart", unit, "system", method)
    )
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to restart {unit}")
    return {"ok": True}


@app.get("/api/network")
async def api_network():
    loop = asyncio.get_event_loop()
    internal, external = await asyncio.gather(
        loop.run_in_executor(None, _get_internal_ip),
        loop.run_in_executor(None, _get_external_ip),
    )
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
    global _update_started_at
    loop = asyncio.get_event_loop()

    running = await loop.run_in_executor(None, _update_is_active)
    if running:
        return {"ok": True, "status": "already_running"}

    # Reset failed state if any
    await asyncio.create_subprocess_exec(
        "systemctl", "reset-failed", UPDATE_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    # Record the start time so we can handle the race condition
    _update_started_at = time.monotonic()

    proc = await asyncio.create_subprocess_exec(
        "systemctl", "start", "--no-block", UPDATE_UNIT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()

    return {"ok": True, "status": "started"}


@app.get("/api/updates/status")
async def api_updates_status(offset: int = 0):
    """Poll endpoint: returns running state, result, and new log content."""
    global _update_started_at
    loop = asyncio.get_event_loop()

    active = await loop.run_in_executor(None, _update_is_active)
    state = await loop.run_in_executor(None, _update_state)
    result = await loop.run_in_executor(None, _update_result)
    new_log, new_offset = await loop.run_in_executor(None, _read_log, offset)

    # Race condition guard: if we just started the unit and it hasn't
    # transitioned to "activating"/"active" yet, report it as still running.
    # Give it up to 10 seconds to appear as active.
    if not active and _update_started_at > 0:
        elapsed = time.monotonic() - _update_started_at
        if elapsed < 10 and state in ("inactive", ""):
            # Unit hasn't started yet — tell the frontend it's still running
            return {
                "running": True,
                "result": "pending",
                "log": new_log,
                "offset": new_offset,
            }
        else:
            # Either it finished or the grace period expired
            _update_started_at = 0.0

    return {
        "running": active,
        "result": result,
        "log": new_log,
        "offset": new_offset,
    }