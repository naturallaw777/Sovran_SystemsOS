"""
Domain conflict and unique-hostname tests.

Tests cover:
1. Wallet Connections initial setup displays unique-hostname guidance.
2. Wallet Connections reconfiguration displays the same guidance.
3. The field example is lightning.yourdomain.com for Wallet Connections.
4. An unused hostname such as lightning.example.com is accepted.
5. Reusing a hostname assigned to Matrix, Nextcloud, WordPress, BTCPay Server,
   Vaultwarden, Haven, or Element Calling returns HTTP 409.
6. Comparison is case-insensitive.
7. A hostname with one trailing dot conflicts with the equivalent hostname without it.
8. Re-saving the existing lightning hostname for lightning remains allowed.
9. Invalid hostnames are rejected before mutation.
10. On conflict, the domain file remains unchanged.
11. On conflict, the DDNS script remains unchanged and is not executed.
12. Generic domain flows for unrelated services remain intact (matrix -> matrix, etc.).
13. JavaScript syntax checks pass for features.js and helpers.js.
"""

import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Minimal stubs so server.py can be imported without full FastAPI ──

def _install_web_stubs():
    if "fastapi" in sys.modules:
        return

    class _HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _FastAPI:
        def __init__(self, *a, **kw): pass
        def mount(self, *a, **kw): return None
        def add_middleware(self, *a, **kw): return None
        def __getattr__(self, _name):
            def _deco_factory(*a, **kw):
                def _deco(func): return func
                return _deco
            return _deco_factory

    class _BaseModel: pass

    class _JSONResponse:
        def __init__(self, content=None, status_code=200):
            self.content = content
            self.status_code = status_code
            self.body = json.dumps(content or {}).encode("utf-8")

    fastapi_mod = types.ModuleType("fastapi")
    fastapi_mod.FastAPI = _FastAPI
    fastapi_mod.HTTPException = _HTTPException
    sys.modules["fastapi"] = fastapi_mod

    resp_mod = types.ModuleType("fastapi.responses")
    resp_mod.HTMLResponse = object
    resp_mod.RedirectResponse = object
    resp_mod.JSONResponse = _JSONResponse
    sys.modules["fastapi.responses"] = resp_mod

    sys.modules["fastapi.staticfiles"] = types.ModuleType("fastapi.staticfiles")

    class _StaticFiles:
        def __init__(self, *args, **kwargs): pass

    sys.modules["fastapi.staticfiles"].StaticFiles = _StaticFiles

    class _Jinja2Templates:
        def __init__(self, *args, **kwargs): pass

    tmpl_mod = types.ModuleType("fastapi.templating")
    tmpl_mod.Jinja2Templates = _Jinja2Templates
    sys.modules["fastapi.templating"] = tmpl_mod

    req_mod = types.ModuleType("fastapi.requests")
    req_mod.Request = object
    sys.modules["fastapi.requests"] = req_mod

    pyd_mod = types.ModuleType("pydantic")
    pyd_mod.BaseModel = _BaseModel
    sys.modules["pydantic"] = pyd_mod

    stl_base = types.ModuleType("starlette.middleware.base")
    stl_base.BaseHTTPMiddleware = object
    sys.modules["starlette.middleware.base"] = stl_base
    stl_mw = types.ModuleType("starlette.middleware")
    sys.modules["starlette.middleware"] = stl_mw
    stl = types.ModuleType("starlette")
    sys.modules["starlette"] = stl


_install_web_stubs()

from sovran_systemsos_web import server  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────

def _make_req(domain_name, domain, ddns_url=""):
    """Build a DomainSetRequest-like object using the server's model."""
    req = object.__new__(server.DomainSetRequest)
    req.domain_name = domain_name
    req.domain = domain
    req.ddns_url = ddns_url
    return req


def _write_domain_file(domains_dir, key, value):
    path = os.path.join(domains_dir, key)
    with open(path, "w") as fh:
        fh.write(value)


# ── Unit tests for server helper functions ─────────────────────────

