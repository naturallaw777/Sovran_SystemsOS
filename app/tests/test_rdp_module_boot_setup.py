import unittest
from pathlib import Path


RDP_NIX = Path(__file__).resolve().parents[2] / "modules" / "rdp.nix"


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
        self.assertIn('timeout --kill-after=5s 15s', self.setup_service)

    def test_setup_runs_grdctl_as_gnome_remote_desktop_user(self):
        self.assertIn("runuser -u gnome-remote-desktop -- \\", self.setup_service)
        self.assertIn('grdctl --system "$@"', self.setup_service)

    def test_hub_files_are_the_source_of_truth_for_username_and_password(self):
        self.assertIn('DEFAULT_USERNAME="sovran"', self.setup_service)
        self.assertIn('if [ ! -f "$USERNAME_FILE" ]; then', self.setup_service)
        self.assertIn("USERNAME=\"$(tr -d '\\n' < \"$USERNAME_FILE\")\"", self.setup_service)
        self.assertIn('if [ ! -f "$PASSWORD_FILE" ]; then', self.setup_service)
        self.assertIn('PASSWORD="$(tr -d \'\\n\' < "$PASSWORD_FILE")"', self.setup_service)
        self.assertIn('grdctl_system rdp set-credentials "$USERNAME" "$PASSWORD"', self.setup_service)
        self.assertNotIn('grdctl --system rdp set-credentials sovran "$PASSWORD"', self.setup_service)

    def test_secure_permissions_are_enforced_for_state_and_secret_files(self):
        self.assertIn('"d /var/lib/gnome-remote-desktop/tls 0700', self.source)
        self.assertIn('chmod 700 \\', self.setup_service)
        self.assertIn('chmod 600 "$USERNAME_FILE"', self.setup_service)
        self.assertIn('chmod 600 "$PASSWORD_FILE"', self.setup_service)
        self.assertIn('chmod 600 "$CRED_FILE"', self.setup_service)
        self.assertIn('chmod 600 "$TLS_DIR/rdp-tls.key"', self.setup_service)
        self.assertIn('chmod 644 "$TLS_DIR/rdp-tls.crt"', self.setup_service)


if __name__ == "__main__":
    unittest.main()
