"""Thin wrapper around the systemctl CLI for Sovran_SystemsOS_Hub."""

from __future__ import annotations

import subprocess
from typing import Literal


def _run(cmd: list[str]) -> str:
    """Run a command and return stripped stdout (empty string on failure)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except Exception:
        return ""


def is_active(unit: str, scope: Literal["system", "user"] = "system") -> str:
    """Return the ActiveState string (active / inactive / failed / …)."""
    return _run(["systemctl", f"--{scope}", "is-active", unit]) or "unknown"


def is_enabled(unit: str, scope: Literal["system", "user"] = "system") -> str:
    """Return the UnitFileState string (enabled / disabled / masked / …)."""
    return _run(["systemctl", f"--{scope}", "is-enabled", unit]) or "unknown"


def run_action(
    action: str,
    unit: str,
    scope: Literal["system", "user"] = "system",
    method: str = "systemctl",
) -> bool:
    """Start / stop / restart a unit.

    For *system* units the command is elevated via *method* (pkexec or sudo).
    Returns True on apparent success.
    """
    base_cmd = ["systemctl", f"--{scope}", action, unit]

    if scope == "system" and method == "pkexec":
        cmd = ["pkexec", "--user", "root"] + base_cmd
    else:
        cmd = base_cmd

    try:
        subprocess.Popen(cmd)
        return True
    except Exception:
        return False