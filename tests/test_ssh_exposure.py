"""Guards for when port 22 is open in the firewall.

sshd-localhost.nix gives every role "ssh root@localhost" by listening on
127.0.0.1 only. NixOS opens sshd's ports in the firewall by default whether or
not sshd listens on them, which left port 22 open on every role, Desktop Only
included, with nothing behind it. The roles that really publish SSH open it
explicitly, so the default has to stay off.

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
    return "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))


class LocalhostSshdDoesNotOpenThePort(unittest.TestCase):

    def test_the_firewall_is_not_opened_by_default(self):
        code = _without_comments(_read("modules", "core", "sshd-localhost.nix"))
        self.assertRegex(code, r"openFirewall\s*=\s*lib\.mkDefault\s+false\s*;")

    def test_it_still_listens_on_loopback_only(self):
        code = _without_comments(_read("modules", "core", "sshd-localhost.nix"))
        self.assertRegex(code, r'addr\s*=\s*"127\.0\.0\.1"')
        self.assertNotIn("0.0.0.0", code)


class PublishedSshOpensItsOwnPort(unittest.TestCase):
    """Turning the default off must not close the roles that want SSH open."""

    def test_the_sshd_feature_opens_22_and_only_when_enabled(self):
        src = _without_comments(_read("modules", "sshd.nix"))
        self.assertRegex(src, r"lib\.mkIf\s+config\.sovran_systemsOS\.features\.sshd")
        self.assertRegex(src, r"networking\.firewall\.allowedTCPPorts\s*=\s*\[\s*22\s*\]")

    def test_remote_deploy_opens_22_and_only_when_enabled(self):
        src = _without_comments(_read("modules", "core", "remote-deploy.nix"))
        self.assertRegex(src, r"lib\.mkIf\s+cfg\.enable")
        self.assertRegex(src, r"networking\.firewall\.allowedTCPPorts\s*=\s*\[\s*22\s*\]")


class DesktopOnlyDocumentsWhatItOpens(unittest.TestCase):

    def test_security_policy_says_desktop_opens_no_tcp_port(self):
        text = " ".join(_read("SECURITY.md").split())  # the file is line-wrapped
        self.assertIn("opens no TCP port", text)
        self.assertIn("UDP 5353", text)


if __name__ == "__main__":
    unittest.main()
