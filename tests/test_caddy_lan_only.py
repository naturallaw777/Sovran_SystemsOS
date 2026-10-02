"""Guards for the LAN-only Caddy sites.

Ride The Lightning (:3051) and Mempool (:60847) sites are for the home network.
Caddy has to check where a request comes from because forwarding ports 80/443 on
the router lets other clients reach it too. The domain sites for the operator's
own public services must stay public. (The Hub is not a Caddy site: it is served
on its own port and checks its own clients.)

These read modules/core/caddy.nix like the nix-file checks in test_security.py:
nothing is run and nothing touches the network.
"""

import ipaddress
import os
import re
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

# What Caddy's "private_ranges" shortcut expands to (see the remote_ip matcher docs).
_PRIVATE_RANGES = ["192.168.0.0/16", "172.16.0.0/12", "10.0.0.0/8",
                   "127.0.0.1/8", "fd00::/8", "::1"]

_LAN_SITES = (":3051", ":60847")


def _read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _site(src, address):
    m = re.search(r"^" + re.escape(address) + r" \{\n(.*?)^\}$", src, re.S | re.M)
    return m.group(1) if m else None


def _snippet(src):
    m = re.search(r"^\(sovran_lan_only\) \{\n(.*?)^\}$", src, re.S | re.M)
    return m.group(1) if m else None


def _allowed_networks(snippet):
    m = re.search(r"^\s*@outside not remote_ip (.+)$", snippet, re.M)
    assert m, "the @outside matcher is missing"
    nets = []
    for token in m.group(1).split():
        for cidr in (_PRIVATE_RANGES if token == "private_ranges" else [token]):
            nets.append(ipaddress.ip_network(cidr, strict=False))
    return nets


def _is_allowed(nets, address):
    ip = ipaddress.ip_address(address)
    return any(ip.version == n.version and ip in n for n in nets)


class LanOnlySites(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read("modules", "core", "caddy.nix")

    def test_lan_sites_use_the_guard_before_they_proxy(self):
        for address in _LAN_SITES:
            with self.subTest(site=address):
                body = _site(self.src, address)
                self.assertIsNotNone(body, f"{address} site not found")
                self.assertIn("import sovran_lan_only", body)
                self.assertLess(body.index("import sovran_lan_only"),
                                body.index("reverse_proxy"))

    def test_only_the_lan_sites_use_the_guard(self):
        self.assertEqual(self.src.count("import sovran_lan_only"), len(_LAN_SITES))
        public = re.findall(r"^\$[A-Z]+ \{\n(.*?)^\}$", self.src, re.S | re.M)
        self.assertGreaterEqual(len(public), 6, "domain sites not found")
        for body in public:
            self.assertNotIn("sovran_lan_only", body)
        # the Matrix site that Element calling writes instead of the plain one
        self.assertNotIn("sovran_lan_only", _read("modules", "element-calling.nix"))

    def test_guard_closes_the_connection_for_everyone_else(self):
        snippet = _snippet(self.src)
        self.assertIsNotNone(snippet, "(sovran_lan_only) snippet not found")
        self.assertRegex(snippet, r"(?m)^\s*abort @outside\s*$")
        # defined before the sites that import it are written (the sites come
        # from bitcoinUiSites, which the generator appends after the snippet)
        self.assertLess(self.src.index("(sovran_lan_only) {"),
                        self.src.index("${bitcoinUiSites}"))

    def test_guard_ranges(self):
        nets = _allowed_networks(_snippet(self.src))
        for address in ("127.0.0.1", "::1", "10.0.0.1", "172.16.0.1", "172.31.255.254",
                        "192.168.1.10", "100.64.0.1", "100.127.255.254", "169.254.1.1",
                        "fd12:3456::1", "fe80::1", "fc00::1"):
            with self.subTest(allowed=address):
                self.assertTrue(_is_allowed(nets, address))
        for address in ("8.8.8.8", "1.1.1.1", "203.0.113.9", "9.255.255.255", "11.0.0.1",
                        "172.15.255.255", "172.32.0.1", "192.169.0.1", "100.63.255.255",
                        "100.128.0.1", "169.253.255.255"):
            with self.subTest(refused=address):
                self.assertFalse(_is_allowed(nets, address))

    def test_ipv6_global_addresses_are_not_filtered(self):
        # Computers on the home network often connect over their own global IPv6
        # address, which cannot be told apart from the internet's by address alone.
        # If this is ever tightened, LAN clients on IPv6 networks lose the Hub.
        nets = _allowed_networks(_snippet(self.src))
        self.assertTrue(_is_allowed(nets, "2001:db8::5"))


if __name__ == "__main__":
    unittest.main()
