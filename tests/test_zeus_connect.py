"""Regression tests for the Hub Zeus Connect QR.

The Zeus Connect setup service (modules/wallet-autoconnect.nix) and the Hub QR
encoding are tested here.  The lndconnect wrapper itself is now part of the
Sovran_Bitcoin flake — its contract tests live in that repository.
"""

import os
import re
import unittest

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _read(relpath: str) -> str:
    with open(os.path.join(_REPO_ROOT, relpath), encoding="utf-8") as fh:
        return fh.read()


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
