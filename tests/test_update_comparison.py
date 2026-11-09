"""Updater comparison and review-before-update regression tests."""
import ast
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "app/sovran_systemsos_web/server.py"


def comparison_namespace():
    # Exercise the production functions without importing the optional Hub/Nix
    # runtime dependencies on a developer machine.
    tree = ast.parse(SERVER.read_text())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in {"_parse_version", "get_update_comparison"}]
    namespace = {"re": re}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SERVER), "exec"), namespace)
    return namespace


class TestComparison(unittest.TestCase):
    def compare(self, locked="abc", head="abc", installed="1.0.0", latest=(1, 0, 0), branch="stable"):
        ns = comparison_namespace()
        calls = []
        ns.update(_get_locked_info=lambda: (locked, branch),
                  _get_sovran_version=lambda fallback: installed,
                  _get_remote_rev=lambda ref: calls.append(ref) or head,
                  _get_remote_version=lambda ref: calls.append(ref) or latest)
        result = ns["get_update_comparison"]()
        self.assertEqual(calls, [branch, branch])
        return result

    def test_available_version(self):
        result = self.compare(head="new", latest=(1, 1, 0))
        self.assertEqual(result, {"available": True, "installed_version": "1.0.0",
                                  "latest_version": "1.1.0", "channel": "stable"})

    def test_unchanged_version_but_new_revision(self):
        self.assertTrue(self.compare(head="new")["available"])

    def test_failed_or_rolled_back_generation(self):
        self.assertTrue(self.compare(latest=(1, 1, 0))["available"])

    def test_up_to_date(self):
        self.assertFalse(self.compare()["available"])

    def test_network_failure_is_unknown(self):
        self.assertIsNone(self.compare(head=None, latest=None)["available"])
        self.assertIsNone(self.compare(latest=None)["available"])

    def test_missing_revision_falls_back_to_versions(self):
        self.assertFalse(self.compare(locked=None, head=None)["available"])
        self.assertTrue(self.compare(locked=None, head=None, latest=(1, 2, 0))["available"])

    def test_missing_installed_version_is_not_invented(self):
        result = self.compare(installed=None)
        self.assertIsNone(result["available"])
        self.assertIsNone(result["installed_version"])

    def test_tracks_locked_branch(self):
        self.assertEqual(self.compare(branch="staging-dev")["channel"], "staging-dev")


class TestReviewUI(unittest.TestCase):
    def test_review_flow(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        result = subprocess.run([node, str(ROOT / "tests/update_review_test.js")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
