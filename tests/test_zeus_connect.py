"""Regression tests for the Hub Zeus Connect QR.

The LND-only rewrite of modules/bitcoin/lndconnect.nix shipped a wrapper
that Zeus cannot use. These tests lock the contract the Hub QR depends on
without needing lnd / tor / qrencode at test time.
"""

import os
import re
import unittest

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _read(relpath: str) -> str:
    with open(os.path.join(_REPO_ROOT, relpath), encoding="utf-8") as fh:
        return fh.read()


class TestLndconnectWrapper(unittest.TestCase):
    """The system `lndconnect` wrapper must emit a Zeus-scannable URI."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read("modules/bitcoin/lndconnect.nix")

    def test_uses_official_lndconnect_flags(self):
        self.assertIn("--adminmacaroonpath=", self.src)
        self.assertIn("--configfile=/dev/null", self.src)
        self.assertIn("--nocert", self.src)
        self.assertIn("--tlscertpath=", self.src)

    def test_does_not_pass_unknown_short_flags(self):
        # The broken rewrite called `lndconnect --cert … --macaroon …`.
        # Those flags do not exist; Zeus then never got a valid URI.
        self.assertIsNone(re.search(r"--cert=", self.src))
        self.assertIsNone(re.search(r"--macaroon=", self.src))

    def test_uses_dedicated_lnd_rest_onion(self):
        self.assertIn("lnd-rest", self.src)
        self.assertIn('onionServices.lnd-rest', self.src)
        # Must not collide with the LND P2P onion named `lnd`.
        self.assertNotIn("onionServices.lnd =", self.src)
        self.assertNotIn('onionService = "${operatorName}/lnd"', self.src)

    def test_reads_onion_from_onion_addresses_dir(self):
        self.assertIn("onionAddresses.dataDir", self.src)
        self.assertNotIn("/var/lib/tor/onion/${onionService}/hostname", self.src)

    def test_omits_tls_cert_over_tor(self):
        # Onion host + embedded localhost cert = Zeus rejects the QR.
        self.assertIn('then "--nocert"', self.src)


class TestZeusConnectSetup(unittest.TestCase):
    """zeus-connect-setup must wait for the REST onion and validate the URI."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read("modules/wallet-autoconnect.nix")

    def test_waits_for_onion_addresses(self):
        self.assertIn("onion-addresses.service", self.src)

    def test_rejects_non_lndconnect_output(self):
        self.assertIn("^lndconnect://", self.src)
        self.assertIn("\\.onion", self.src)
        self.assertIn("macaroon=", self.src)

    def test_no_clightning_fallback(self):
        self.assertNotIn("lnconnect-clnrest", self.src)


class TestHubQrFallback(unittest.TestCase):
    """Hub QR encoding must not die on a payload that is too large for ECC H."""

    def test_qrencode_falls_back_to_lower_ecc(self):
        src = _read("app/sovran_systemsos_web/server.py")
        self.assertIn('for ecc in ("H", "Q", "L")', src)

    def test_qronly_does_not_hide_uri_when_qr_fails(self):
        src = _read("app/sovran_systemsos_web/server.py")
        self.assertIn("Don't hide the URI if we could not render a scannable QR.", src)

    def test_zeus_guide_mentions_use_tor(self):
        src = _read("app/sovran_systemsos_web/static/js/service-detail.js")
        self.assertIn("Use Tor", src)


if __name__ == "__main__":
    unittest.main()
