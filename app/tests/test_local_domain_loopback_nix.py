"""Structural regression tests for modules/core/local-domain-loopback.nix.

Verifies that the sovran-hosts-update helper:
  - is built as a pkgs.writeShellApplication with explicit runtimeInputs
    (gawk, gnugrep, coreutils);
  - uses ``lib.getExe hostsUpdateScript`` for both the systemd ExecStart and
    the activation script so that both contexts share the same Nix-store
    executable;
  - does NOT point ExecStart at the raw /etc path;
  - includes element-calling in the supported domain list;
  - uses ``awk -v`` for safe marker-variable passing rather than interpolating
    marker text directly into the awk program;
  - retains the domain validation regex (idempotency / injection prevention);
  - exposes /etc/sovran-hosts-update.sh as a symlink via ``source =`` (not a
    second raw ``text =`` body);
  - does NOT rely on environment.systemPackages for the helper's dependencies.
"""

import unittest
from pathlib import Path

NIX_FILE = (
    Path(__file__).resolve().parents[2]
    / "modules"
    / "core"
    / "local-domain-loopback.nix"
)


class LocalDomainLoopbackNixStructureTests(unittest.TestCase):
    def setUp(self):
        self.source = NIX_FILE.read_text()

    # ── writeShellApplication and explicit runtimeInputs ────────────────────

    def test_uses_write_shell_application(self):
        self.assertIn("pkgs.writeShellApplication", self.source)

    def test_runtime_inputs_includes_coreutils(self):
        self.assertIn("pkgs.coreutils", self.source)

    def test_runtime_inputs_includes_gawk(self):
        self.assertIn("pkgs.gawk", self.source)

    def test_runtime_inputs_includes_gnugrep(self):
        self.assertIn("pkgs.gnugrep", self.source)

    def test_runtime_inputs_block_present(self):
        self.assertIn("runtimeInputs", self.source)

    # ── Both execution paths use lib.getExe ─────────────────────────────────

    def test_exec_start_uses_lib_get_exe(self):
        """systemd ExecStart must reference the Nix-store executable."""
        self.assertIn("ExecStart = lib.getExe hostsUpdateScript", self.source)

    def test_activation_script_uses_lib_get_exe(self):
        """Activation text must call the same Nix-store executable."""
        self.assertIn("${lib.getExe hostsUpdateScript}", self.source)

    def test_exec_start_does_not_point_to_etc_path(self):
        """ExecStart must NOT use the raw /etc path (which lacks a deterministic PATH)."""
        self.assertNotIn('ExecStart = "/etc/sovran-hosts-update.sh"', self.source)

    # ── /etc symlink uses source =, not a second text = body ────────────────

    def test_etc_entry_uses_source_not_text(self):
        """The /etc/sovran-hosts-update.sh entry must be a symlink (source =),
        not a second raw script body (text =)."""
        self.assertIn(
            'environment.etc."sovran-hosts-update.sh".source', self.source
        )

    def test_etc_source_points_to_get_exe(self):
        self.assertIn(
            'environment.etc."sovran-hosts-update.sh".source = lib.getExe hostsUpdateScript',
            self.source,
        )

    # ── element-calling domain is supported ─────────────────────────────────

    def test_element_calling_domain_key_present(self):
        self.assertIn("element-calling", self.source)

    # ── Robust awk -v variable passing ──────────────────────────────────────

    def test_awk_uses_dash_v_for_begin_marker(self):
        """awk must receive the begin marker via -v, not by shell interpolation."""
        self.assertIn('awk -v begin=', self.source)

    def test_awk_uses_dash_v_for_end_marker(self):
        self.assertIn('-v end=', self.source)

    def test_awk_does_not_interpolate_marker_into_program(self):
        """The old pattern interpolated $BEGIN_MARKER directly into the awk source."""
        self.assertNotIn('/$BEGIN_MARKER', self.source)
        self.assertNotIn('/$END_MARKER', self.source)

    # ── Domain validation ────────────────────────────────────────────────────

    def test_domain_validation_regex_present(self):
        """The hostname validation regex must still be present for injection prevention."""
        self.assertIn("grep -qE", self.source)
        self.assertIn("[a-zA-Z0-9]", self.source)

    def test_invalid_domain_warning_present(self):
        self.assertIn("skipping invalid domain value", self.source)

    # ── No environment.systemPackages reliance ───────────────────────────────

    def test_no_environment_system_packages_for_helper(self):
        """The helper's tools are declared via runtimeInputs; the module must
        not add them to environment.systemPackages."""
        self.assertNotIn("environment.systemPackages", self.source)

    # ── Idempotency: existing Sovran block is removed before rewriting ───────

    def test_existing_block_removal_logic_present(self):
        """awk strip of the managed block must be present for idempotency."""
        self.assertIn("skip=1", self.source)
        self.assertIn("skip=0", self.source)

    # ── Activation script warns on failure rather than silently swallowing ───

    def test_activation_script_emits_warning_on_failure(self):
        self.assertIn("warning: sovran-hosts-update", self.source)


if __name__ == "__main__":
    unittest.main()
