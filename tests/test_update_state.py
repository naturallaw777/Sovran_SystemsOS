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
    read_staged_generation,
    staged_generation_is_active,
)


GENERATION = (
    "/nix/store/rmi0g35cd8w60k0ig7pm6kb8kzws8b7x-"
    "nixos-system-nixos-26.11.20260817.ec2d622"
)
OTHER_GENERATION = (
    "/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-"
    "nixos-system-nixos-26.11.20260816.old"
)


class TestStagedGenerationState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.marker = root / "update.generation"
        self.log = root / "update.log"
        self.current = root / "current-system"

    def test_explicit_generation_marker_is_read(self):
        self.marker.write_text(GENERATION + "\n", encoding="utf-8")
        self.assertEqual(
            read_staged_generation(str(self.marker), str(self.log)), GENERATION
        )

    def test_legacy_updater_generation_is_recovered_from_log_tail(self):
        self.log.write_text(
            "building the system configuration...\n"
            f"Done. The new configuration is {GENERATION}\n"
            "✓ Update staged successfully\n",
            encoding="utf-8",
        )
        self.assertEqual(
            read_staged_generation(str(self.marker), str(self.log)), GENERATION
        )

    def test_latest_generation_line_wins(self):
        self.log.write_text(
            f"Done. The new configuration is {OTHER_GENERATION}\n"
            f"Done. The new configuration is {GENERATION}\n",
            encoding="utf-8",
        )
        self.assertEqual(
            read_staged_generation(str(self.marker), str(self.log)), GENERATION
        )

    def test_invalid_marker_is_ignored(self):
        self.marker.write_text("/tmp/not-a-generation\n", encoding="utf-8")
        self.log.write_text("no completed generation\n", encoding="utf-8")
        self.assertIsNone(read_staged_generation(str(self.marker), str(self.log)))

    def test_staged_generation_is_active_after_reboot(self):
        self.marker.write_text(GENERATION + "\n", encoding="utf-8")
        os.symlink(GENERATION, self.current)
        self.assertTrue(
            staged_generation_is_active(
                str(self.marker), str(self.log), str(self.current)
            )
        )

    def test_staged_generation_remains_pending_before_reboot(self):
        self.marker.write_text(GENERATION + "\n", encoding="utf-8")
        os.symlink(OTHER_GENERATION, self.current)
        self.assertFalse(
            staged_generation_is_active(
                str(self.marker), str(self.log), str(self.current)
            )
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
