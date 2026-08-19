"""Regression tests for Hub update completion and polling recovery."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_APP_PARENT = _REPO_ROOT / "app"
if str(_APP_PARENT) not in sys.path:
    sys.path.insert(0, str(_APP_PARENT))

from sovran_systemsos_web.update_state import (  # noqa: E402
    effective_update_status,
    reboot_is_pending,
)


# Real store paths observed on the incident machine that prompted this rework.
RUNNING_GENERATION = (
    "84rsiqi66nc68jbikd26ms50ap831xf8-nixos-system-nixos-26.11.20260817.ec2d622"
)
PREVIOUS_GENERATION = (
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-nixos-system-nixos-26.11.20260816.old"
)
# What the stale Hub log still claimed was staged: a two-week-old update cycle.
HUB_LOG_GENERATION = (
    "yis0saq6p8fhqcaii0h2yzqf0blhdwns-nixos-system-nixos-26.11.20260804.e72e4f2"
)


class TestRebootPendingState(unittest.TestCase):
    """Reboot-pending state is derived from NixOS, not from Hub marker files.

    The system profile (what boots next) is compared against
    /run/current-system (what is running).  This stays correct no matter
    which tool performed the update: Hub "Update System", a terminal
    ``nixos-rebuild``, or an SSH support session.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = root / "store"
        self.store.mkdir()
        # /nix/var/nix/profiles/system is a two-hop chain: the diagnostics on
        # the incident box showed ``system`` -> ``system-148-link`` -> store.
        self.profile = root / "system"
        self.profile_entry = root / "system-148-link"
        # /run/current-system links straight to the running store path.
        self.current = root / "current-system"

    def _store_dir(self, name: str) -> str:
        path = self.store / name
        path.mkdir(exist_ok=True)
        return str(path)

    def _stage(self, booted: str, running: str) -> None:
        """Stage ``booted`` as the boot default with ``running`` live."""
        os.symlink(self._store_dir(booted), self.profile_entry)
        os.symlink(self.profile_entry, self.profile)
        os.symlink(self._store_dir(running), self.current)

    def test_hub_update_staged_and_not_yet_rebooted_is_pending(self):
        self._stage(booted=RUNNING_GENERATION, running=PREVIOUS_GENERATION)
        self.assertTrue(
            reboot_is_pending(str(self.profile), str(self.current))
        )

    def test_staged_generation_booted_is_no_longer_pending(self):
        self._stage(booted=RUNNING_GENERATION, running=RUNNING_GENERATION)
        self.assertFalse(
            reboot_is_pending(str(self.profile), str(self.current))
        )

    def test_terminal_switch_needs_no_reboot(self):
        # nixos-rebuild switch moves the profile AND current-system together.
        self._stage(booted=RUNNING_GENERATION, running=RUNNING_GENERATION)
        self.assertFalse(
            reboot_is_pending(str(self.profile), str(self.current))
        )

    def test_rollback_leaves_nothing_pending(self):
        # nixos-rebuild switch --rollback points both at the rollback target.
        self._stage(booted=PREVIOUS_GENERATION, running=PREVIOUS_GENERATION)
        self.assertFalse(
            reboot_is_pending(str(self.profile), str(self.current))
        )

    def test_unverifiable_state_is_never_a_reboot_demand(self):
        # No profile and no running system readable: the Hub must not nag
        # about a reboot it cannot substantiate.
        self.assertFalse(
            reboot_is_pending(str(self.profile), str(self.current))
        )

    def test_stale_hub_marker_clears_after_terminal_updates(self):
        """The exact incident: terminal-updated machine, frozen Hub marker.

        The user's last Hub update (old updater, weeks prior) left
        REBOOT_REQUIRED behind.  Every update since ran in a terminal and
        never touched the Hub's files, so the log still records a staged
        generation from 2026-08-04 while the machine runs a 2026-08-17
        build.  With the profile and the running system in agreement, the
        stale claim must reconcile to IDLE regardless of anything the old
        marker/log files say.
        """
        root = Path(self.tmp.name)
        log = root / "sovran-hub-update.log"
        log.write_text(
            "Done. The new configuration is "
            f"/nix/store/{HUB_LOG_GENERATION}\n"
            "✓ Update staged successfully\n",
            encoding="utf-8",
        )
        # Deliberately no sovran-hub-update.generation marker: the updater
        # that produced this state predates the marker feature.
        self.assertFalse(
            (root / "sovran-hub-update.generation").exists()
        )

        self._stage(booted=RUNNING_GENERATION, running=RUNNING_GENERATION)
        self.assertEqual(
            effective_update_status(
                "REBOOT_REQUIRED", str(self.profile), str(self.current)
            ),
            "IDLE",
        )

    def test_genuine_pending_reboot_claim_survives(self):
        # A staged generation that has NOT been booted yet: the claim is
        # true and must keep surfacing until the reboot really happens.
        self._stage(booted=RUNNING_GENERATION, running=PREVIOUS_GENERATION)
        self.assertEqual(
            effective_update_status(
                "REBOOT_REQUIRED", str(self.profile), str(self.current)
            ),
            "REBOOT_REQUIRED",
        )

    def test_other_statuses_pass_through_unchanged(self):
        self._stage(booted=RUNNING_GENERATION, running=RUNNING_GENERATION)
        for status in ("RUNNING", "FAILED", "SUCCESS", "IDLE"):
            self.assertEqual(
                effective_update_status(
                    status, str(self.profile), str(self.current)
                ),
                status,
            )


