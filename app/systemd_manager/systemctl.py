from __future__ import annotations
import subprocess
from typing import Literal


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except Exception:
        return ""


def is_active(unit: str, scope: Literal["system", "user"] = "system") -> str:
    return _run(["systemctl", f"--{scope}", "is-active", unit]) or "unknown"


def is_enabled(unit: str, scope: Literal["system", "user"] = "system") -> str:
    return _run(["systemctl", f"--{scope}", "is-enabled", unit]) or "unknown"


def run_action(action: str, unit: str, scope: Literal["system", "user"] = "system", method: str = "systemctl") -> bool:
    """Fire a systemctl action (start/stop/restart). Returns True on success."""
    base_cmd = ["systemctl", f"--{scope}", action, unit]
    if scope == "system" and method == "pkexec":
        cmd = ["pkexec", "--user", "root"] + base_cmd
    else:
        cmd = base_cmd
    try:
        subprocess.run(cmd, timeout=30)
        return True
    except Exception:
        return False
