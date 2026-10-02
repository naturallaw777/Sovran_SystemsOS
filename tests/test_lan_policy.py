"""Tests for the Hub's local-network policy and the middleware that enforces it.

The Hub runs as root, so it answers this computer and the local network and
nobody else: LanPolicy in security_helpers decides, LanOnlyMiddleware in
server.py enforces it before authentication is considered.

LanPolicy is exercised directly. The middleware is exercised over real HTTP
where the environment allows it; server.py cannot be imported from this repo
(it needs sovran_nwc from the Sovran_Bitcoin flake), so those tests skip rather
than fail, and the wiring is additionally asserted from source so it is always
checked.
"""

import logging
import os
import sys
import unittest

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_APP_PARENT = os.path.join(_REPO_ROOT, "app")
if _APP_PARENT not in sys.path:
    sys.path.insert(0, _APP_PARENT)

from sovran_systemsos_web.security_helpers import (  # noqa: E402
    LanPolicy,
    LAN_ONLY_IPV4,
    LAN_ONLY_IPV6,
)

_LOCAL = (
    "127.0.0.1", "10.0.0.1", "172.16.0.1", "172.31.255.254", "192.168.1.10",
    "100.64.0.1", "169.254.1.1",
    "::1", "fd12:3456::1", "fc00::1", "fe80::1",
)

_REMOTE = (
    "8.8.8.8", "1.1.1.1", "203.0.113.9", "9.255.255.255",
    "172.15.255.255", "172.32.0.1", "192.169.0.1", "100.63.255.255",
    # public IPv6 — every address in 2000::/3 is on the internet
    "2001:4860:4860::8888", "2606:4700:4700::1111",
    "2a00:1450:4001::1", "2400:cb00::1",
)


class LanPolicyMatrix(unittest.TestCase):

    def test_local_addresses_are_allowed(self):
        policy = LanPolicy()
        for address in _LOCAL:
            with self.subTest(local=address):
                self.assertTrue(policy.allows(address))

    def test_remote_addresses_are_refused(self):
        policy = LanPolicy()
        for address in _REMOTE:
            with self.subTest(remote=address):
                self.assertFalse(policy.allows(address))

    def test_ipv6_global_is_not_whitelisted(self):
        # 2000::/3 is the whole IPv6 global unicast space: allowing it would
        # let every public IPv6 address through.
        joined = " ".join(LAN_ONLY_IPV4 + LAN_ONLY_IPV6)
        self.assertNotIn("2000::/3", joined)
        for net in LanPolicy().networks:
            if net.version == 6:
                with self.subTest(range=str(net)):
                    self.assertTrue(str(net).startswith(("::1", "fc00", "fe80")),
                                    f"{net} is not a local-only IPv6 range")


class LanPolicyConfiguration(unittest.TestCase):

    def test_declared_networks_are_allowed(self):
        policy = LanPolicy(extra_networks=["203.0.113.0/28", "2001:db8:abcd::/48"])
        self.assertTrue(policy.allows("203.0.113.9"))
        self.assertFalse(policy.allows("203.0.113.16"))
        self.assertTrue(policy.allows("2001:db8:abcd::5"))
        self.assertFalse(policy.allows("2001:db8:abce::5"))

    def test_a_bare_address_is_a_single_host(self):
        policy = LanPolicy(extra_networks=["203.0.113.9"])
        self.assertTrue(policy.allows("203.0.113.9"))
        self.assertFalse(policy.allows("203.0.113.10"))

    def test_disabled_allows_everything(self):
        policy = LanPolicy(enabled=False)
        for address in _REMOTE:
            with self.subTest(remote=address):
                self.assertTrue(policy.allows(address))

    def test_malformed_network_does_not_widen_the_policy(self):
        # A typo must fail closed, not open the Hub to everything.
        policy = LanPolicy(extra_networks=["not-a-network", "203.0.113.0/28"])
        self.assertTrue(policy.allows("203.0.113.9"))
        self.assertFalse(policy.allows("8.8.8.8"))

    def test_a_zero_length_prefix_is_not_a_network(self):
        # 0.0.0.0/0 and ::/0 mean "everyone". That is lan_only = false and it
        # has to be asked for by name rather than arrive as a "network".
        policy = LanPolicy(extra_networks=["0.0.0.0/0", "::/0"])
        for address in _REMOTE:
            with self.subTest(remote=address):
                self.assertFalse(policy.allows(address))

    def test_missing_or_unparseable_client_is_refused(self):
        policy = LanPolicy()
        for address in (None, "", "testclient", "not-an-ip"):
            with self.subTest(client=address):
                self.assertFalse(policy.allows(address))

    def test_a_dual_stack_socket_does_not_hide_the_ipv4_client(self):
        # With an IPv6 listener, IPv4 clients arrive as ::ffff:a.b.c.d. The
        # address that counts is the IPv4 one inside it, both ways round.
        policy = LanPolicy()
        for address in ("::ffff:192.168.1.5", "::ffff:127.0.0.1", "::ffff:10.1.2.3"):
            with self.subTest(local=address):
                self.assertTrue(policy.allows(address))
        for address in ("::ffff:8.8.8.8", "::ffff:203.0.113.9"):
            with self.subTest(remote=address):
                self.assertFalse(policy.allows(address))


