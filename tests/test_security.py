"""Security regression tests for Sovran Hub server helpers.

Tests cover the concrete payload classes described in the security review:
  - DDNS URL validation (injection payloads)
  - Nix string escaping (injection into generated Nix source)
  - Nostr npub validation (Nix injection via nostr_npub)
  - SSH public-key validation (support-key handling)
  - /api/reboot auth-exemption removal

These tests use only the Python standard library so they run without installing
the full application dependency tree.  The helper functions are replicated from
server.py to allow isolated unit testing.
"""

import base64
import ipaddress
import re
import sys
import types
import unittest
import urllib.parse

# ---------------------------------------------------------------------------
# Replicate the helpers under test so we can test them without importing the
# full FastAPI application (which is not available in CI).
# ---------------------------------------------------------------------------

# ── _nix_escape ──────────────────────────────────────────────────────────────

def _nix_escape(value: str) -> str:
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("\n", "\\n")
    value = value.replace("\r", "\\r")
    value = value.replace("\t", "\\t")
    value = value.replace("${", "\\${")
    return value


# ── NPUB_RE ───────────────────────────────────────────────────────────────────

NPUB_RE = re.compile(r"^npub1[023456789acdefghjklmnpqrstuvwxyz]{58}$")


# ── _validate_ddns_url ────────────────────────────────────────────────────────

_DDNS_URL_MAX_LEN = 2048
_DDNS_CONTROL_RE  = re.compile(r"[\x00-\x1f\x7f]")


def _validate_ddns_url(url: str) -> str:
    if not url:
        raise ValueError("DDNS URL must not be empty")
    if len(url) > _DDNS_URL_MAX_LEN:
        raise ValueError("DDNS URL exceeds maximum length")
    if _DDNS_CONTROL_RE.search(url):
        raise ValueError("DDNS URL contains control characters")
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        raise ValueError("DDNS URL could not be parsed")
    if parsed.scheme.lower() != "https":
        raise ValueError("DDNS URL must use the https scheme")
    if parsed.username or parsed.password:
        raise ValueError("DDNS URL must not contain credentials")
    if parsed.fragment:
        raise ValueError("DDNS URL must not contain a fragment")
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("DDNS URL must contain a hostname")
    try:
        ipaddress.ip_address(hostname)
        raise ValueError("DDNS URL hostname must not be a raw IP address")
    except ValueError as exc:
        if "raw IP" in str(exc):
            raise
    return url


# ── _validate_ssh_pubkey ──────────────────────────────────────────────────────

_SSH_PUBKEY_ALGORITHMS = frozenset([
    "ssh-ed25519",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
])


def _validate_ssh_pubkey(key: str) -> str:
    key = key.strip()
    if not key:
        raise ValueError("SSH public key must not be empty")
    if _DDNS_CONTROL_RE.search(key):
        raise ValueError("SSH public key contains control characters")
    if "\n" in key or "\r" in key:
        raise ValueError("SSH public key must be a single line")
    parts = key.split()
    if len(parts) < 2:
        raise ValueError("SSH public key is malformed")
    algo, b64 = parts[0], parts[1]
    if algo not in _SSH_PUBKEY_ALGORITHMS:
        raise ValueError(f"Unsupported SSH key algorithm: {algo!r}")
    try:
        decoded = base64.b64decode(b64, validate=True)
    except Exception:
        raise ValueError("SSH public key payload is not valid base64")
    if len(decoded) < 20:
        raise ValueError("SSH public key payload is too short")
    return key


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestNixEscape(unittest.TestCase):
    """_nix_escape must prevent injection into Nix string literals."""

    def test_double_quotes_escaped(self):
        self.assertEqual(_nix_escape('"hello"'), '\\"hello\\"')

    def test_backslash_escaped(self):
        self.assertEqual(_nix_escape("a\\b"), "a\\\\b")

    def test_nix_interpolation_escaped(self):
        result = _nix_escape("${pkgs.bash}")
        # Nix interpolation is prevented by the leading backslash; the raw
        # result must contain "\\${" (backslash then ${), not bare "${".
        self.assertIn("\\${", result)
        # The result must not start with "${" (unescaped)
        self.assertFalse(result.startswith("${"))

    def test_newline_escaped(self):
        result = _nix_escape("foo\nbar")
        self.assertNotIn("\n", result)
        self.assertIn("\\n", result)

    def test_carriage_return_escaped(self):
        result = _nix_escape("foo\rbar")
        self.assertNotIn("\r", result)

    def test_tab_escaped(self):
        result = _nix_escape("foo\tbar")
        self.assertNotIn("\t", result)

    def test_semicolons_unchanged(self):
        # Semicolons are safe inside Nix string literals
        self.assertEqual(_nix_escape("a;b"), "a;b")

    def test_valid_timezone(self):
        # Typical timezone value must pass through unchanged
        self.assertEqual(_nix_escape("Europe/London"), "Europe/London")

    def test_injection_payload_quotes_and_interpolation(self):
        payload = '"; import <nixpkgs/nixos/tests/keymap.nix> { ${builtins.readFile "/etc/shadow"} }'
        result = _nix_escape(payload)
        # Unescaped double-quotes must not appear in the result
        self.assertNotIn('"', result.replace('\\"', ""))
        # All ${...} sequences must be preceded by backslash
        self.assertIn("\\${", result)
        # No bare ${ that is not preceded by backslash
        import re as _re
        self.assertIsNone(_re.search(r'(?<!\\)\$\{', result))

    def test_npub_injection(self):
        payload = 'npub1aaa"; extraUsers.evil.isNormalUser = true; #'
        result = _nix_escape(payload)
        # The result should not contain unescaped quotes
        self.assertNotIn('"', result.replace('\\"', ""))


