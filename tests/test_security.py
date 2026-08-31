"""Security regression tests for Sovran Hub security helpers.

Tests exercise the exact production implementations — no helpers are
redefined or simulated here.  Every test calls the deployed code.

Tests must never:
  - reboot, rebuild, or alter real SSH keys
  - access the network
  - write to system paths
"""

import base64
import json
import os
import sys
import tempfile
import time
import unittest

# Add the app package to the path so we can import without the full FastAPI tree.
_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_APP_PARENT = os.path.join(_REPO_ROOT, "app")
if _APP_PARENT not in sys.path:
    sys.path.insert(0, _APP_PARENT)

from sovran_systemsos_web.security_helpers import (  # noqa: E402
    _nix_escape,
    NPUB_RE,
    _validate_npub,
    _validate_ddns_url,
    _validate_ssh_pubkey,
    _DDNS_ALLOWED_HOSTNAMES,
    _bech32_decode,
    load_session_store,
    save_session_store,
)
from sovran_systemsos_web import support_ops  # noqa: E402


# ---------------------------------------------------------------------------
# Nix string escaping
# ---------------------------------------------------------------------------

class TestNixEscape(unittest.TestCase):
    """_nix_escape must prevent injection into Nix string literals."""

    def test_double_quotes_escaped(self):
        self.assertEqual(_nix_escape('"hello"'), '\\"hello\\"')

    def test_backslash_escaped(self):
        self.assertEqual(_nix_escape("a\\b"), "a\\\\b")

    def test_nix_interpolation_escaped(self):
        self.assertEqual(_nix_escape("${evil}"), "\\${evil}")

    def test_newline_escaped(self):
        self.assertEqual(_nix_escape("a\nb"), "a\\nb")

    def test_carriage_return_escaped(self):
        self.assertEqual(_nix_escape("a\rb"), "a\\rb")

    def test_tab_escaped(self):
        self.assertEqual(_nix_escape("a\tb"), "a\\tb")

    def test_semicolons_unchanged(self):
        self.assertEqual(_nix_escape("a;b"), "a;b")

    def test_valid_timezone(self):
        self.assertEqual(_nix_escape("America/New_York"), "America/New_York")

    def test_injection_payload_quotes_and_interpolation(self):
        payload = '"; import <nixpkgs/nixos/tests/keymap.nix> { ${builtins.readFile "/etc/shadow"} }'
        result = _nix_escape(payload)
        import re as _re
        self.assertIsNone(_re.search(r'(?<!\\)\$\{', result))

    def test_npub_injection(self):
        payload = 'npub1aaa"; extraUsers.evil.isNormalUser = true; #'
        result = _nix_escape(payload)
        self.assertNotIn('"', result.replace('\\"', ""))


# ---------------------------------------------------------------------------
# Nostr npub validation — regex pre-filter
# ---------------------------------------------------------------------------

class TestNpubValidationRegex(unittest.TestCase):
    """NPUB_RE must enforce the npub1 + 58 lowercase bech32 shape."""

    # 58 bech32 chars after "npub1"
    VALID_SHAPE = "npub1" + "q" * 58

    def test_valid_shape_accepted(self):
        self.assertIsNotNone(NPUB_RE.fullmatch(self.VALID_SHAPE))

    def test_wrong_prefix_rejected(self):
        self.assertIsNone(NPUB_RE.fullmatch("nsec1" + "q" * 58))

    def test_too_short_rejected(self):
        self.assertIsNone(NPUB_RE.fullmatch("npub1" + "q" * 57))

    def test_too_long_rejected(self):
        self.assertIsNone(NPUB_RE.fullmatch("npub1" + "q" * 59))

    def test_uppercase_rejected(self):
        self.assertIsNone(NPUB_RE.fullmatch("NPUB1" + "q" * 58))

    def test_injection_quote_rejected(self):
        self.assertIsNone(NPUB_RE.fullmatch('npub1aaa"; extraUsers.evil.isNormalUser = true; #'))

    def test_injection_interpolation_rejected(self):
        self.assertIsNone(NPUB_RE.fullmatch("npub1" + "${" + "q" * 52))


# ---------------------------------------------------------------------------
# Nostr npub validation — full bech32
# ---------------------------------------------------------------------------

