"""Guards for when port 22 is open in the firewall.

sshd-localhost.nix gives Server + Desktop and Bitcoin Node "ssh root@localhost"
by listening on 127.0.0.1 only. NixOS opens sshd's ports in the firewall by
default whether or not sshd listens on them, which left port 22 open with
nothing behind it. The roles that really publish SSH open it explicitly, so the
default has to stay off. Desktop Only now ships no sshd at all.

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


class DesktopOnlyHasNoSshDaemon(unittest.TestCase):

    def test_loopback_sshd_is_gated_off(self):
        code = _without_comments(_read("modules", "core", "sshd-localhost.nix"))
        self.assertRegex(
            code, r"lib\.mkIf\s+\(!config\.sovran_systemsOS\.roles\.desktop\)")

    def test_factory_ssh_key_bootstrap_is_gated_off(self):
        code = _without_comments(_read("modules", "core", "ssh-bootstrap.nix"))
        self.assertRegex(
            code, r"lib\.mkIf\s+\(userExists\s+&&\s+!config\.sovran_systemsOS\.roles\.desktop\)")

    def test_remote_deploy_is_rejected_on_desktop(self):
        code = _without_comments(_read("modules", "core", "remote-deploy.nix"))
        self.assertRegex(
            code, r"assertion\s*=\s*!config\.sovran_systemsOS\.roles\.desktop")
        self.assertRegex(
            code, r"lib\.mkIf\s+\(!config\.sovran_systemsOS\.roles\.desktop\)")


class DesktopOnlyDocumentsWhatItOpens(unittest.TestCase):

    def test_security_policy_says_desktop_opens_no_tcp_port(self):
        text = " ".join(_read("SECURITY.md").split())  # the file is line-wrapped
        self.assertIn("opens no TCP port", text)
        self.assertIn("UDP 5353", text)

    def test_security_policy_says_desktop_has_no_ssh_daemon(self):
        text = " ".join(_read("SECURITY.md").split()).replace("**", "").replace("`", "")
        self.assertIn("Desktop Only ships no SSH at all", text)
        self.assertIn("no sshd daemon (not even loopback)", text)


if __name__ == "__main__":
    unittest.main()
