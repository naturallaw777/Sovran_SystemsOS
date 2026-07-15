"""Tests for server-local loopback diagnostics and domain validation.

Covers:
- Domain value validation and injection prevention.
- Loopback address detection (IPv4 and IPv6).
- _resolve_all_addresses returning multiple addresses.
- _check_domain_health_fast with loopback resolution.
- _evaluate_domain_checklist with loopback override — no false dns_mismatch.
- _evaluate_domain_checklist with genuine DNS mismatch — still reports error.
- api_services health stays "healthy" when domain resolves to loopback.
- api_services health stays "needs_attention" when DNS is genuinely wrong.
- api_domains_check returns "local_override" for loopback-resolved domains.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Minimal stubs so server.py can be imported without the full FastAPI stack.
# ---------------------------------------------------------------------------

def _install_web_stubs():
    if "fastapi" in sys.modules:
        return

    class _HTTPException(Exception):
        def __init__(self, status_code=None, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def mount(self, *args, **kwargs):
            return None

        def add_middleware(self, *args, **kwargs):
            return None

        def __getattr__(self, _name):
            def _decorator_factory(*args, **kwargs):
                def _decorator(func):
                    return func
                return _decorator
            return _decorator_factory

    class _BaseModel:
        pass

    class _StaticFiles:
        def __init__(self, *args, **kwargs):
            pass

    class _Jinja2Templates:
        def __init__(self, *args, **kwargs):
            pass

    class _BaseHTTPMiddleware:
        pass

    fastapi_module = types.ModuleType("fastapi")
    fastapi_module.FastAPI = _FastAPI
    fastapi_module.HTTPException = _HTTPException
    sys.modules["fastapi"] = fastapi_module

    responses_module = types.ModuleType("fastapi.responses")
    responses_module.HTMLResponse = object
    responses_module.JSONResponse = object
    responses_module.RedirectResponse = object
    sys.modules["fastapi.responses"] = responses_module

    staticfiles_module = types.ModuleType("fastapi.staticfiles")
    staticfiles_module.StaticFiles = _StaticFiles
    sys.modules["fastapi.staticfiles"] = staticfiles_module

    templating_module = types.ModuleType("fastapi.templating")
    templating_module.Jinja2Templates = _Jinja2Templates
    sys.modules["fastapi.templating"] = templating_module

    requests_module = types.ModuleType("fastapi.requests")
    requests_module.Request = object
    sys.modules["fastapi.requests"] = requests_module

    pydantic_module = types.ModuleType("pydantic")
    pydantic_module.BaseModel = _BaseModel
    sys.modules["pydantic"] = pydantic_module

    starlette_base_module = types.ModuleType("starlette.middleware.base")
    starlette_base_module.BaseHTTPMiddleware = _BaseHTTPMiddleware
    sys.modules["starlette.middleware.base"] = starlette_base_module

    starlette_middleware_module = types.ModuleType("starlette.middleware")
    starlette_middleware_module.base = starlette_base_module
    sys.modules["starlette.middleware"] = starlette_middleware_module

    starlette_module = types.ModuleType("starlette")
    starlette_module.middleware = starlette_middleware_module
    sys.modules["starlette"] = starlette_module


_install_web_stubs()
from sovran_systemsos_web import server  # noqa: E402


# ===========================================================================
# Domain value validation
# ===========================================================================

class TestValidateDomainValue(unittest.TestCase):
    """_validate_domain_value must reject anything that could corrupt /etc/hosts."""

    def _v(self, value: str) -> bool:
        return server._validate_domain_value(value)

    # -- Valid values --------------------------------------------------------

    def test_simple_domain_valid(self):
        self.assertTrue(self._v("cloud.example.com"))

    def test_subdomain_valid(self):
        self.assertTrue(self._v("matrix.home.example.org"))

    def test_single_label_with_tld_valid(self):
        self.assertTrue(self._v("example.com"))

    def test_hyphen_in_domain_valid(self):
        self.assertTrue(self._v("my-nextcloud.example.com"))

    # -- Injection / malformed values ----------------------------------------

    def test_empty_string_invalid(self):
        self.assertFalse(self._v(""))

    def test_newline_injection_invalid(self):
        self.assertFalse(self._v("evil.com\n127.0.0.1 other.host"))

    def test_carriage_return_injection_invalid(self):
        self.assertFalse(self._v("evil.com\r127.0.0.1 other.host"))

    def test_space_injection_invalid(self):
        self.assertFalse(self._v("evil.com 127.0.0.1"))

    def test_hash_comment_injection_invalid(self):
        self.assertFalse(self._v("evil.com# comment"))

    def test_bare_hostname_no_dot_invalid(self):
        self.assertFalse(self._v("localhost"))

    def test_bare_ip_invalid(self):
        self.assertFalse(self._v("192.168.1.1"))

    def test_too_long_invalid(self):
        self.assertFalse(self._v("a" * 254 + ".com"))

    def test_leading_dot_invalid(self):
        self.assertFalse(self._v(".example.com"))

    def test_trailing_dot_invalid(self):
        self.assertFalse(self._v("example.com."))


# ===========================================================================
# Loopback address detection
# ===========================================================================

class TestIsLoopbackAddress(unittest.TestCase):

    def test_ipv4_loopback(self):
        self.assertTrue(server._is_loopback_address("127.0.0.1"))

    def test_ipv4_loopback_other(self):
        self.assertTrue(server._is_loopback_address("127.0.0.2"))

    def test_ipv4_loopback_high(self):
        self.assertTrue(server._is_loopback_address("127.255.255.255"))

    def test_ipv6_loopback(self):
        self.assertTrue(server._is_loopback_address("::1"))

    def test_public_ipv4_not_loopback(self):
        self.assertFalse(server._is_loopback_address("203.0.113.10"))

    def test_private_ipv4_not_loopback(self):
        self.assertFalse(server._is_loopback_address("192.168.1.50"))

    def test_ipv6_public_not_loopback(self):
        self.assertFalse(server._is_loopback_address("2001:db8::1"))

    def test_invalid_string_not_loopback(self):
        self.assertFalse(server._is_loopback_address("not-an-ip"))


# ===========================================================================
# _check_domain_health_fast
# ===========================================================================

class TestCheckDomainHealthFast(unittest.TestCase):
    """_check_domain_health_fast returns True when there is an issue,
    False when everything looks fine."""

    def _fast(self, domain, external_ip, resolved_addrs):
        with patch.object(server, "_resolve_all_addresses", return_value=resolved_addrs):
            return server._check_domain_health_fast(domain, external_ip)

    def test_no_domain_no_issue(self):
        # None/empty domain: the fast check reports True (handled by checklist).
        result = server._check_domain_health_fast(None, "203.0.113.10")
        self.assertTrue(result)

    def test_empty_domain_no_issue(self):
        result = server._check_domain_health_fast("", "203.0.113.10")
        self.assertTrue(result)

    def test_loopback_ipv4_no_issue(self):
        """Loopback override must not be flagged as a DNS mismatch."""
        result = self._fast("cloud.example.com", "203.0.113.10", ["127.0.0.1"])
        self.assertFalse(result)

    def test_loopback_ipv6_no_issue(self):
        result = self._fast("cloud.example.com", "203.0.113.10", ["::1"])
        self.assertFalse(result)

    def test_matches_external_ip_no_issue(self):
        result = self._fast("cloud.example.com", "203.0.113.10", ["203.0.113.10"])
        self.assertFalse(result)

    def test_mismatch_is_an_issue(self):
        result = self._fast("cloud.example.com", "203.0.113.10", ["198.51.100.1"])
        self.assertTrue(result)

    def test_unavailable_external_ip_no_issue(self):
        result = self._fast("cloud.example.com", "unavailable", ["198.51.100.1"])
        self.assertFalse(result)

    def test_multiple_addresses_one_matches_no_issue(self):
        """If any resolved address matches external_ip the check should pass."""
        result = self._fast(
            "cloud.example.com", "203.0.113.10",
            ["198.51.100.1", "203.0.113.10"],
        )
        self.assertFalse(result)


# ===========================================================================
# _evaluate_domain_checklist — loopback override path
# ===========================================================================

class TestEvaluateDomainChecklistLoopback(unittest.TestCase):

    def _eval(self, domain, external_ip, resolved_addrs, reachable_result=None):
        with (
            patch.object(server, "_resolve_all_addresses", return_value=resolved_addrs),
            patch.object(server, "_check_domain_reachable",
                         return_value=reachable_result or {"reachable": True, "status_code": 200}),
        ):
            return server._evaluate_domain_checklist(domain, external_ip)

    def test_loopback_dns_step_is_ok_not_error(self):
        result = self._eval("cloud.example.com", "203.0.113.10", ["127.0.0.1"])
        dns_step = next(s for s in result["domain_check_steps"] if s["step"] == 2)
        self.assertEqual(dns_step["status"], "ok")
        self.assertNotIn("mismatch", dns_step.get("detail", "").lower())

    def test_loopback_domain_status_is_local_override(self):
        result = self._eval("cloud.example.com", "203.0.113.10", ["127.0.0.1"])
        self.assertEqual(result["domain_status"]["status"], "local_override")

    def test_loopback_has_no_issues_when_reachable(self):
        result = self._eval(
            "cloud.example.com", "203.0.113.10", ["127.0.0.1"],
            reachable_result={"reachable": True, "status_code": 200},
        )
        self.assertFalse(result["has_issues"])

    def test_loopback_has_issues_when_caddy_unreachable(self):
        """A loopback override with Caddy down should still report an issue."""
        result = self._eval(
            "cloud.example.com", "203.0.113.10", ["127.0.0.1"],
            reachable_result={"reachable": False, "error": "connection refused"},
        )
        self.assertTrue(result["has_issues"])

    def test_ipv6_loopback_no_issue(self):
        result = self._eval("cloud.example.com", "203.0.113.10", ["::1"])
        self.assertEqual(result["domain_status"]["status"], "local_override")
        self.assertFalse(result["has_issues"])

    def test_genuine_mismatch_still_reports_error(self):
        result = self._eval("cloud.example.com", "203.0.113.10", ["198.51.100.1"])
        self.assertEqual(result["domain_status"]["status"], "dns_mismatch")
        self.assertTrue(result["has_issues"])

    def test_correct_public_dns_still_reports_ok(self):
        result = self._eval("cloud.example.com", "203.0.113.10", ["203.0.113.10"])
        self.assertEqual(result["domain_status"]["status"], "connected")
        self.assertFalse(result["has_issues"])

    def test_no_domain_has_issues(self):
        result = self._eval(None, "203.0.113.10", [])
        self.assertTrue(result["has_issues"])


# ===========================================================================
# api_services — composite health with loopback
# ===========================================================================

class TestApiServicesLoopbackHealth(unittest.IsolatedAsyncioTestCase):

    async def _get_health(self, resolved_addrs, cached_reachable):
        """Return the health value for a single domain-requiring service."""
        service_cfg = {
            "services": [
                {"unit": "caddy.service", "icon": "nextcloud", "enabled": True, "type": "system"}
            ]
        }
        with (
            patch.object(server, "load_config", return_value=service_cfg),
            patch.object(server, "_read_hub_overrides", return_value=({}, None, None)),
            patch.object(server.sysctl, "is_active", return_value="active"),
            patch.dict(server.SERVICE_DOMAIN_MAP, {"caddy.service": "nextcloud"}, clear=False),
            patch("builtins.open", mock_open(read_data="cloud.example.com\n")),
            patch.object(server, "_resolve_all_addresses", return_value=resolved_addrs),
            patch.object(server, "_is_domain_reachable_cached", return_value=cached_reachable),
            patch.object(server, "_get_listening_ports",
                         return_value={"tcp": {80, 443}, "udp": set()}),
            patch.object(server, "_get_firewall_allowed_ports",
                         return_value={"tcp": set(), "udp": set()}),
            patch.object(server, "_cached_external_ip", "203.0.113.10"),
        ):
            results = await server.api_services()

        return results[0]["health"]

    async def test_loopback_and_reachable_is_healthy(self):
        """Loopback override + Caddy reachable → healthy, not needs_attention."""
        health = await self._get_health(["127.0.0.1"], cached_reachable=True)
        self.assertEqual(health, "healthy")

    async def test_loopback_and_caddy_down_is_needs_attention(self):
        """Loopback override + Caddy unreachable → needs_attention (genuine issue)."""
        health = await self._get_health(["127.0.0.1"], cached_reachable=False)
        self.assertEqual(health, "needs_attention")

    async def test_correct_dns_and_reachable_is_healthy(self):
        health = await self._get_health(["203.0.113.10"], cached_reachable=True)
        self.assertEqual(health, "healthy")

    async def test_dns_mismatch_is_needs_attention(self):
        health = await self._get_health(["198.51.100.1"], cached_reachable=True)
        self.assertEqual(health, "needs_attention")


# ===========================================================================
# api_domains_check — loopback detection
# ===========================================================================

class TestApiDomainsCheckLoopback(unittest.IsolatedAsyncioTestCase):

    async def _check(self, resolved_addrs, external_ip="203.0.113.10"):
        with (
            patch.object(server, "_resolve_all_addresses", return_value=resolved_addrs),
            patch.object(server, "_cached_external_ip", external_ip),
        ):
            result = await server.api_domains_check(
                MagicMock(domains=["cloud.example.com"])
            )
        return result["domains"][0]

    async def test_loopback_ipv4_returns_local_override(self):
        result = await self._check(["127.0.0.1"])
        self.assertEqual(result["status"], "local_override")

    async def test_loopback_ipv6_returns_local_override(self):
        result = await self._check(["::1"])
        self.assertEqual(result["status"], "local_override")

    async def test_correct_dns_returns_connected(self):
        result = await self._check(["203.0.113.10"])
        self.assertEqual(result["status"], "connected")

    async def test_mismatch_returns_dns_mismatch(self):
        result = await self._check(["198.51.100.1"])
        self.assertEqual(result["status"], "dns_mismatch")

    async def test_no_resolution_returns_unresolvable(self):
        result = await self._check([])
        self.assertEqual(result["status"], "unresolvable")


if __name__ == "__main__":
    unittest.main()
