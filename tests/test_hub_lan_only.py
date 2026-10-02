"""Guards for the Hub checking its own clients.

The Hub runs as root. Whether a packet may reach its port is up to the firewall
and the router; the application adds a second lock by answering only this
computer and the local network. These read the modules as text, like the other
nix-file checks: nothing is run and nothing touches the network.
"""

import os
import re
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _option(src, name):
    m = re.search(name + r"\s*=\s*lib\.mkOption\s*\{(.*?)\n      \};", src, re.S)
    return m.group(1) if m else None


class HubChecksItsOwnClients(unittest.TestCase):

    def test_lan_only_option_exists_and_defaults_on(self):
        body = _option(_read("modules", "core", "roles.nix"), "lanOnly")
        self.assertIsNotNone(body, "hub.lanOnly option not found")
        self.assertRegex(body, r"default\s*=\s*true")

    def test_extra_networks_option_exists_and_defaults_empty(self):
        body = _option(_read("modules", "core", "roles.nix"), "extraLanNetworks")
        self.assertIsNotNone(body, "hub.extraLanNetworks option not found")
        self.assertRegex(body, r"default\s*=\s*\[\s*\]")

    def test_policy_is_baked_into_the_generated_config(self):
        hub = _read("modules", "core", "sovran-hub.nix")
        self.assertRegex(hub, r"lan_only\s*=\s*cfg\.hub\.lanOnly\s*;")
        self.assertRegex(hub, r"lan_extra_networks\s*=\s*cfg\.hub\.extraLanNetworks\s*;")

    def test_a_typo_is_caught_at_build_time(self):
        hub = _read("modules", "core", "sovran-hub.nix")
        self.assertIn("builtins.all lanNetworkOk cfg.hub.extraLanNetworks", hub)

    def test_the_hub_enforces_it_in_its_own_middleware(self):
        server = _read("app", "sovran_systemsos_web", "server.py")
        self.assertIn("class LanOnlyMiddleware(BaseHTTPMiddleware)", server)
        self.assertIn("app.add_middleware(LanOnlyMiddleware", server)


if __name__ == "__main__":
    unittest.main()