class NormalizeHostnameTests(unittest.TestCase):
    def test_trims_whitespace(self):
        self.assertEqual(server._normalize_hostname("  foo.example.com  "), "foo.example.com")

    def test_lowercases(self):
        self.assertEqual(server._normalize_hostname("FOO.Example.COM"), "foo.example.com")

    def test_removes_exactly_one_trailing_dot(self):
        self.assertEqual(server._normalize_hostname("foo.example.com."), "foo.example.com")

    def test_does_not_remove_two_trailing_dots(self):
        # Only one trailing dot is removed; two trailing dots leave one.
        self.assertEqual(server._normalize_hostname("foo.example.com.."), "foo.example.com.")

    def test_no_trailing_dot_unchanged(self):
        self.assertEqual(server._normalize_hostname("foo.example.com"), "foo.example.com")

    def test_strips_and_lowercases_with_trailing_dot(self):
        self.assertEqual(server._normalize_hostname("  Lightning.Example.COM.  "), "lightning.example.com")


class ValidateHostnameTests(unittest.TestCase):
    def test_valid_simple_domain(self):
        self.assertTrue(server._validate_hostname("foo.example.com"))

    def test_valid_subdomain(self):
        self.assertTrue(server._validate_hostname("lightning.yourdomain.com"))

    def test_valid_bare_hostname(self):
        self.assertTrue(server._validate_hostname("example"))

    def test_valid_with_hyphens(self):
        self.assertTrue(server._validate_hostname("my-host.example.com"))

    def test_invalid_empty(self):
        self.assertFalse(server._validate_hostname(""))

    def test_invalid_trailing_dot(self):
        # After normalization a trailing dot should have been removed.
        self.assertFalse(server._validate_hostname("foo.example.com."))

    def test_invalid_with_underscore(self):
        self.assertFalse(server._validate_hostname("foo_bar.example.com"))

    def test_invalid_leading_hyphen(self):
        self.assertFalse(server._validate_hostname("-foo.example.com"))

    def test_invalid_spaces(self):
        self.assertFalse(server._validate_hostname("foo example.com"))


class CheckDomainConflictTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_domains_dir = server.DOMAINS_DIR
        server.DOMAINS_DIR = self.tmpdir

    def tearDown(self):
        server.DOMAINS_DIR = self._orig_domains_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_conflict_when_no_other_files(self):
        result = server._check_domain_conflict("lightning", "lightning.example.com")
        self.assertIsNone(result)

    def test_conflict_when_matrix_has_same_hostname(self):
        _write_domain_file(self.tmpdir, "matrix", "shared.example.com")
        result = server._check_domain_conflict("lightning", "shared.example.com")
        self.assertEqual(result, "matrix")

    def test_conflict_when_nextcloud_has_same_hostname(self):
        _write_domain_file(self.tmpdir, "nextcloud", "shared.example.com")
        result = server._check_domain_conflict("lightning", "shared.example.com")
        self.assertEqual(result, "nextcloud")

    def test_conflict_when_wordpress_has_same_hostname(self):
        _write_domain_file(self.tmpdir, "wordpress", "shared.example.com")
        result = server._check_domain_conflict("lightning", "shared.example.com")
        self.assertEqual(result, "wordpress")

    def test_conflict_when_btcpayserver_has_same_hostname(self):
        _write_domain_file(self.tmpdir, "btcpayserver", "shared.example.com")
        result = server._check_domain_conflict("lightning", "shared.example.com")
        self.assertEqual(result, "btcpayserver")

    def test_conflict_when_vaultwarden_has_same_hostname(self):
        _write_domain_file(self.tmpdir, "vaultwarden", "shared.example.com")
        result = server._check_domain_conflict("lightning", "shared.example.com")
        self.assertEqual(result, "vaultwarden")

    def test_conflict_when_haven_has_same_hostname(self):
        _write_domain_file(self.tmpdir, "haven", "shared.example.com")
        result = server._check_domain_conflict("lightning", "shared.example.com")
        self.assertEqual(result, "haven")

    def test_conflict_when_element_calling_has_same_hostname(self):
        _write_domain_file(self.tmpdir, "element-calling", "shared.example.com")
        result = server._check_domain_conflict("lightning", "shared.example.com")
        self.assertEqual(result, "element-calling")

    def test_no_conflict_for_self(self):
        # Re-saving lightning's own existing hostname must be allowed.
        _write_domain_file(self.tmpdir, "lightning", "lightning.example.com")
        result = server._check_domain_conflict("lightning", "lightning.example.com")
        self.assertIsNone(result)

    def test_symmetric_conflict_matrix_reusing_lightning(self):
        # Saving matrix with lightning's existing hostname is also rejected.
        _write_domain_file(self.tmpdir, "lightning", "shared.example.com")
        result = server._check_domain_conflict("matrix", "shared.example.com")
        self.assertEqual(result, "lightning")

    def test_no_conflict_unrelated_services_without_lightning(self):
        # Two unrelated non-lightning services with the same hostname.
        # The rule only applies when lightning is involved.
        _write_domain_file(self.tmpdir, "matrix", "shared.example.com")
        result = server._check_domain_conflict("nextcloud", "shared.example.com")
        self.assertIsNone(result)