# ── Middleware ───────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI  # noqa: E402
    from fastapi.testclient import TestClient  # noqa: E402
    from sovran_systemsos_web.server import LanOnlyMiddleware  # noqa: E402
    HAVE_MIDDLEWARE = True
except Exception:  # fastapi / sovran_nwc unavailable from this repo
    HAVE_MIDDLEWARE = False


def _app_with(policy):
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    app.add_middleware(LanOnlyMiddleware, policy=policy)
    return app


@unittest.skipUnless(HAVE_MIDDLEWARE, "server.py is not importable here")
class LanOnlyMiddlewareOverHttp(unittest.TestCase):

    def _status(self, policy, client_ip):
        client = TestClient(_app_with(policy), client=(client_ip, 51234))
        return client.get("/ping").status_code

    def test_local_client_is_served(self):
        for address in ("127.0.0.1", "192.168.1.10", "10.0.0.1"):
            with self.subTest(local=address):
                self.assertEqual(self._status(LanPolicy(), address), 200)

    def test_remote_client_is_refused(self):
        for address in ("203.0.113.9", "8.8.8.8", "2001:4860:4860::8888"):
            with self.subTest(remote=address):
                self.assertEqual(self._status(LanPolicy(), address), 403)

    def test_refusal_says_nothing_about_the_configuration(self):
        # An outsider learns that the answer is no, not why or what to change.
        client = TestClient(_app_with(LanPolicy()), client=("203.0.113.9", 51234))
        response = client.get("/ping")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Not available from this network"})

    def test_disabled_policy_admits_remote_clients(self):
        self.assertEqual(self._status(LanPolicy(enabled=False), "203.0.113.9"), 200)

    def test_a_refused_address_is_logged_once(self):
        # The operator whose own device is refused needs to find out why; a
        # scanner must not be able to fill the journal.
        client = TestClient(_app_with(LanPolicy()), client=("203.0.113.9", 51234))
        with self.assertLogs("sovran_systemsos_web.server", level="WARNING") as seen:
            for _ in range(5):
                client.get("/ping")
        self.assertEqual(len(seen.records), 1)
        message = seen.records[0].getMessage()
        self.assertIn("203.0.113.9", message)
        self.assertIn("sovran_systemsOS.hub.extraLanNetworks", message)

    def test_a_served_client_is_not_logged(self):
        records = []

        class _Collect(logging.Handler):
            def emit(self, record):
                records.append(record)

        logger = logging.getLogger("sovran_systemsos_web.server")
        handler = _Collect(level=logging.WARNING)
        logger.addHandler(handler)
        try:
            client = TestClient(_app_with(LanPolicy()), client=("192.168.1.10", 51234))
            client.get("/ping")
        finally:
            logger.removeHandler(handler)
        self.assertEqual(records, [])


# ── Wiring, checked from source so it always runs ─────────────────────────────

def _server_source():
    with open(os.path.join(_APP_PARENT, "sovran_systemsos_web", "server.py"),
              encoding="utf-8") as f:
        return f.read()


class LanOnlyWiring(unittest.TestCase):

    def test_middleware_is_registered_outermost(self):
        # Starlette makes the last-registered middleware the outermost one, so
        # an off-network client is turned away before auth is considered.
        src = _server_source()
        auth = src.index("app.add_middleware(AuthMiddleware)")
        nocache = src.index("app.add_middleware(NoCacheMiddleware)")
        lan = src.index("app.add_middleware(LanOnlyMiddleware")
        self.assertLess(auth, nocache)
        self.assertLess(nocache, lan)

    def test_policy_comes_from_the_generated_config(self):
        src = _server_source()
        self.assertIn("LanPolicy(", src)
        self.assertIn('_hub_cfg.get("lan_only", True)', src)
        self.assertIn('_hub_cfg.get("lan_extra_networks")', src)


if __name__ == "__main__":
    unittest.main()