class TestNpubBech32Validation(unittest.TestCase):
    """_validate_npub must verify the full bech32 checksum and payload length."""

    BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

    def _make_npub(self, payload_bytes: bytes) -> str | None:
        """Build a syntactically valid npub from raw 32-byte payload."""
        from sovran_systemsos_web.security_helpers import (
            _bech32_hrp_expand,
            _bech32_polymod,
            _bech32_create_checksum,
        )

        def _convertbits(data, frombits, tobits, pad=True):
            acc, bits, ret, maxv = 0, 0, [], (1 << tobits) - 1
            for value in data:
                acc = ((acc << frombits) | value)
                bits += frombits
                while bits >= tobits:
                    bits -= tobits
                    ret.append((acc >> bits) & maxv)
            if pad and bits:
                ret.append((acc << (tobits - bits)) & maxv)
            return ret

        hrp = "npub"
        data5 = _convertbits(list(payload_bytes), 8, 5)
        checksum = _bech32_create_checksum(hrp, data5)
        full = data5 + checksum
        return hrp + "1" + "".join(self.BECH32_CHARSET[d] for d in full)

    def test_valid_npub_passes_bech32(self):
        npub = self._make_npub(bytes(32))
        self.assertIsNotNone(npub)
        self.assertTrue(_validate_npub(npub))

    def test_bech32_decode_returns_32_bytes(self):
        npub = self._make_npub(b'\x01' * 32)
        result = _bech32_decode(npub)
        self.assertIsNotNone(result)
        hrp, payload = result
        self.assertEqual(hrp, "npub")
        self.assertEqual(len(payload), 32)

    def test_corrupted_checksum_rejected(self):
        npub = self._make_npub(bytes(32))
        # Flip last character in the data part
        corrupted = npub[:-1] + ("q" if npub[-1] != "q" else "p")
        self.assertFalse(_validate_npub(corrupted))

    def test_mixed_case_rejected(self):
        npub = self._make_npub(bytes(32))
        mixed = npub[:10].upper() + npub[10:]
        self.assertFalse(_validate_npub(mixed))

    def test_wrong_hrp_rejected(self):
        self.assertFalse(_validate_npub("nsec1" + "q" * 58))

    def test_synthetic_all_q_rejected_by_checksum(self):
        self.assertFalse(_validate_npub("npub1" + "q" * 58))


# ---------------------------------------------------------------------------
# DDNS URL validation
# ---------------------------------------------------------------------------

class TestDdnsUrlValidation(unittest.TestCase):
    """_validate_ddns_url must enforce all security constraints."""

    # VALID_URL has no ${IP}: callers must substitute before validation.
    VALID_URL = "https://njal.la/update/?h=test.example.com&k=TOKEN&a=1.2.3.4"

    def test_valid_njalla_url_accepted(self):
        self.assertEqual(_validate_ddns_url(self.VALID_URL), self.VALID_URL)

    def test_www_njalla_accepted(self):
        url = "https://www.njal.la/update/?h=test&k=TOKEN"
        self.assertEqual(_validate_ddns_url(url), url)

    def test_http_scheme_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("http://njal.la/update/?k=TOKEN")

    def test_ftp_scheme_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("ftp://njal.la/update/?k=TOKEN")

    def test_credentials_in_url_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("******njal.la/update/?k=TOKEN")

    def test_fragment_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://njal.la/update/?k=TOKEN#frag")

    def test_raw_ip_host_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://1.2.3.4/update/?k=TOKEN")

    def test_non_standard_port_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://njal.la:8443/update/?k=TOKEN")

    def test_control_character_newline_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://njal.la/update/?k=TOKEN\n")

    def test_control_character_null_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://njal.la/update/?k=\x00TOKEN")

    def test_percent_encoded_null_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://njal.la/update/?k=TOKEN%00")

    def test_localhost_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://localhost/update/?k=TOKEN")

    def test_127_0_0_1_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://127.0.0.1/update/?k=TOKEN")

    def test_arbitrary_public_hostname_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://example.com/update/?k=TOKEN")

    def test_attacker_host_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://attacker.njal.la/update/?k=TOKEN")

    def test_metadata_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://169.254.169.254/update/?k=TOKEN")

    def test_empty_url_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("")

    def test_too_long_rejected(self):
        long_url = "https://njal.la/update/?" + "k=" + "x" * 3000
        with self.assertRaises(ValueError):
            _validate_ddns_url(long_url)

    def test_allowed_hostnames_set(self):
        self.assertIn("njal.la", _DDNS_ALLOWED_HOSTNAMES)
        self.assertIn("www.njal.la", _DDNS_ALLOWED_HOSTNAMES)
        self.assertNotIn("attacker.njal.la", _DDNS_ALLOWED_HOSTNAMES)
        self.assertNotIn("localhost", _DDNS_ALLOWED_HOSTNAMES)

    def test_dollar_expression_rejected(self):
        """$ in a validated URL is rejected; callers must substitute ${IP} first."""
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://njal.la/update/?h=test&k=TOKEN&a=${IP}")

    def test_wrong_path_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ddns_url("https://njal.la/api/?k=TOKEN")

    def test_exact_update_path_accepted(self):
        url = "https://njal.la/update/?h=host.example.com&k=TOKEN"
        self.assertEqual(_validate_ddns_url(url), url)


# ---------------------------------------------------------------------------
# SSH public-key validation
# ---------------------------------------------------------------------------

