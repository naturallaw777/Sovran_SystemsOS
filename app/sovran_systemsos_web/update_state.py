"""Persistent update-state helpers for the Sovran Hub.

The full-system updater stages a NixOS generation with ``nixos-rebuild boot``.
That generation is not active until the machine reboots.  These helpers let the
Hub distinguish a genuinely pending reboot from an old REBOOT_REQUIRED marker
that survived the reboot.

This module deliberately has no FastAPI or systemd dependencies so its state
reconciliation can be tested without importing the Hub server.
"""

from __future__ import annotations

import os
import re


# Nix store hashes use the lower-case Nix base32 alphabet.  Keep the output
# name deliberately conservative: a system generation has no path separators.
_SYSTEM_GENERATION_RE = re.compile(
    r"^/nix/store/[0-9a-z]{32}-nixos-system-[A-Za-z0-9._+\-]+$"
)
_LOG_GENERATION_RE = re.compile(
    r"The new configuration is "
    r"(/nix/store/[0-9a-z]{32}-nixos-system-[A-Za-z0-9._+\-]+)"
)


def _valid_generation(value: str) -> str | None:
    """Return a normalized NixOS generation path, or ``None`` if invalid."""
    candidate = value.strip()
    if _SYSTEM_GENERATION_RE.fullmatch(candidate):
        return candidate
    return None


def read_staged_generation(marker_path: str, log_path: str) -> str | None:
    """Read the generation staged by the last successful Hub update.

    New updater versions write ``marker_path`` explicitly.  For an update that
    started with an older updater, recover the same value from the final
    ``nixos-rebuild`` log line.  Only the tail is needed and bounding the read
    avoids loading a potentially large build log during every status poll.
    """
    try:
        with open(marker_path, "r", encoding="utf-8") as marker:
            generation = _valid_generation(marker.read())
            if generation:
                return generation
    except OSError:
        pass

    try:
        with open(log_path, "rb") as log:
            log.seek(0, os.SEEK_END)
            size = log.tell()
            log.seek(max(0, size - 131_072), os.SEEK_SET)
            tail = log.read().decode("utf-8", errors="replace")
    except OSError:
        return None

    matches = list(_LOG_GENERATION_RE.finditer(tail))
    if not matches:
        return None
    return _valid_generation(matches[-1].group(1))


def staged_generation_is_active(
    marker_path: str,
    log_path: str,
    current_system_path: str = "/run/current-system",
) -> bool:
    """Return whether the staged update generation is now the running system."""
    staged = read_staged_generation(marker_path, log_path)
    if not staged:
        return False
    try:
        current = os.path.realpath(current_system_path)
    except OSError:
        return False
    return current == staged
