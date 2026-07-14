import unittest
from pathlib import Path


RDP_NIX = Path(__file__).resolve().parents[2] / "modules" / "rdp.nix"
USERNAME_READ = "USERNAME=\"$(tr -d '\\n' < \"$USERNAME_FILE\")\""
USERNAME_LENGTH_GUARD = "if [ \"''${#USERNAME}\" -gt 32 ]; then"
SHORT_PASSWORD_GUARD = 'if [ "\'\'${#PASSWORD}" -lt 8 ]; then'


def _section(source: str, start: str, end: str) -> str:
    start_idx = source.find(start)
    if start_idx == -1:
        raise AssertionError(f"Expected section start not found: {start!r}")
    end_idx = source.find(end, start_idx)
    if end_idx == -1:
        raise AssertionError(f"Expected section end not found: {end!r}")
    return source[start_idx:end_idx]


class RdpModuleBootSetupTests(unittest.TestCase):
    def setUp(self):
        self.source = RDP_NIX.read_text()
        self.gnome_service = _section(
            self.source,
            "systemd.services.gnome-remote-desktop = {",
            "systemd.tmpfiles.rules = [",
        )
        self.setup_service = _section(
            self.source,
            "systemd.services.gnome-remote-desktop-setup = {",
            "};\n}",
        )

    def test_does_not_redeclare_gnome_remote_desktop_user(self):
        self.assertNotIn("users.users.gnome-remote-desktop", self.source)
        self.assertNotIn("createHome = true;", self.source)

    def test_main_service_requires_setup_before_starting(self):
        self.assertIn('wantedBy = [ "graphical.target" ];', self.gnome_service)
        self.assertIn('after = [ "gnome-remote-desktop-setup.service" ];', self.gnome_service)
        self.assertIn('requires = [ "gnome-remote-desktop-setup.service" ];', self.gnome_service)

    def test_setup_waits_for_configuration_service_and_bounded_timeout(self):
        self.assertIn('wantedBy = [ "graphical.target" ];', self.setup_service)
        self.assertIn('before = [ "gnome-remote-desktop.service" ];', self.setup_service)
        self.assertIn('"dbus.service"', self.setup_service)
        self.assertIn('"gnome-remote-desktop-configuration.service"', self.setup_service)
        self.assertNotIn("RemainAfterExit", self.setup_service)
        self.assertIn('TimeoutStartSec = "2min";', self.setup_service)
        self.assertIn('timeout --kill-after=5s 10s', self.setup_service)
        self.assertIn('echo "grdctl command timed out: $*" >&2', self.setup_service)
        self.assertIn('echo "grdctl command failed (exit $rc): $*" >&2', self.setup_service)

    def test_setup_runs_grdctl_directly_as_root(self):
        # The oneshot service runs as root; grdctl --system is called directly.
        # GRD 50.x invokes pkexec internally, but the call itself is plain
        # grdctl --system, not a manual pkexec invocation.
        self.assertIn('grdctl --system "$@"', self.setup_service)
        self.assertNotIn("runuser", self.setup_service)
        self.assertNotIn("sudo", self.setup_service)
        # No direct Nix-store pkexec invocation (pkgs.polkit}/bin/pkexec).
        self.assertNotIn("pkgs.polkit}/bin/pkexec", self.setup_service)

    def test_privilege_escalation_packages_absent_from_setup_path(self):
        self.assertNotIn("pkgs.polkit", self.setup_service)
        self.assertNotIn("pkgs.util-linux", self.setup_service)

    def test_run_wrappers_bin_prepended_to_path(self):
        # /run/wrappers/bin must be prepended to PATH before any grdctl_system
        # invocation so that grdctl --system resolves the NixOS setuid pkexec.
        path_export = 'export PATH="/run/wrappers/bin:$PATH"'
        grdctl_marker = "grdctl_system"
        script = self.setup_service
        path_idx = script.find(path_export)
        grdctl_idx = script.find(grdctl_marker)
        self.assertGreater(path_idx, -1, f"{path_export!r} not found in setup script")
        self.assertGreater(
            grdctl_idx, path_idx,
            "PATH export must appear before the first grdctl_system usage",
        )

    def test_pkexec_preflight_check(self):
        # A preflight must confirm /run/wrappers/bin/pkexec is executable
        # with a clear error message before any GRD configuration changes.
        self.assertIn("test -x /run/wrappers/bin/pkexec", self.setup_service)
        self.assertIn(
            "/run/wrappers/bin/pkexec is absent or not executable",
            self.setup_service,
        )

    def test_hub_files_are_the_source_of_truth_for_username_and_password(self):
        self.assertIn('DEFAULT_USERNAME="sovran"', self.setup_service)
        self.assertIn('if [ ! -f "$USERNAME_FILE" ]; then', self.setup_service)
        self.assertIn(USERNAME_READ, self.setup_service)
        self.assertIn(USERNAME_LENGTH_GUARD, self.setup_service)
        self.assertIn('case "$USERNAME" in', self.setup_service)
        self.assertIn('[A-Za-z_][A-Za-z0-9_-]*)', self.setup_service)
        self.assertIn("RDP username is too long (''${#USERNAME} characters, maximum 32)", self.setup_service)
        self.assertIn("RDP username must start with a letter or underscore and contain only letters, numbers, underscores, and hyphens", self.setup_service)
        self.assertIn('if [ ! -f "$PASSWORD_FILE" ]; then', self.setup_service)
        self.assertIn("tr -d '\\n'", self.setup_service)
        self.assertIn('"$PASSWORD_FILE"', self.setup_service)
        self.assertIn(SHORT_PASSWORD_GUARD, self.setup_service)
        self.assertIn("RDP password is too short (''${#PASSWORD} characters, minimum 8)", self.setup_service)
        self.assertIn('grdctl_system rdp set-credentials "$USERNAME" "$PASSWORD"', self.setup_service)
        self.assertNotIn('grdctl --system rdp set-credentials sovran "$PASSWORD"', self.setup_service)

    def test_secure_permissions_are_enforced_for_state_and_secret_files(self):
        self.assertIn('"d /var/lib/gnome-remote-desktop/tls 0700', self.source)
        self.assertIn("chmod 700", self.setup_service)
        self.assertIn('chmod 600 "$USERNAME_FILE"', self.setup_service)
        self.assertIn('chmod 600 "$PASSWORD_FILE"', self.setup_service)
        self.assertIn('chmod 600 "$CRED_FILE"', self.setup_service)
        self.assertIn('chmod 600 "$TLS_DIR/rdp-tls.key"', self.setup_service)
        self.assertIn('chmod 644 "$TLS_DIR/rdp-tls.crt"', self.setup_service)
        self.assertIn('LOCAL_IP="$(hostname -I | awk \'{print $1}\')"', self.setup_service)
        self.assertIn('LOCAL_IP="127.0.0.1"', self.setup_service)


if __name__ == "__main__":
    unittest.main()
