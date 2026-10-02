"""Guards for serving the Hub on its own port instead of through Caddy.

The Hub is the one service that runs as root. It listens on 0.0.0.0:8937
itself, so Caddy adds nothing it needs: not TLS (the site was plain http), not
authentication, not cache headers (the app sets its own). What it did add was a
second door: with ports 80/443 forwarded for public services, a Host header on
those ports reached the Hub. The Hub is therefore served on port 8937 only, and
Caddy keeps the two services it is actually needed for, because they listen on
loopback only: Ride The Lightning (:3051) and Mempool (:60847).

Like the other nix-file checks these read the modules as text: nothing is run
and nothing touches the network.
"""

import os
import re
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _without_comments(src):
    """The Nix source with `#` comment lines removed."""
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


def _binding(src, name):
    """The right-hand side of a top-level `name = ...;` binding in a let/attrset."""
    m = re.search(r"^\s*" + re.escape(name) + r"\s*=\s*(?P<v>.*?);\s*$", src, re.M | re.S)
    assert m, f"{name} not found"
    return m.group("v")


class HubIsNotACaddySite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.caddy = _read("modules", "core", "caddy.nix")
        cls.code = _without_comments(cls.caddy)

    def test_there_is_no_site_for_the_hub(self):
        self.assertNotRegex(self.code, r"sovransystemsos\.local")
        self.assertNotIn("8937", self.code)

    def test_the_public_ports_still_belong_to_the_public_sites(self):
        # Caddy now also runs to bridge RTL and Mempool (even on Node Only),
        # which must not open 80/443 by itself: those follow the domain-based
        # services and nothing else.
        self.assertRegex(
            self.code,
            r"networking\.firewall\.allowedTCPPorts\s*=\s*lib\.mkIf\s+needsHttpsPorts\s*\[\s*80\s+443\s*\]",
        )


class CaddyDoesNoAddressFiltering(unittest.TestCase):
    """Caddy is a bridge for RTL and Mempool and a TLS front for public sites.

    It used to carry a client-address guard (sovran_lan_only). That guard was
    never aimed at these two sites: the bug was a Host header on ports 80/443
    reaching the Hub, and RTL and Mempool sit on ports of their own. It also
    could not be made right for IPv6, where a laptop's global address on the
    LAN is indistinguishable from a stranger's.
    """

    @classmethod
    def setUpClass(cls):
        cls.caddy = _read("modules", "core", "caddy.nix")
        cls.code = _without_comments(cls.caddy)

    def test_there_is_no_address_filter(self):
        # (private_ranges is deliberately not on this list: the Nextcloud site
        # uses it for trusted_proxies, which is not a filter on who may connect.)
        for needle in ("sovran_lan_only", "remote_ip", "abort @"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, self.code)

    def test_the_bitcoin_sites_are_plain_proxies(self):
        for site, upstream in ((":3051", ":3050"), (":60847", ":60845")):
            with self.subTest(site=site):
                m = re.search(r"^" + re.escape(site) + r" \{\n(.*?)^\}$", self.code, re.S | re.M)
                self.assertIsNotNone(m, f"{site} site not found")
                directives = [l.strip() for l in m.group(1).splitlines() if l.strip()]
                self.assertEqual(directives, [f"reverse_proxy {upstream}", "encode gzip zstd"])

    def test_the_options_for_a_declared_prefix_are_gone(self):
        # Never needed once Caddy stops guessing: neither the option nor its
        # build-time assertion may linger half-wired.
        roles = _read("modules", "core", "roles.nix")
        self.assertNotIn("lanIPv6Prefixes", roles)
        self.assertNotIn("lanIPv6Prefixes", self.caddy)


