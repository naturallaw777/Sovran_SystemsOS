"""Thin wrapper around the systemctl CLI for Sovran_SystemsOS_Hub."""

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


def active_states(units_by_scope: dict[str, list[str]], timeout: float = 5) -> dict[tuple[str, str], str]:
    """Return active states for many units with one systemctl call per scope.

    The dashboard polls service state frequently. Spawning one ``systemctl``
    process per tile makes a slow or unavailable system bus multiply the delay
    (and can make the first dashboard render wait through many timeouts).  The
    ``is-active`` command accepts multiple units, so batch them and cap the
    whole batch at a single timeout.
    """
    states: dict[tuple[str, str], str] = {}
    valid_scopes = {"system", "user"}

    for scope, units in units_by_scope.items():
        unique_units = list(dict.fromkeys(unit for unit in units if unit))
        if not unique_units:
            continue
        if scope not in valid_scopes:
            for unit in unique_units:
                states[(scope, unit)] = "unknown"
            continue

        try:
            result = subprocess.run(
                ["systemctl", f"--{scope}", "is-active", "--", *unique_units],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            lines = result.stdout.splitlines()
            for index, unit in enumerate(unique_units):
                state = lines[index].strip() if index < len(lines) else ""
                states[(scope, unit)] = state or "unknown"
        except Exception:
            for unit in unique_units:
                states[(scope, unit)] = "unknown"

    return states


def is_enabled(unit: str, scope: Literal["system", "user"] = "system") -> str:
    return _run(["systemctl", f"--{scope}", "is-enabled", unit]) or "unknown"


def run_action(
    action: str,
    unit: str,
    scope: Literal["system", "user"] = "system",
    method: str = "systemctl",
) -> bool:
    base_cmd = ["systemctl", f"--{scope}", action, unit]
    if scope == "system" and method == "pkexec":
        cmd = ["pkexec", "--user", "root"] + base_cmd
    else:
        cmd = base_cmd
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False