class TestNpubValidation(unittest.TestCase):
    """NPUB_RE must accept valid npubs and reject injection payloads."""

    # A real npub (58 bech32 chars after "npub1")
    VALID_NPUB = "npub1" + "q" * 58  # synthetic but format-correct

    def test_valid_npub_accepted(self):
        self.assertIsNotNone(NPUB_RE.fullmatch(self.VALID_NPUB))

    def test_wrong_prefix_rejected(self):
        self.assertIsNone(NPUB_RE.fullmatch("nsec1" + "q" * 58))

    def test_too_short_rejected(self):
        self.assertIsNone(NPUB_RE.fullmatch("npub1" + "q" * 57))

    def test_too_long_rejected(self):
        self.assertIsNone(NPUB_RE.fullmatch("npub1" + "q" * 59))

    def test_injection_with_quote_rejected(self):
        payload = 'npub1aaa"; extraUsers.evil.isNormalUser = true; #'
        self.assertIsNone(NPUB_RE.fullmatch(payload))

    def test_injection_with_interpolation_rejected(self):
        payload = "npub1" + "${" + "q" * 52
        self.assertIsNone(NPUB_RE.fullmatch(payload))

    def test_injection_with_newline_rejected(self):
        payload = "npub1" + "q" * 30 + "\n" + "q" * 28
        self.assertIsNone(NPUB_RE.fullmatch(payload))

    def test_injection_with_semicolon_rejected(self):
        payload = "npub1" + "q" * 30 + ";" + "q" * 27
        self.assertIsNone(NPUB_RE.fullmatch(payload))

    def test_injection_with_backslash_rejected(self):
        payload = "npub1" + "q" * 30 + "\\" + "q" * 27
        self.assertIsNone(NPUB_RE.fullmatch(payload))

    def test_uppercase_letters_rejected(self):
        # bech32 is lower-case only (uppercase I, O, B, 1 excluded)
        self.assertIsNone(NPUB_RE.fullmatch("npub1" + "Q" * 58))

    def test_empty_rejected(self):
        self.assertIsNone(NPUB_RE.fullmatch(""))


class TestDdnsUrlValidation(unittest.TestCase):
    """_validate_ddns_url must reject injection payloads."""

    VALID_URL = "https://njal.la/update/?h=test.example.com&k=TOKEN&a=${IP}"

    def test_valid_url_accepted(self):
        result = _validate_ddns_url(self.VALID_URL)
        self.assertEqual(result, self.VALID_URL)

    def test_http_scheme_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("http://njal.la/update/?h=test&k=TOKEN")

    def test_ftp_scheme_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("ftp://njal.la/update/?h=test&k=TOKEN")

    def test_credentials_in_url_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("******njal.la/update/?k=TOKEN")

    def test_fragment_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://njal.la/update/?k=TOKEN#fragment")

    def test_raw_ip_host_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://1.2.3.4/update/?k=TOKEN")

    def test_control_character_newline_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://njal.la/update/?k=TOKEN\nmalicious")

    def test_control_character_null_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://njal.la/update/?k=TOKEN\x00evil")

    def test_semicolon_in_query_accepted(self):
        # Semicolons are valid in query strings
        result = _validate_ddns_url("https://njal.la/update/?h=test&k=abc;def")
        self.assertIsNotNone(result)

    def test_quote_injection_in_url_accepted_as_url(self):
        # A quote character is valid URL data (percent-encoded in practice),
        # but even unencoded it is safe because _validate_ddns_url validates
        # structure not characters.  The important thing is the URL passes
        # through to curl as a single argument — shell injection is impossible.
        url = 'https://njal.la/update/?k=abc"def'
        result = _validate_ddns_url(url)
        self.assertEqual(result, url)

    def test_backtick_in_url_accepted_as_url(self):
        url = "https://njal.la/update/?k=abc`id`"
        result = _validate_ddns_url(url)
        self.assertEqual(result, url)

    def test_dollar_sign_in_url_accepted_as_url(self):
        url = "https://njal.la/update/?k=$(cat /etc/passwd)"
        result = _validate_ddns_url(url)
        self.assertEqual(result, url)

    def test_empty_url_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("")

    def test_too_long_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://njal.la/?" + "x" * 2050)