class TestSshPubkeyValidation(unittest.TestCase):
    """_validate_ssh_pubkey must accept only valid single-line OpenSSH public keys."""

    VALID_ED25519 = (
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl user@host"
    )

    def test_valid_ed25519_accepted(self):
        result = _validate_ssh_pubkey(self.VALID_ED25519)
        self.assertEqual(result, self.VALID_ED25519)

    def test_unsupported_algorithm_rsa_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey("ssh-rsa AAAAB3NzaC1yc2EAAAA user@host")

    def test_dss_algorithm_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey("ssh-dss AAAAB3NzaC1kc3MAAA user@host")

    def test_multiline_injection_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey(self.VALID_ED25519 + "\necho pwned")

    def test_options_prefix_not_accepted(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey('command="ls" ' + self.VALID_ED25519)

    def test_empty_key_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey("")

    def test_control_character_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey("ssh-ed25519 AAAA\x00 user@host")

    def test_malformed_base64_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey("ssh-ed25519 not-valid-base64!!! user@host")

    def test_too_short_payload_rejected(self):
        short_b64 = base64.b64encode(b"\x00" * 10).decode()
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey(f"ssh-ed25519 {short_b64} user@host")

    def test_missing_key_body_rejected(self):
        with self.assertRaises(ValueError):
            _validate_ssh_pubkey("ssh-ed25519")


# ---------------------------------------------------------------------------
# Auth-exempt paths
# ---------------------------------------------------------------------------

class TestAuthExemptPaths(unittest.TestCase):
    """/api/reboot and status endpoints must not be in the auth-exempt set."""

    def _get_exempt_paths(self):
        import re
        src = open(
            os.path.join(_REPO_ROOT, "app", "sovran_systemsos_web", "server.py")
        ).read()
        m = re.search(r"_AUTH_EXEMPT_PATHS\s*=\s*\{([^}]*)\}", src)
        self.assertIsNotNone(m, "_AUTH_EXEMPT_PATHS not found in server.py")
        return {p.strip().strip('"') for p in m.group(1).split(",") if p.strip().strip('"')}

    def test_reboot_not_exempt(self):
        self.assertNotIn("/api/reboot", self._get_exempt_paths())

    def test_updates_status_not_exempt(self):
        self.assertNotIn("/api/updates/status", self._get_exempt_paths())

    def test_rebuild_status_not_exempt(self):
        self.assertNotIn("/api/rebuild/status", self._get_exempt_paths())

    def test_login_still_exempt(self):
        self.assertIn("/api/login", self._get_exempt_paths())

    def test_ping_still_exempt(self):
        self.assertIn("/api/ping", self._get_exempt_paths())


class TestFrontendAuthRecovery(unittest.TestCase):
    """Expired browser sessions must not leave the Hub polling forever."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(
            _REPO_ROOT, "app", "sovran_systemsos_web", "static", "js", "helpers.js"
        )
        with open(path, encoding="utf-8") as f:
            cls.helpers = f.read()

    def test_api_fetch_redirects_unauthorized_response_to_login(self):
        self.assertRegex(self.helpers, r"res\.status\s*===\s*401")
        self.assertIn('window.location.replace("/login")', self.helpers)

    def test_unauthorized_response_does_not_use_local_auto_login(self):
        # Remote clients must still authenticate with the Hub password.
        self.assertNotIn('window.location.replace("/auto-login")', self.helpers)


class TestManualLogoutPersistence(unittest.TestCase):
    """Explicit logout must take precedence over desktop auto-login."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(_REPO_ROOT, "app", "sovran_systemsos_web", "server.py")
        with open(path, encoding="utf-8") as f:
            cls.server = f.read()

    def _between(self, start, end):
        return self.server.split(start, 1)[1].split(end, 1)[0]

    def test_auto_login_honors_manual_logout_cookie(self):
        route = self._between(
            '@app.get("/auto-login")',
            "class LoginRequest",
        )
        self.assertIn("request.cookies.get(MANUAL_LOGOUT_COOKIE_NAME)", route)
        self.assertIn('RedirectResponse(url="/login"', route)

    def test_logout_sets_persistent_manual_logout_cookie(self):
        route = self._between(
            '@app.post("/api/logout")',
            "def _get_sovran_version",
        )
        self.assertIn("key=MANUAL_LOGOUT_COOKIE_NAME", route)
        self.assertIn("max_age=MANUAL_LOGOUT_MAX_AGE", route)
        self.assertIn("httponly=True", route)

    def test_password_login_clears_manual_logout_cookie(self):
        route = self._between(
            '@app.post("/api/login")',
            '@app.post("/api/logout")',
        )
        self.assertIn(
            "response.delete_cookie(key=MANUAL_LOGOUT_COOKIE_NAME)", route
        )


class TestHubBrowserProfilePersistence(unittest.TestCase):
    """The desktop launcher must keep a persistent browser profile.

    The hub_manual_logout marker (and the session cookie) are stored in this
    profile. If the launcher used an ephemeral /tmp profile that it deleted on
    exit, closing and reopening the Hub window would wipe the marker and
    /auto-login would silently log the user back in without a password.
    """

    @classmethod
    def setUpClass(cls):
        path = os.path.join(
            _REPO_ROOT, "modules", "core", "sovran-hub.nix"
        )
        with open(path, encoding="utf-8") as f:
            cls.wrapper = f.read()

    def test_profile_is_not_under_tmp(self):
        # The profile must live in a persistent per-user location, not /tmp.
        self.assertNotIn("/tmp/sovran-hub-brave", self.wrapper)

    def test_profile_is_not_deleted_on_exit(self):
        # There must be no trap that removes the user-data-dir on exit.
        self.assertNotRegex(self.wrapper, r"rm\s+-rf\s+.*HUB_DATA")
        self.assertNotIn("trap '", self.wrapper)

    def test_profile_is_persistent_per_user_location(self):
        self.assertIn("sovran-hub-browser", self.wrapper)
        # It should honour XDG_STATE_HOME (standard, persistent per-user dir).
        self.assertIn("XDG_STATE_HOME", self.wrapper)

    def test_launcher_still_uses_user_data_dir(self):
        self.assertIn("--user-data-dir=", self.wrapper)


# ---------------------------------------------------------------------------
# Persistent session store
# ---------------------------------------------------------------------------

class TestSessionStore(unittest.TestCase):
    """Sessions must persist across Hub restarts so rebuild/update polling
    keeps working after nixos-rebuild switch restarts the Hub service."""

    def _store_path(self, tmpdir, name="hub-sessions.json"):
        return os.path.join(tmpdir, name)

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._store_path(tmpdir)
            future = time.time() + 3600
            sessions = {"token-a": future, "token-b": future + 10}
            self.assertTrue(save_session_store(path, sessions))
            self.assertEqual(load_session_store(path), sessions)

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(load_session_store(self._store_path(tmpdir)), {})

    def test_malformed_json_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._store_path(tmpdir)
            with open(path, "w") as f:
                f.write("{not json")
            self.assertEqual(load_session_store(path), {})

    def test_non_dict_json_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._store_path(tmpdir)
            with open(path, "w") as f:
                json.dump(["token"], f)
            self.assertEqual(load_session_store(path), {})

    def test_expired_sessions_discarded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._store_path(tmpdir)
            now = time.time()
            save_session_store(path, {"alive": now + 3600, "dead": now - 1})
            loaded = load_session_store(path)
            self.assertIn("alive", loaded)
            self.assertNotIn("dead", loaded)

    def test_invalid_entries_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._store_path(tmpdir)
            now = time.time()
            with open(path, "w") as f:
                json.dump({
                    "good": now + 3600,
                    "": now + 3600,              # empty token
                    "bool-expiry": True,         # bool is not a valid expiry
                    "str-expiry": "soon",        # non-numeric expiry
                    "none-expiry": None,
                }, f)
            loaded = load_session_store(path)
            self.assertEqual(list(loaded.keys()), ["good"])

    def test_file_mode_is_0600(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._store_path(tmpdir)
            save_session_store(path, {"token": time.time() + 60})
            mode = os.stat(path).st_mode & 0o777
            self.assertEqual(mode, 0o600)

    def test_save_overwrites_existing_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._store_path(tmpdir)
            future = time.time() + 3600
            save_session_store(path, {"old": future})
            save_session_store(path, {"new": future})
            self.assertEqual(load_session_store(path), {"new": future})

    def test_empty_store_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._store_path(tmpdir)
            self.assertTrue(save_session_store(path, {}))
            self.assertEqual(load_session_store(path), {})

    def test_no_leftover_temp_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._store_path(tmpdir)
            save_session_store(path, {"token": time.time() + 60})
            leftovers = [n for n in os.listdir(tmpdir) if n.startswith(".hub_sessions_tmp")]
            self.assertEqual(leftovers, [])


# ---------------------------------------------------------------------------
# tech-support.nix validation
# ---------------------------------------------------------------------------

class TestTechSupportSudoRules(unittest.TestCase):
    """tech-support.nix must not grant broad privileges."""

    def _get_nix_content(self):
        path = os.path.join(_REPO_ROOT, "modules", "core", "tech-support.nix")
        with open(path) as f:
            return f.read()

    def test_no_nano_custom_nix(self):
        self.assertNotIn("nano /etc/nixos/custom.nix", self._get_nix_content())

    def test_no_nano_configuration_nix(self):
        self.assertNotIn("nano /etc/nixos/configuration.nix", self._get_nix_content())

    def test_no_unrestricted_nixos_rebuild(self):
        self.assertNotIn("nixos-rebuild switch", self._get_nix_content())

    def test_no_wildcard_systemctl_restart(self):
        self.assertNotIn("systemctl restart *", self._get_nix_content())

    def test_journalctl_wildcard_removed(self):
        """The bare 'journalctl *' sudo rule must be gone."""
        content = self._get_nix_content()
        self.assertNotIn('"/run/current-system/sw/bin/journalctl *"', content)
        self.assertNotIn("journalctl *", content.replace("journal-helper", ""))

    def test_journal_helper_referenced(self):
        """The restricted journal helper must be referenced instead."""
        content = self._get_nix_content()
        self.assertIn("sovran-journal-helper", content)

    def test_sovran_hub_web_service_referenced(self):
        """tech-support.nix must reference sovran-hub-web.service, not the nonexistent sovran-hub.service."""
        content = self._get_nix_content()
        self.assertIn("sovran-hub-web.service", content)
        self.assertNotIn('"sovran-hub.service"', content)


# ---------------------------------------------------------------------------
# Journal helper — unit allowlist validation
# ---------------------------------------------------------------------------

class TestJournalHelper(unittest.TestCase):
    """The restricted journal helper must enforce the explicit unit allowlist."""

    def _run_helper(self, args):
        """Run the helper script and return (returncode, stderr)."""
        import subprocess
        helper = os.path.join(_REPO_ROOT, "modules", "core", "sovran-journal-helper.py")
        result = subprocess.run(
            [sys.executable, helper] + args,
            capture_output=True, text=True,
        )
        return result.returncode, result.stderr

    # ── Allowlisted units ──
    def test_sovran_hub_web_accepted(self):
        rc, stderr = self._run_helper(["--unit", "sovran-hub-web.service"])
        self.assertNotIn("rejected", stderr)

    def test_caddy_accepted(self):
        rc, stderr = self._run_helper(["--unit", "caddy.service"])
        self.assertNotIn("rejected", stderr)

    def test_bitcoind_accepted(self):
        rc, stderr = self._run_helper(["--unit", "bitcoind.service"])
        self.assertNotIn("rejected", stderr)

    def test_lnd_accepted(self):
        rc, stderr = self._run_helper(["--unit", "lnd.service"])
        self.assertNotIn("rejected", stderr)

    # ── Rejected units ──
    def test_unapproved_service_rejected(self):
        rc, stderr = self._run_helper(["--unit", "sshd.service"])
        self.assertNotEqual(rc, 0)
        self.assertIn("rejected", stderr)

    def test_old_sovran_hub_service_rejected(self):
        """The old nonexistent sovran-hub.service must now be rejected."""
        rc, stderr = self._run_helper(["--unit", "sovran-hub.service"])
        self.assertNotEqual(rc, 0)
        self.assertIn("rejected", stderr)

    def test_directory_flag_rejected(self):
        rc, stderr = self._run_helper(["--directory", "/var/log"])
        self.assertNotEqual(rc, 0)
        self.assertIn("rejected", stderr)

    def test_arbitrary_path_rejected(self):
        rc, stderr = self._run_helper(["/etc/passwd"])
        self.assertNotEqual(rc, 0)
        self.assertIn("rejected", stderr)

    def test_file_flag_rejected(self):
        rc, stderr = self._run_helper(["--file", "/var/log/journal/foo"])
        self.assertNotEqual(rc, 0)
        self.assertIn("rejected", stderr)

    def test_no_args_rejected(self):
        """Whole-journal queries (no --unit) must be rejected."""
        rc, stderr = self._run_helper([])
        self.assertNotEqual(rc, 0)
        # Should mention --unit requirement
        self.assertIn("unit", stderr.lower())

    def test_lines_only_no_unit_rejected(self):
        """--lines without --unit is a whole-journal query and must be rejected."""
        rc, stderr = self._run_helper(["--lines", "50"])
        self.assertNotEqual(rc, 0)

    def test_lines_flag_accepted(self):
        rc, stderr = self._run_helper(["--unit", "caddy.service", "--lines", "50"])
        self.assertNotIn("rejected", stderr)

    def test_lines_too_large_rejected(self):
        rc, stderr = self._run_helper(["--lines", "99999"])
        self.assertNotEqual(rc, 0)
        self.assertIn("rejected", stderr)

    def test_negative_lines_rejected(self):
        rc, stderr = self._run_helper(["--lines", "-1"])
        self.assertNotEqual(rc, 0)

    def test_since_with_valid_date_accepted(self):
        rc, stderr = self._run_helper(["--unit", "caddy.service", "--since", "2024-01-01"])
        self.assertNotIn("rejected", stderr)

    def test_since_with_path_rejected(self):
        rc, stderr = self._run_helper(["--since", "/etc/passwd"])
        self.assertNotEqual(rc, 0)
        self.assertIn("rejected", stderr)

    def test_output_short_accepted(self):
        rc, stderr = self._run_helper(["--unit", "caddy.service", "--output", "short"])
        self.assertNotIn("rejected", stderr)

    def test_output_arbitrary_rejected(self):
        rc, stderr = self._run_helper(["--output", "export --to /tmp/out"])
        self.assertNotEqual(rc, 0)
        self.assertIn("rejected", stderr)

    def test_invalid_unit_name_rejected(self):
        rc, stderr = self._run_helper(["--unit", "../../../etc/passwd"])
        self.assertNotEqual(rc, 0)
        self.assertIn("rejected", stderr)

    def test_unit_without_suffix_rejected(self):
        rc, stderr = self._run_helper(["--unit", "caddy"])
        self.assertNotEqual(rc, 0)
        self.assertIn("rejected", stderr)


# ---------------------------------------------------------------------------
# Legacy Njalla migration — production-backed tests
# ---------------------------------------------------------------------------

class TestNjallaLegacyMigration(unittest.TestCase):
    """migrate_legacy_njalla_script must not execute or preserve malicious content.

    All tests call the exact production implementation from support_ops with
    temporary files; no logic is duplicated here.
    """

    def _run_migration(self, script_content: str) -> tuple[list[str], bool]:
        """Run the production migration against temp files, return (urls, script_archived)."""
        captured_urls: list[str] = []
        saved = [False]

        def _load():
            return []

        def _save(urls):
            captured_urls.extend(urls)
            saved[0] = True

        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = os.path.join(tmpdir, "njalla.sh")
            with open(script_path, "w") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)

            support_ops.migrate_legacy_njalla_script(
                script_path,
                _validate_ddns_url,
                _save,
                _load,
            )

            archived = oct(os.stat(script_path).st_mode)[-3:] == "000"
        return captured_urls, archived

    def test_valid_unquoted_curl_line_extracted(self):
        script = (
            "#!/usr/bin/env bash\n"
            "IP=$(dig @resolver4.opendns.com myip.opendns.com +short -4)\n"
            "curl --silent https://njal.la/update/?h=test.example.com&k=TOKEN&a=${IP}\n"
        )
        urls, archived = self._run_migration(script)
        self.assertEqual(len(urls), 1)
        self.assertIn("njal.la", urls[0])
        self.assertTrue(archived, "script should be archived after successful migration")

    def test_valid_quoted_curl_line_extracted(self):
        """Historical quoted form: curl \"https://njal.la/...\" must be parsed."""
        script = (
            "#!/usr/bin/env bash\n"
            'curl "https://njal.la/update/?h=test.example.com&k=TOKEN&a=${IP}"\n'
        )
        urls, archived = self._run_migration(script)
        self.assertEqual(len(urls), 1, "quoted URL must be extracted")
        self.assertIn("njal.la", urls[0])

    def test_command_injection_not_extracted(self):
        script = "curl https://njal.la/update/?k=TOKEN; rm -rf /\n"
        urls, _ = self._run_migration(script)
        self.assertEqual(urls, [])

    def test_backtick_injection_not_extracted(self):
        script = "curl https://njal.la/update/?k=`cat /etc/passwd`\n"
        urls, _ = self._run_migration(script)
        self.assertEqual(urls, [])

    def test_pipe_injection_not_extracted(self):
        script = "curl https://njal.la/update/?k=TOKEN | curl https://attacker.com\n"
        urls, _ = self._run_migration(script)
        self.assertEqual(urls, [])

    def test_dollar_injection_not_extracted(self):
        script = "curl https://njal.la/update/?k=$(evil_command)\n"
        urls, _ = self._run_migration(script)
        self.assertEqual(urls, [])

    def test_non_njalla_url_not_extracted(self):
        script = "curl https://attacker.example.com/update/?k=TOKEN\n"
        urls, _ = self._run_migration(script)
        self.assertEqual(urls, [])

    def test_http_url_not_extracted(self):
        script = "curl http://njal.la/update/?k=TOKEN\n"
        urls, _ = self._run_migration(script)
        self.assertEqual(urls, [])

    def test_semicolons_in_url_not_extracted(self):
        script = "curl https://njal.la/update/?k=TOKEN;echo evil\n"
        urls, _ = self._run_migration(script)
        self.assertEqual(urls, [])

    def test_newline_injection_not_extracted(self):
        script = 'curl "https://njal.la/update/?k=TOKEN\necho evil"\n'
        urls, _ = self._run_migration(script)
        self.assertEqual(urls, [])

    def test_malformed_quotes_not_extracted(self):
        """Half-open quote must not match."""
        script = 'curl "https://njal.la/update/?k=TOKEN\n'
        urls, _ = self._run_migration(script)
        self.assertEqual(urls, [])

    def test_failed_persistence_leaves_script_untouched(self):
        """If save_fn raises, the script must NOT be archived."""
        def _fail_save(urls):
            raise OSError("disk full")

        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = os.path.join(tmpdir, "njalla.sh")
            script_content = (
                "#!/usr/bin/env bash\n"
                "curl https://njal.la/update/?h=test&k=TOKEN\n"
            )
            with open(script_path, "w") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)

            support_ops.migrate_legacy_njalla_script(
                script_path,
                _validate_ddns_url,
                _fail_save,
                lambda: [],
            )

            # Script must still be executable (not archived)
            mode = oct(os.stat(script_path).st_mode)[-3:]
            self.assertNotEqual(mode, "000", "script must not be archived when persistence fails")