# ── API endpoint integration-style tests ──────────────────────────

import asyncio


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


class ApiDomainsSetConflictTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.njalla_dir = tempfile.mkdtemp()
        self.njalla_script = os.path.join(self.njalla_dir, "njalla.sh")
        self._orig_domains_dir = server.DOMAINS_DIR
        self._orig_njalla = server.NJALLA_SCRIPT
        server.DOMAINS_DIR = self.tmpdir
        server.NJALLA_SCRIPT = self.njalla_script

    def tearDown(self):
        server.DOMAINS_DIR = self._orig_domains_dir
        server.NJALLA_SCRIPT = self._orig_njalla
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        shutil.rmtree(self.njalla_dir, ignore_errors=True)

    # ── Test 4: unused hostname is accepted ──────────────────────────
    def test_unused_hostname_is_accepted(self):
        with patch.object(server, "_trigger_hosts_update"):
            result = _run(server.api_domains_set(_make_req("lightning", "lightning.example.com")))
        self.assertEqual(result.get("ok"), True)
        # Domain file should be written.
        with open(os.path.join(self.tmpdir, "lightning")) as fh:
            saved = fh.read()
        self.assertEqual(saved, "lightning.example.com")

    # ── Test 5: conflict with each managed service returns 409 ────────
    def _assert_conflict_409(self, target_key, conflicting_key, hostname):
        _write_domain_file(self.tmpdir, conflicting_key, hostname)
        with self.assertRaises(Exception) as ctx:
            _run(server.api_domains_set(_make_req(target_key, hostname)))
        exc = ctx.exception
        self.assertEqual(getattr(exc, "status_code", None), 409)
        detail = getattr(exc, "detail", {})
        self.assertEqual(detail.get("error"), "domain_conflict")
        self.assertEqual(detail.get("conflicting_domain_key"), conflicting_key)
        self.assertIn("message", detail)

    def test_conflict_with_matrix_returns_409(self):
        self._assert_conflict_409("lightning", "matrix", "shared.example.com")

    def test_conflict_with_nextcloud_returns_409(self):
        self._assert_conflict_409("lightning", "nextcloud", "shared.example.com")

    def test_conflict_with_wordpress_returns_409(self):
        self._assert_conflict_409("lightning", "wordpress", "shared.example.com")

    def test_conflict_with_btcpayserver_returns_409(self):
        self._assert_conflict_409("lightning", "btcpayserver", "shared.example.com")

    def test_conflict_with_vaultwarden_returns_409(self):
        self._assert_conflict_409("lightning", "vaultwarden", "shared.example.com")

    def test_conflict_with_haven_returns_409(self):
        self._assert_conflict_409("lightning", "haven", "shared.example.com")

    def test_conflict_with_element_calling_returns_409(self):
        self._assert_conflict_409("lightning", "element-calling", "shared.example.com")

    # ── Test 6: comparison is case-insensitive ───────────────────────
    def test_conflict_is_case_insensitive(self):
        _write_domain_file(self.tmpdir, "matrix", "Shared.Example.COM")
        with self.assertRaises(Exception) as ctx:
            _run(server.api_domains_set(_make_req("lightning", "shared.example.com")))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 409)

    def test_conflict_case_insensitive_reversed(self):
        _write_domain_file(self.tmpdir, "matrix", "shared.example.com")
        with self.assertRaises(Exception) as ctx:
            _run(server.api_domains_set(_make_req("lightning", "SHARED.EXAMPLE.COM")))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 409)

    # ── Test 7: trailing-dot normalization causes conflict ────────────
    def test_trailing_dot_conflicts_with_same_hostname(self):
        _write_domain_file(self.tmpdir, "matrix", "shared.example.com")
        with self.assertRaises(Exception) as ctx:
            _run(server.api_domains_set(_make_req("lightning", "shared.example.com.")))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 409)

    def test_stored_trailing_dot_conflicts_with_clean_submission(self):
        _write_domain_file(self.tmpdir, "matrix", "shared.example.com.")
        with self.assertRaises(Exception) as ctx:
            _run(server.api_domains_set(_make_req("lightning", "shared.example.com")))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 409)

    # ── Test 8: re-saving existing lightning hostname is allowed ──────
    def test_resave_existing_lightning_hostname_allowed(self):
        _write_domain_file(self.tmpdir, "lightning", "lightning.example.com")
        with patch.object(server, "_trigger_hosts_update"):
            result = _run(server.api_domains_set(_make_req("lightning", "lightning.example.com")))
        self.assertEqual(result.get("ok"), True)

    # ── Test 9: invalid hostname is rejected before mutation ──────────
    def test_invalid_hostname_rejected(self):
        with self.assertRaises(Exception) as ctx:
            _run(server.api_domains_set(_make_req("lightning", "not a hostname!")))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 400)

    def test_hostname_with_underscore_rejected(self):
        with self.assertRaises(Exception) as ctx:
            _run(server.api_domains_set(_make_req("lightning", "foo_bar.example.com")))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 400)

    # ── Test 10: on conflict, domain file remains unchanged ───────────
    def test_domain_file_unchanged_on_conflict(self):
        _write_domain_file(self.tmpdir, "matrix", "shared.example.com")
        lightning_path = os.path.join(self.tmpdir, "lightning")
        # Write a prior value.
        _write_domain_file(self.tmpdir, "lightning", "old.example.com")
        with self.assertRaises(Exception):
            _run(server.api_domains_set(_make_req("lightning", "shared.example.com")))
        # The lightning domain file must still contain the old value.
        with open(lightning_path) as fh:
            saved = fh.read()
        self.assertEqual(saved, "old.example.com")

    def test_domain_file_not_created_on_conflict_if_absent(self):
        _write_domain_file(self.tmpdir, "matrix", "shared.example.com")
        lightning_path = os.path.join(self.tmpdir, "lightning")
        self.assertFalse(os.path.exists(lightning_path))
        with self.assertRaises(Exception):
            _run(server.api_domains_set(_make_req("lightning", "shared.example.com")))
        self.assertFalse(os.path.exists(lightning_path))

    # ── Test 11: on conflict, DDNS script unchanged and not executed ──
    def test_njalla_script_not_written_on_conflict(self):
        _write_domain_file(self.tmpdir, "matrix", "shared.example.com")
        with self.assertRaises(Exception):
            _run(server.api_domains_set(
                _make_req("lightning", "shared.example.com",
                          ddns_url='curl "https://njal.la/update/?h=shared.example.com&k=key&auto"')
            ))
        self.assertFalse(os.path.exists(self.njalla_script))

    def test_njalla_script_not_executed_on_conflict(self):
        _write_domain_file(self.tmpdir, "matrix", "shared.example.com")
        with patch("subprocess.run") as mock_run, self.assertRaises(Exception):
            _run(server.api_domains_set(
                _make_req("lightning", "shared.example.com",
                          ddns_url='curl "https://njal.la/update/?h=shared.example.com&k=key&auto"')
            ))
        mock_run.assert_not_called()

    # ── Test 12: generic domain flows for unrelated services intact ───
    def test_matrix_save_without_lightning_succeeds(self):
        with patch.object(server, "_trigger_hosts_update"):
            result = _run(server.api_domains_set(_make_req("matrix", "matrix.example.com")))
        self.assertEqual(result.get("ok"), True)
        with open(os.path.join(self.tmpdir, "matrix")) as fh:
            saved = fh.read()
        self.assertEqual(saved, "matrix.example.com")

    def test_nextcloud_save_without_lightning_succeeds(self):
        with patch.object(server, "_trigger_hosts_update"):
            result = _run(server.api_domains_set(_make_req("nextcloud", "cloud.example.com")))
        self.assertEqual(result.get("ok"), True)

    def test_two_non_lightning_services_sharing_hostname_allowed(self):
        # The uniqueness rule is only enforced when lightning is involved.
        _write_domain_file(self.tmpdir, "matrix", "shared.example.com")
        with patch.object(server, "_trigger_hosts_update"):
            result = _run(server.api_domains_set(_make_req("nextcloud", "shared.example.com")))
        self.assertEqual(result.get("ok"), True)