class CaddyRunsWhereItIsNeeded(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.caddy = _read("modules", "core", "caddy.nix")
        cls.code = _without_comments(cls.caddy)

    def test_it_runs_for_domains_vhosts_or_the_bitcoin_uis(self):
        self.assertRegex(
            self.code,
            r"caddyEnabled\s*=\s*needsHttpsPorts\s*\|\|\s*extraVhosts\s*!=\s*\"\"\s*\|\|\s*servesRtl\s*;",
        )
        self.assertRegex(self.code, r"enable\s*=\s*caddyEnabled\s*;")

    def test_rtl_and_mempool_follow_their_services(self):
        self.assertRegex(self.code,
                         r"servesRtl\s*=\s*config\.sovran_systemsOS\.services\.bitcoin\s*;")
        self.assertRegex(
            self.code,
            r"servesMempool\s*=\s*servesRtl\s*&&\s*config\.sovran_systemsOS\.features\.mempool\s*;",
        )

    def test_each_site_exists_only_where_its_service_does(self):
        self.assertRegex(self.code, r"lib\.optionalString\s+servesRtl\s*''\s*\n+:3051 \{")
        self.assertRegex(self.code, r"lib\.optionalString\s+servesMempool\s*''\s*\n+:60847 \{")
        # ... and they are written into the Caddyfile from that one place
        self.assertIn("${bitcoinUiSites}", self.caddy)

    def test_rtl_and_mempool_still_proxy_to_their_loopback_ports(self):
        self.assertRegex(self.code, r":3051 \{[^}]*reverse_proxy :3050")
        self.assertRegex(self.code, r":60847 \{[^}]*reverse_proxy :60845")


class HubPortExposure(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.hub = _read("modules", "core", "sovran-hub.nix")
        cls.roles = _read("modules", "core", "roles.nix")

    def _firewall_value(self):
        m = re.search(
            r"^    networking\.firewall\.allowedTCPPorts =\s*(?P<value>.*?);\s*$",
            self.hub, re.S | re.M,
        )
        self.assertIsNotNone(m, "networking.firewall.allowedTCPPorts not found")
        return m.group("value")

    def test_the_hub_port_is_never_opened_unconditionally(self):
        # Regression: this used to be `allowedTCPPorts = [ 8937 60847 ]` with
        # no mkIf and no option gate, on every role, Desktop Only included.
        value = self._firewall_value()
        self.assertNotRegex(value, r"^\s*\[")
        self.assertRegex(value, r"lib\.optionals\s+cfg\.hub\.directPort\s+\[\s*8937\s*\]")

    def test_the_mempool_port_follows_mempool(self):
        self.assertRegex(
            self._firewall_value(),
            r"lib\.optionals\s+\(cfg\.services\.bitcoin\s*&&\s*cfg\.features\.mempool\)\s+\[\s*60847\s*\]",
        )

    def test_nothing_else_is_opened_here(self):
        ports = re.findall(r"\[\s*(\d+)\s*\]", self._firewall_value())
        self.assertEqual(sorted(ports), ["60847", "8937"])

    def test_direct_port_is_on_for_the_server_roles_and_off_for_desktop_only(self):
        m = re.search(r"directPort\s*=\s*lib\.mkOption\s*\{(.*?)\n      \};", self.roles, re.S)
        self.assertIsNotNone(m, "hub.directPort option not found")
        self.assertRegex(m.group(1), r"default\s*=\s*!config\.sovran_systemsOS\.roles\.desktop\s*;")

    def test_the_bind_is_ipv4_only_on_purpose(self):
        # IPv6 clients cannot reach the Hub, so the question of which IPv6
        # addresses are "local" never comes up. Widening the bind reopens it.
        self.assertIn('host="0.0.0.0"', self.hub)
        self.assertNotRegex(self.hub, r'host="::"')
        self.assertNotRegex(self.hub, r"both IPv4 and IPv6")


class TheHubIsDocumentedAtItsPort(unittest.TestCase):

    def test_no_document_still_sends_people_to_port_80(self):
        for name in (("README.md",), ("SECURITY.md",),
                     ("app", "sovran_systemsos_web", "templates", "index.html")):
            with self.subTest(file=name[-1]):
                text = _read(*name)
                self.assertNotRegex(text, r"sovransystemsos\.local(?!:8937)(?![a-z])",
                                    f"{name[-1]} sends people to sovransystemsos.local without :8937")

    def test_the_documents_name_the_port(self):
        self.assertIn("http://sovransystemsos.local:8937", _read("README.md"))
        self.assertIn("http://sovransystemsos.local:8937", _read("SECURITY.md"))
        self.assertIn("hub.directPort", _read("SECURITY.md"))


if __name__ == "__main__":
    unittest.main()