# ---------------------------------------------------------------------------
# Legacy root key removal — production-backed tests
# ---------------------------------------------------------------------------

class TestLegacyRootKeyRemoval(unittest.TestCase):
    """remove_legacy_root_key must remove only the exact historical key blob.

    All tests call the exact production implementation from support_ops with
    temporary files; no simulation is used.
    """

    TARGET_BLOB = support_ops.LEGACY_ROOT_KEY_BLOB

    def _do_removal(self, file_content: str) -> tuple[bool, str]:
        """Run production key removal, return (changed, result_content)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_keys = os.path.join(tmpdir, "authorized_keys")
            with open(auth_keys, "w") as f:
                f.write(file_content)
            changed = support_ops.remove_legacy_root_key(auth_keys, self.TARGET_BLOB)
            with open(auth_keys) as f:
                result = f.read()
        return changed, result

    def test_exact_historical_key_removed(self):
        """The exact historical key must be removed regardless of comment."""
        lines = (
            "ssh-ed25519 AAAA admin@host\n"
            f"ssh-ed25519 {self.TARGET_BLOB} free@nixos\n"
            "ssh-ed25519 CCCC another@host\n"
        )
        changed, result = self._do_removal(lines)
        self.assertTrue(changed)
        self.assertNotIn(self.TARGET_BLOB, result)
        self.assertIn("admin@host", result)
        self.assertIn("another@host", result)

    def test_same_comment_different_blob_preserved(self):
        """A key with 'free@nixos' comment but different blob must NOT be removed."""
        lines = (
            "ssh-ed25519 DIFFERENTBLOB free@nixos\n"
        )
        changed, result = self._do_removal(lines)
        self.assertFalse(changed)
        self.assertIn("DIFFERENTBLOB", result)

    def test_legacy_key_with_different_comment_removed(self):
        """The exact blob with any comment (or no comment) must be removed."""
        lines = f"ssh-ed25519 {self.TARGET_BLOB} some-other-comment\n"
        changed, result = self._do_removal(lines)
        self.assertTrue(changed)
        self.assertNotIn(self.TARGET_BLOB, result)

    def test_unrelated_keys_preserved(self):
        lines = "ssh-ed25519 AAAA admin@host\nssh-ed25519 CCCC another@host\n"
        changed, result = self._do_removal(lines)
        self.assertFalse(changed)
        self.assertEqual(result, lines)

    def test_empty_file_unchanged(self):
        changed, result = self._do_removal("")
        self.assertFalse(changed)
        self.assertEqual(result, "")

    def test_comment_line_preserved(self):
        lines = "# authorized keys\nssh-ed25519 AAAA admin@host\n"
        changed, result = self._do_removal(lines)
        self.assertFalse(changed)
        self.assertEqual(result, lines)

    def test_missing_file_returns_false(self):
        result = support_ops.remove_legacy_root_key("/nonexistent/path", self.TARGET_BLOB)
        self.assertFalse(result)

    def test_audit_callback_called(self):
        events = []
        lines = f"ssh-ed25519 {self.TARGET_BLOB} free@nixos\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_keys = os.path.join(tmpdir, "authorized_keys")
            with open(auth_keys, "w") as f:
                f.write(lines)
            support_ops.remove_legacy_root_key(
                auth_keys, self.TARGET_BLOB,
                audit_fn=lambda event, details="": events.append(event),
            )
        self.assertIn("LEGACY_ROOT_KEY_REMOVED", events)


# ---------------------------------------------------------------------------
# Support session expiry — production-backed tests
# ---------------------------------------------------------------------------

class TestSupportSessionExpiration(unittest.TestCase):
    """expire_if_stale must enforce expiry and the session_id guard.

    All tests call the exact production implementation from support_ops with
    temporary files and injectable clock/disable functions.
    """

    def _write_session(self, tmpdir, **fields) -> str:
        status_file = os.path.join(tmpdir, "support-session-status")
        with open(status_file, "w") as f:
            json.dump(fields, f)
        return status_file

    def test_future_expiry_not_expired(self):
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = self._write_session(tmpdir, expires_at=time.time() + 3600)
            disabled = [False]
            result = support_ops.expire_if_stale(
                sf,
                clock_fn=time.time,
                disable_fn=lambda: [disabled.__setitem__(0, True), True][1],
            )
        self.assertFalse(result)
        self.assertFalse(disabled[0])

    def test_past_expiry_expired(self):
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = self._write_session(tmpdir, expires_at=time.time() - 1)
            disabled = [False]
            result = support_ops.expire_if_stale(
                sf,
                clock_fn=time.time,
                disable_fn=lambda: [disabled.__setitem__(0, True), True][1],
            )
        self.assertTrue(result)
        self.assertTrue(disabled[0])

    def test_no_expiry_recent_session_not_expired(self):
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = self._write_session(tmpdir, enabled_at=time.time() - 100)
            result = support_ops.expire_if_stale(sf, clock_fn=time.time)
        self.assertFalse(result)

    def test_no_expiry_old_session_expired(self):
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = self._write_session(tmpdir, enabled_at=time.time() - 86401)
            disabled = [False]
            result = support_ops.expire_if_stale(
                sf,
                clock_fn=time.time,
                disable_fn=lambda: [disabled.__setitem__(0, True), True][1],
            )
        self.assertTrue(result)
        self.assertTrue(disabled[0])

    def test_session_id_guard_matching_expires(self):
        """Timer with matching session_id must expire the session."""
        import time
        sid = "test-session-id"
        exp = time.time() - 1
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = self._write_session(tmpdir, session_id=sid, expires_at=exp)
            disabled = [False]
            result = support_ops.expire_if_stale(
                sf,
                clock_fn=time.time,
                disable_fn=lambda: [disabled.__setitem__(0, True), True][1],
                session_id=sid,
                expected_expiry=exp,
            )
        self.assertTrue(result)
        self.assertTrue(disabled[0])

    def test_stale_timer_does_not_revoke_replacement_session(self):
        """A timer for an old session must not revoke a newer replacement session."""
        import time
        old_sid = "old-session"
        new_sid = "new-session"
        exp = time.time() - 1
        with tempfile.TemporaryDirectory() as tmpdir:
            # Current session has the NEW session id
            sf = self._write_session(tmpdir, session_id=new_sid, expires_at=exp)
            disabled = [False]
            # Timer fires with OLD session id
            result = support_ops.expire_if_stale(
                sf,
                clock_fn=time.time,
                disable_fn=lambda: [disabled.__setitem__(0, True), True][1],
                session_id=old_sid,  # stale — doesn't match stored new_sid
                expected_expiry=exp,
            )
        self.assertFalse(result, "stale timer must not revoke replacement session")
        self.assertFalse(disabled[0])

    def test_stale_expiry_mismatch_does_not_revoke(self):
        """A timer with mismatched expected_expiry must not revoke."""
        import time
        sid = "same-sid"
        exp = time.time() - 1
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = self._write_session(tmpdir, session_id=sid, expires_at=exp + 999)
            disabled = [False]
            result = support_ops.expire_if_stale(
                sf,
                clock_fn=time.time,
                disable_fn=lambda: [disabled.__setitem__(0, True), True][1],
                session_id=sid,
                expected_expiry=exp,  # differs from stored exp+999
            )
        self.assertFalse(result)
        self.assertFalse(disabled[0])

    def test_startup_reconciliation_with_live_session(self):
        """On startup, a live session must not be expired."""
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = self._write_session(tmpdir, expires_at=time.time() + 3600, session_id="live")
            disabled = [False]
            result = support_ops.expire_if_stale(
                sf,
                clock_fn=time.time,
                disable_fn=lambda: [disabled.__setitem__(0, True), True][1],
            )
        self.assertFalse(result)
        self.assertFalse(disabled[0])

    def test_audit_callback_receives_support_expired_event(self):
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = self._write_session(tmpdir, expires_at=time.time() - 1)
            events = []
            support_ops.expire_if_stale(
                sf,
                clock_fn=time.time,
                audit_fn=lambda event, details="": events.append(event),
            )
        self.assertIn("SUPPORT_EXPIRED", events)

    def test_zero_enabled_at_not_expired(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sf = self._write_session(tmpdir, enabled_at=0)
            result = support_ops.expire_if_stale(sf)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# Cron composition
# ---------------------------------------------------------------------------

class TestCronComposition(unittest.TestCase):
    """configuration.nix must not disable cron (rsnapshot and other module jobs depend on it)."""

    def _get_config_content(self):
        path = os.path.join(_REPO_ROOT, "configuration.nix")
        with open(path) as f:
            return f.read()

    def test_cron_not_disabled(self):
        """services.cron.enable = false must not appear in configuration.nix."""
        self.assertNotIn("services.cron.enable = false", self._get_config_content())

    def test_sovran_ddns_update_timer_in_njalla(self):
        """The periodic Njalla updater must be the systemd timer, not a cron job."""
        path = os.path.join(_REPO_ROOT, "modules", "core", "njalla.nix")
        with open(path) as f:
            content = f.read()
        self.assertIn("sovran-ddns-update", content)
        self.assertNotIn("services.cron", content)


if __name__ == "__main__":
    unittest.main()
