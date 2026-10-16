"""Guards for the Mullvad VPN client being a plain Desktop Role install.

The desktop app and its daemon ship with Desktop Only and with no other role:
Server + Desktop and Bitcoin Node are machines that serve, and a VPN client with
its own DNS and routing policy is not something their services asked for.

Beyond that the install is deliberately boring. It is the NixOS service exactly
as NixOS ships it — no local-network boot service, no DNS or firewall edits of
our own, no Hub tile, no Feature Manager card, no toggles. The account, the
relay and the kill switch belong to the app.

Like the other nix-file checks these read the shipped sources as text: nothing is
run and nothing touches the network.
"""

import os
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _without_comments(src):
    """The source with whole-line `#` comments removed."""
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


class TheClientIsBuiltOnDesktopAndNowhereElse(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.module = _read("modules", "mullvad.nix")
        cls.code = _without_comments(cls.module)

    def test_the_module_is_imported(self):
        self.assertIn("./mullvad.nix", _read("modules", "modules.nix"))

    def test_the_gate_is_the_desktop_role(self):
        self.assertRegex(
            self.code,
            r"lib\.mkIf\s+config\.sovran_systemsOS\.roles\.desktop\s*\{",
        )

    def test_no_other_role_is_mentioned(self):
        self.assertNotIn("server_plus_desktop", self.code)
        self.assertNotIn("roles.node", self.code)

    def test_the_install_is_the_daemon_and_the_app(self):
        self.assertRegex(self.code, r"services\.mullvad-vpn\s*=\s*\{")
        self.assertRegex(self.code, r"(?m)^    enable = true;$")
        self.assertRegex(self.code, r"gui\.enable = true;")


class TheInstallStaysVanilla(unittest.TestCase):
    """Nothing is configured for the user, in the module or out of it."""

    @classmethod
    def setUpClass(cls):
        cls.module = _without_comments(_read("modules", "mullvad.nix"))

    def test_no_extra_services_are_added(self):
        self.assertNotIn("systemd.services", self.module)

    def test_no_dns_or_network_edits_of_our_own(self):
        # The NixOS module already turns on systemd-resolved and points
        # NetworkManager at it; re-declaring either here would be our policy,
        # not the distribution's.
        for key in ("services.resolved", "networkmanager", "networking."):
            self.assertNotIn(key, self.module)

    def test_no_firewall_or_kernel_edits(self):
        self.assertNotIn("firewall", self.module)
        self.assertNotIn("boot.", self.module)

    def test_no_packages_are_forced_in(self):
        self.assertNotIn("environment.systemPackages", self.module)

    def test_the_feature_flag_does_not_come_back(self):
        # A Hub-managed feature flag on an app that is simply installed would
        # put a toggle in front of something that has no decision to make.
        for path in (("modules", "core", "roles.nix"),
                     ("modules", "core", "role-logic.nix")):
            self.assertNotIn("mullvad", _read(*path).lower(), f"{path[-1]} mentions mullvad")


class TheHubDoesNotMentionIt(unittest.TestCase):
    """The app is not a service the Hub manages or announces."""

    def test_the_hub_tiles_and_roles_are_untouched(self):
        self.assertNotIn("mullvad", _read("modules", "core", "sovran-hub.nix").lower())

    def test_the_hub_backend_is_untouched(self):
        self.assertNotIn("mullvad", _read("app", "sovran_systemsos_web", "server.py").lower())

    def test_the_desktop_shell_is_untouched(self):
        # The app appears in the GNOME app grid by itself; no folder edit, no
        # dock entry.
        self.assertNotIn(
            "mullvad", _read("modules", "core", "sovran_systemsos-desktop.nix").lower())

    def test_there_is_no_icon_for_it(self):
        # app/icons holds Hub tile icons only.
        self.assertFalse(
            os.path.exists(os.path.join(_ROOT, "app", "icons", "mullvad.svg")))


if __name__ == "__main__":
    unittest.main()