class TestSshPubkeyValidation(unittest.TestCase):
    """_validate_ssh_pubkey must accept valid keys and reject injections."""

    # Minimal valid ed25519 key (32-byte payload, base64-encoded)
    _PAYLOAD = base64.b64encode(b"\x00" * 64).decode()
    VALID_KEY = f"ssh-ed25519 {_PAYLOAD} user@host"

    def test_valid_ed25519_accepted(self):
        result = _validate_ssh_pubkey(self.VALID_KEY)
        self.assertEqual(result, self.VALID_KEY)

    def test_unsupported_algorithm_rejected(self):
        payload = base64.b64encode(b"\x00" * 40).decode()
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey(f"ssh-rsa {payload} user@host")

    def test_dss_algorithm_rejected(self):
        payload = base64.b64encode(b"\x00" * 40).decode()
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey(f"ssh-dss {payload} user@host")

    def test_multiline_injection_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey(f"{self.VALID_KEY}\nssh-ed25519 AAAA second-key")

    def test_options_prefix_not_accepted(self):
        # OpenSSH key options ("command=..." etc.) should be rejected as
        # the algorithm will not match.
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey(f'command="evil" {self.VALID_KEY}')

    def test_empty_key_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey("")

    def test_control_character_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey(f"ssh-ed25519 {self._PAYLOAD}\x00 user@host")

    def test_malformed_base64_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey("ssh-ed25519 NOT!VALID!BASE64 user@host")

    def test_too_short_payload_rejected(self):
        short = base64.b64encode(b"\x00" * 5).decode()
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey(f"ssh-ed25519 {short} user@host")


class TestAuthExemptPaths(unittest.TestCase):
    """/api/reboot and status endpoints must not be in the auth-exempt set."""

    def _get_exempt_paths(self):
        """Extract _AUTH_EXEMPT_PATHS from server.py without importing it."""
        import re
        src = open(
            __file__.replace("tests/test_security.py", "app/sovran_systemsos_web/server.py")
        ).read()
        m = re.search(r"_AUTH_EXEMPT_PATHS\s*=\s*\{([^}]*)\}", src)
        self.assertIsNotNone(m, "_AUTH_EXEMPT_PATHS not found in server.py")
        return {p.strip().strip('"') for p in m.group(1).split(",") if p.strip().strip('"')}

    def test_reboot_not_exempt(self):
        exempt = self._get_exempt_paths()
        self.assertNotIn("/api/reboot", exempt)

    def test_updates_status_not_exempt(self):
        exempt = self._get_exempt_paths()
        self.assertNotIn("/api/updates/status", exempt)

    def test_rebuild_status_not_exempt(self):
        exempt = self._get_exempt_paths()
        self.assertNotIn("/api/rebuild/status", exempt)

    def test_login_still_exempt(self):
        exempt = self._get_exempt_paths()
        self.assertIn("/api/login", exempt)

    def test_ping_still_exempt(self):
        exempt = self._get_exempt_paths()
        self.assertIn("/api/ping", exempt)


class TestTechSupportSudoRules(unittest.TestCase):
    """tech-support.nix must not grant Nix-edit or unrestricted rebuild/systemctl."""

    def _get_nix_content(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "modules", "core", "tech-support.nix"
        )
        with open(os.path.normpath(path)) as f:
            return f.read()

    def test_no_nano_custom_nix(self):
        content = self._get_nix_content()
        self.assertNotIn("nano /etc/nixos/custom.nix", content)

    def test_no_nano_configuration_nix(self):
        content = self._get_nix_content()
        self.assertNotIn("nano /etc/nixos/configuration.nix", content)

    def test_no_unrestricted_nixos_rebuild(self):
        content = self._get_nix_content()
        self.assertNotIn("nixos-rebuild switch", content)

    def test_no_wildcard_systemctl_restart(self):
        content = self._get_nix_content()
        self.assertNotIn("systemctl restart *", content)


if __name__ == "__main__":
    unittest.main()