class TestUpdatePollingWiring(unittest.TestCase):
    """Guard the browser failure modes that caused a permanent spinner."""

    @classmethod
    def setUpClass(cls):
        js_dir = _REPO_ROOT / "app" / "sovran_systemsos_web" / "static" / "js"
        cls.update_js = (js_dir / "update.js").read_text(encoding="utf-8")
        cls.rebuild_js = (js_dir / "rebuild.js").read_text(encoding="utf-8")
        cls.helpers_js = (js_dir / "helpers.js").read_text(encoding="utf-8")
        cls.events_js = (js_dir / "events.js").read_text(encoding="utf-8")
        cls.template = (
            _REPO_ROOT / "app" / "sovran_systemsos_web" / "templates" / "index.html"
        ).read_text(encoding="utf-8")

    def test_status_fetches_have_an_abort_timeout(self):
        self.assertIn("function apiFetchWithTimeout", self.helpers_js)
        self.assertIn("new AbortController()", self.helpers_js)
        self.assertIn("controller.abort()", self.helpers_js)
        self.assertIn("apiFetchWithTimeout(", self.update_js)
        self.assertIn("STATUS_POLL_FETCH_TIMEOUT", self.update_js)

    def test_async_update_polls_cannot_overlap(self):
        self.assertIn("_updatePollInFlight", self.update_js)
        self.assertIn(
            "if (_updateFinished || _updatePollInFlight) return;", self.update_js
        )
        self.assertIn("finally", self.update_js)

    def test_connection_failure_has_explicit_non_running_ui(self):
        self.assertIn("showUpdateStatusUnavailable", self.update_js)
        self.assertIn("Update status unavailable", self.update_js)
        self.assertIn("Retry Status", self.template)
        self.assertIn("retryUpdateStatus", self.events_js)

    def test_rdp_or_tab_resume_forces_reconciliation(self):
        self.assertIn("resumeUpdateStatusAfterInterruption", self.events_js)
        self.assertIn('window.addEventListener("focus"', self.events_js)
        self.assertIn('document.addEventListener("visibilitychange"', self.events_js)

    def test_verbose_log_rendering_is_bounded(self):
        self.assertIn("UPDATE_VISIBLE_LOG_MAX_CHARS", self.update_js)
        self.assertIn("document.createTextNode(text)", self.update_js)
        self.assertNotIn("$modalLog.textContent += text", self.update_js)

    def test_page_reload_restores_running_or_completed_update(self):
        self.assertIn("restoreUpdateModalIfNeeded", self.update_js)
        self.assertIn("await restoreUpdateModalIfNeeded();", self.events_js)
        self.assertIn('current.result === "reboot_required"', self.update_js)

    def test_all_javascript_remains_syntax_valid(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not available in this test environment")
        for script in (
            _REPO_ROOT / "app" / "sovran_systemsos_web" / "static" / "js"
        ).glob("*.js"):
            result = subprocess.run(
                [node, "--check", str(script)], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