# ── Test 13: JavaScript syntax checks ─────────────────────────────

class JsSyntaxTests(unittest.TestCase):
    def _js_files(self):
        static_js = Path(__file__).resolve().parents[1] / "sovran_systemsos_web" / "static" / "js"
        return sorted(static_js.glob("*.js"))

    def test_js_syntax_no_errors(self):
        for js_file in self._js_files():
            with self.subTest(file=js_file.name):
                result = subprocess.run(
                    ["node", "--check", str(js_file)],
                    capture_output=True, text=True
                )
                self.assertEqual(
                    result.returncode, 0,
                    msg=f"Syntax error in {js_file.name}:\n{result.stderr}"
                )


# ── UI guidance content tests (features.js) ───────────────────────

class FeaturesJsContentTests(unittest.TestCase):
    """Verify the features.js source contains the required Wallet Connections guidance."""

    def setUp(self):
        self.features_js = (
            Path(__file__).resolve().parents[1]
            / "sovran_systemsos_web" / "static" / "js" / "features.js"
        ).read_text(encoding="utf-8")

    # ── Test 1: initial setup displays unique-hostname guidance ───────
    def test_setup_modal_contains_nwc_warning(self):
        self.assertIn("Wallet Connections requires its own unique hostname", self.features_js)

    # ── Test 2: reconfiguration displays the same guidance ────────────
    def test_reconfig_modal_contains_nwc_warning(self):
        # The warning text must appear in both openDomainSetupModal and
        # openDomainReconfigureModal — two occurrences minimum.
        count = self.features_js.count("Wallet Connections requires its own unique hostname")
        self.assertGreaterEqual(count, 2, "Warning must appear in both setup and reconfigure modals")

    # ── Test 3: field example is lightning.yourdomain.com ────────────
    def test_lightning_placeholder_is_present(self):
        self.assertIn("lightning.yourdomain.com", self.features_js)

    # ── Warning references correct services ───────────────────────────
    def test_warning_mentions_matrix(self):
        self.assertIn("Matrix", self.features_js)

    def test_warning_mentions_nextcloud(self):
        self.assertIn("Nextcloud", self.features_js)

    def test_warning_mentions_btcpay_server(self):
        self.assertIn("BTCPay Server", self.features_js)

    def test_warning_mentions_vaultwarden(self):
        self.assertIn("Vaultwarden", self.features_js)

    def test_warning_mentions_haven(self):
        self.assertIn("Haven", self.features_js)

    def test_warning_mentions_wordpress(self):
        self.assertIn("WordPress", self.features_js)

    # ── isWalletConnections guard targets correct identifiers ─────────
    def test_nwc_wallets_id_check_present(self):
        self.assertIn('feat.id === "nwc-wallets"', self.features_js)

    def test_lightning_domain_name_check_present(self):
        self.assertIn('feat.domain_name === "lightning"', self.features_js)

    # ── Error surfacing ───────────────────────────────────────────────
    def test_error_message_surfaced_in_setup_modal(self):
        # The catch block must use err.message rather than hard-coded string.
        self.assertIn("err.message", self.features_js)


if __name__ == "__main__":
    unittest.main()
