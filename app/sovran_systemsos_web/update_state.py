"""Update-state helpers for the Sovran Hub.

The full-system updater stages a NixOS generation with ``nixos-rebuild boot``.
That generation is not active until the machine reboots — and the same is true
for updates started from a terminal or an SSH support session, which never go
near the Hub's status files.

The ONLY reliable indicator that a reboot is pending is NixOS itself: the
system profile (``/nix/var/nix/profiles/system``), which ``nixos-rebuild``
points at the newest generation on every ``boot`` AND every ``switch``, versus
``/run/current-system``, the generation actually running since the last boot.
When the two differ, a staged generation has not been booted yet.

Earlier revisions reconstructed this from a marker file and log tails written
by the Hub's own updater.  Any system updated by other means — or whose
``REBOOT_REQUIRED`` status was written by an updater older than the marker
feature — left the Hub showing "Restart required" forever: the recorded
generation could never equal the (since advanced) running one, so the marker
could never be cleared.

This module has no FastAPI or systemd dependencies so the policy can be tested
without importing the Hub server.
"""

from __future__ import annotations

import os

# The NixOS system profile.  ``nixos-rebuild boot`` and ``nixos-rebuild
# switch`` both add a generation here; ``boot`` additionally makes it the
# bootloader default.  The path is a symlink chain (``system`` ->
# ``system-N-link`` -> ``/nix/store/...-nixos-system-...``).
BOOT_PROFILE_PATH = "/nix/var/nix/profiles/system"
CURRENT_SYSTEM_PATH = "/run/current-system"


def reboot_is_pending(
    boot_profile_path: str = BOOT_PROFILE_PATH,
    current_system_path: str = CURRENT_SYSTEM_PATH,
) -> bool:
    """Return whether a staged NixOS generation has not been booted yet.

    This is deliberately independent of how the update was started — Hub
    "Update System", terminal ``nixos-rebuild boot``, or a support session all
    move the system profile the same way:

    * after ``nixos-rebuild boot``:  profile -> new, current -> old  → pending
    * after rebooting:               both -> new                     → cleared
    * after ``nixos-rebuild switch``: both move together             → no reboot
      ever needed (switch activates immediately)
    * after a rollback:              both point at the rollback target → cleared

    Unreadable or missing paths are treated as "not pending": the Hub must
    never demand a reboot it cannot substantiate.
    """
    try:
        boot_default = os.path.realpath(boot_profile_path)
        current = os.path.realpath(current_system_path)
    except OSError:
        return False
    if not os.path.exists(boot_default) or not os.path.exists(current):
        return False
    return boot_default != current


def effective_update_status(
    status: str,
    boot_profile_path: str = BOOT_PROFILE_PATH,
    current_system_path: str = CURRENT_SYSTEM_PATH,
) -> str:
    """Map a persisted Hub status to the one that reflects live NixOS state.

    Only ``REBOOT_REQUIRED`` is re-validated: it means "the update staged a
    generation the machine has not booted into", a claim that must stay true
    no matter which tool performed the last update.  When the boot default IS
    the running system the claim is stale — the staged generation booted, was
    superseded by a newer update, or the marker was written by an updater that
    could never clear it — so the effective status is ``IDLE``.

    All other statuses (``RUNNING``, ``FAILED``, ``SUCCESS``, ``IDLE``) pass
    through unchanged; RUNNING staleness is handled separately against the
    systemd unit itself.
    """
    if status == "REBOOT_REQUIRED" and not reboot_is_pending(
        boot_profile_path, current_system_path
    ):
        return "IDLE"
    return status
