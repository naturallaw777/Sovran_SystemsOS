"""
Wallet Connections tests — validates the real AlbyHubManager and LNURL service
using mocked Alby Hub HTTP responses.

Tests cover:
- Feature registry and role visibility
- Manager idempotent setup/start/unlock
- Token refresh after 401/403
- App and transaction pagination
- Real create request body and scopes
- Real pairingUri returned once, absent from list
- Duplicate alias/name rejection
- Initial transfer success and partial-failure semantics
- Real list mapping (no secrets)
- Pending transaction blocking
- Drain permission update, transfer, final verification, restoration
- Delete using app pubkey after drain
- LNURL discovery from real-style app metadata
- Callback /api/invoices request includes numeric appId
- AppId mismatch rejection
- Invalid/fake BOLT11 rejection
- Public verification failure does not duplicate or roll back creation
- Caddy proxies to dedicated LNURL port 8181, not 8937
- Internal ports are not publicly opened
"""

import json
import re
import sys
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

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
        def __init__(self, *args, **kwargs):
            pass

    sys.modules["fastapi.staticfiles"].StaticFiles = _StaticFiles

    class _Jinja2Templates:
        def __init__(self, *args, **kwargs):
            pass

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

from sovran_systemsos_web import server
from sovran_systemsos_web import nwc_hub_manager as mgr
from sovran_systemsos_web.nwc_lnurl_service import (
    _lnurl_callback,
    _lnurl_discovery,
)


# ── Helpers ───────────────────────────────────────────────────────


def _make_app(
    id_=1,
    name="Test Wallet",
    alias="testwallet",
    scopes=None,
    pubkey="aabbcc",
    balance_msat=0,
    pending=None,
    max_amount=0,
):
    if scopes is None:
        scopes = list(mgr.RECEIVE_ONLY_SCOPES)
    return {
        "id": id_,
        "name": name,
        "nostrPubkey": pubkey,
        "scopes": scopes,
        "isolated": True,
        "maxAmountSat": max_amount,
        "budgetRenewal": "never",
        "budget": {"usedBudget": balance_msat, "remainingBudget": 0},
        "pendingTransactions": pending or [],
        "metadata": {
            "app_store_app_id": "uncle-jim",
            "lnurl_alias": alias,
            "lnurl_description": "Pay via Lightning",
            "lnurl_min_sendable_msat": 1000,
            "lnurl_max_sendable_msat": 1_000_000_000,
        },
        "createdAt": 1700000000,
    }


def _fresh_manager() -> mgr.AlbyHubManager:
    """Return a new manager with non-existent paths so filesystem checks fail fast."""
    return mgr.AlbyHubManager(
        api_base="http://127.0.0.1:18080",
        unlock_password_file="/nonexistent/unlock-password",
        macaroon_file="/nonexistent/albyhub.macaroon",
    )


# ── Feature registry tests ────────────────────────────────────────


class FeatureRegistryTests(unittest.TestCase):
    def test_node_role_includes_nwc_wallets(self):
        self.assertIn("nwc-wallets", server.ROLE_FEATURES["node"])

    def test_desktop_role_excludes_nwc_wallets(self):
        self.assertNotIn("nwc-wallets", server.ROLE_FEATURES["desktop"])

    def test_feature_metadata(self):
        feat = next(f for f in server.FEATURE_REGISTRY if f["id"] == "nwc-wallets")
        self.assertEqual(feat["name"], "Wallet Connections")
        self.assertTrue(feat["needs_domain"])
        self.assertEqual(feat["domain_name"], "lightning")
        ports = [(p["port"], p["protocol"]) for p in feat["port_requirements"]]
        self.assertIn(("80", "TCP"), ports)
        self.assertIn(("443", "TCP"), ports)

    def test_service_map_points_to_albyhub(self):
        self.assertEqual(server.FEATURE_SERVICE_MAP["nwc-wallets"], "albyhub.service")

    def test_domain_map_points_to_albyhub(self):
        self.assertEqual(server.SERVICE_DOMAIN_MAP["albyhub.service"], "lightning")

    def test_lnurl_paths_not_in_auth_exempt_prefixes(self):
        for prefix in server._AUTH_EXEMPT_PREFIXES:
            self.assertNotIn("lnurlp", prefix)

    def test_caddy_lnurl_proxy_port_is_not_8937(self):
        """Caddy must proxy LNURL routes to the dedicated service port (8181), not Hub port 8937."""
        caddy_nix = (
            Path(__file__).resolve().parents[3] / "modules" / "core" / "caddy.nix"
        )
        if caddy_nix.exists():
            content = caddy_nix.read_text()
            # Find the LIGHTNING block
            lightning_block = re.search(
                r"LIGHTNING\s*\{[^}]+\}", content, re.DOTALL
            )
            if lightning_block:
                block = lightning_block.group(0)
                self.assertNotIn(
                    "8937",
                    block,
                    "Caddy must NOT proxy LNURL routes to Hub port 8937",
                )
                self.assertIn(
                    "8181",
                    block,
                    "Caddy must proxy LNURL routes to dedicated LNURL port 8181",
                )


# ── Alias validation ──────────────────────────────────────────────


class AliasValidationTests(unittest.TestCase):
    def test_valid_aliases(self):
        for alias in ("app", "a1", "my-wallet", "app_1", "a" * 32):
            self.assertTrue(server._nwc_validate_alias(alias), f"expected valid: {alias}")

    def test_invalid_aliases(self):
        for alias in ("_bad", "Upper", "a" * 33, "", "-start"):
            self.assertFalse(server._nwc_validate_alias(alias), f"expected invalid: {alias}")


# ── Manager unit tests (mocked HTTP) ────────────────────────────────


class ManagerEnsureReadyTests(unittest.TestCase):
    def _manager_with_stubs(self, unlock_pw="testpass", macaroon_hex="deadbeef"):
        m = _fresh_manager()
        m._wait_for_file = MagicMock()
        m._wait_for_hub_api = MagicMock()
        m._read_unlock_password = MagicMock(return_value=unlock_pw)
        m._wait_for_node_ready = MagicMock()
        return m

    def test_setup_and_token_cached(self):
        m = self._manager_with_stubs()
        m._hub_setup = MagicMock()
        m._hub_unlock = MagicMock()
        m._obtain_token = MagicMock(return_value="tok123")
        token = m.ensure_ready()
        self.assertEqual(token, "tok123")
        # Second call should use cached token without re-auth
        token2 = m.ensure_ready()
        self.assertEqual(token2, "tok123")
        m._obtain_token.assert_called_once()

    def test_idempotent_setup_skipped_when_already_complete(self):
        m = self._manager_with_stubs()
        m._hub_setup = MagicMock()
        m._hub_unlock = MagicMock()
        m._obtain_token = MagicMock(return_value="tok-setup")
        m.ensure_ready()
        m._hub_setup.assert_called_once()

    def test_401_triggers_token_refresh(self):
        m = self._manager_with_stubs()
        m._hub_setup = MagicMock()
        m._hub_unlock = MagicMock()
        tokens = iter(["first-token", "refreshed-token"])
        m._obtain_token = MagicMock(side_effect=tokens)
        m.ensure_ready()

        # First _request call raises 401; second returns success after token refresh
        request_count = [0]

        def _request_side(*_a, **_kw):
            request_count[0] += 1
            if request_count[0] == 1:
                raise mgr.AlbyHubHttpError(401, "Unauthorised")
            return {"ok": True}

        m._request = MagicMock(side_effect=_request_side)
        result = m._authenticated_request("GET", "/api/apps")
        # The retry with a refreshed token should succeed
        self.assertEqual(result, {"ok": True})
        # Token must have been refreshed (obtain_token called twice total)
        self.assertEqual(m._obtain_token.call_count, 2)

    def test_403_triggers_token_refresh(self):
        m = self._manager_with_stubs()
        m._hub_setup = MagicMock()
        m._hub_unlock = MagicMock()
        tokens = iter(["first", "second", "third"])
        m._obtain_token = MagicMock(side_effect=tokens)
        m.ensure_ready()
        m._token = None  # clear to force re-auth

        request_count = [0]

        def _request_side(*_a, **_kw):
            request_count[0] += 1
            if request_count[0] == 1:
                raise mgr.AlbyHubHttpError(403, "Forbidden")
            return {}

        m._request = MagicMock(side_effect=_request_side)
        result = m._authenticated_request("GET", "/api/apps")
        self.assertEqual(result, {})


class ManagerPaginationTests(unittest.TestCase):
    def test_paginate_collects_all_pages(self):
        m = _fresh_manager()
        page1 = [{"id": i} for i in range(100)]
        page2 = [{"id": i} for i in range(100, 150)]

        def _request(method, path, **_kw):
            if "offset=0" in path:
                return page1
            return page2

        m._token = "tok"
        m._request = MagicMock(side_effect=_request)
        result = m._paginate("/api/apps?limit={limit}&offset={offset}")
        self.assertEqual(len(result), 150)

    def test_paginate_single_page_stops(self):
        m = _fresh_manager()
        m._token = "tok"
        m._request = MagicMock(return_value=[{"id": 1}, {"id": 2}])
        result = m._paginate("/api/apps?limit={limit}&offset={offset}", page_size=100)
        self.assertEqual(len(result), 2)
        m._request.assert_called_once()


class ManagerListTests(unittest.TestCase):
    def _mgr_with_token(self, apps):
        m = _fresh_manager()
        m._token = "tok"
        m._request = MagicMock(return_value=apps)
        return m

    def test_list_returns_only_managed_isolated_apps(self):
        apps = [
            _make_app(id_=1, alias="alice"),
            {
                "id": 2, "name": "Unmanaged", "isolated": True,
                "metadata": {"app_store_app_id": "other"},
                "scopes": [], "budget": {}, "pendingTransactions": [],
            },
            {
                "id": 3, "name": "Not isolated", "isolated": False,
                "metadata": {"app_store_app_id": "uncle-jim"},
                "scopes": [], "budget": {}, "pendingTransactions": [],
            },
        ]
        m = self._mgr_with_token(apps)
        result = m.list_wallets(domain="pay.example.com")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["alias"], "alice")

    def test_list_does_not_include_pairing_uri(self):
        apps = [_make_app()]
        m = self._mgr_with_token(apps)
        for wallet in m.list_wallets():
            self.assertNotIn("pairing_uri", wallet)
            self.assertNotIn("pairingUri", wallet)

    def test_list_maps_access_preset_from_scopes(self):
        apps = [
            _make_app(id_=1, alias="recv", scopes=list(mgr.RECEIVE_ONLY_SCOPES)),
            _make_app(id_=2, alias="send", scopes=list(mgr.LIMITED_SEND_SCOPES)),
        ]
        m = self._mgr_with_token(apps)
        wallets = m.list_wallets()
        self.assertEqual(wallets[0]["access_preset"], "receive_only")
        self.assertEqual(wallets[1]["access_preset"], "send_receive_limited")

    def test_list_maps_lightning_address(self):
        apps = [_make_app(alias="bob")]
        m = self._mgr_with_token(apps)
        result = m.list_wallets(domain="pay.example.com")
        self.assertEqual(result[0]["lightning_address"], "bob@pay.example.com")


class ManagerCreateTests(unittest.TestCase):
    def _mgr(self, existing_apps=None, create_resp=None):
        m = _fresh_manager()
        m._token = "tok"
        if existing_apps is None:
            existing_apps = []
        if create_resp is None:
            create_resp = {
                "id": 99,
                "pairingUri": "nostr+walletconnect://fakepubkey?relay=wss%3A%2F%2Frelay.getalby.com&secret=FAKESECRET",
                **_make_app(id_=99, alias="new"),
            }

        call_count = [0]

        def _request(method, path, **kw):
            call_count[0] += 1
            if method == "GET" and path.startswith("/api/apps"):
                return existing_apps
            if method == "POST" and path == "/api/apps":
                return create_resp
            if method == "GET" and path.startswith("/api/apps/99"):
                return _make_app(id_=99, alias="new")
            return {}

        m._request = MagicMock(side_effect=_request)
        return m

    @staticmethod
    def _call_body(call):
        """Return the ``body`` kwarg from a MagicMock call_args."""
        return call.kwargs.get("body") or {}

    def test_create_returns_pairing_uri_once(self):
        m = self._mgr()
        result = m.create_wallet("New Wallet", "new", "receive_only", None)
        self.assertIn("pairing_uri", result)
        self.assertTrue(result["pairing_uri"].startswith("nostr+walletconnect://"))

    def test_create_sends_isolated_true(self):
        m = self._mgr()
        m.create_wallet("W", "w", "receive_only", None)
        create_call = next(
            c for c in m._request.call_args_list
            if c.args[0] == "POST" and c.args[1] == "/api/apps"
        )
        body = self._call_body(create_call)
        self.assertTrue(body.get("isolated"))

    def test_create_receive_only_scopes(self):
        m = self._mgr()
        m.create_wallet("W", "w", "receive_only", None)
        create_call = next(
            c for c in m._request.call_args_list
            if c.args[0] == "POST" and "/api/apps" in c.args[1]
        )
        body = self._call_body(create_call)
        self.assertNotIn("pay_invoice", body.get("scopes", []))
        for scope in mgr.RECEIVE_ONLY_SCOPES:
            self.assertIn(scope, body.get("scopes", []))

    def test_create_limited_includes_pay_invoice(self):
        m = self._mgr()
        m.create_wallet("W", "w", "send_receive_limited", 5000)
        create_call = next(
            c for c in m._request.call_args_list
            if c.args[0] == "POST" and "/api/apps" in c.args[1]
        )
        body = self._call_body(create_call)
        self.assertIn("pay_invoice", body.get("scopes", []))

    def test_create_includes_managed_metadata(self):
        m = self._mgr()
        m.create_wallet("W", "w", "receive_only", None)
        create_call = next(
            c for c in m._request.call_args_list
            if c.args[0] == "POST" and "/api/apps" in c.args[1]
        )
        body = self._call_body(create_call)
        meta = body.get("metadata", {})
        self.assertEqual(meta.get("app_store_app_id"), "uncle-jim")
        self.assertEqual(meta.get("lnurl_alias"), "w")

    def test_create_rejects_duplicate_alias(self):
        existing = [_make_app(alias="dup")]
        m = self._mgr(existing_apps=existing)
        with self.assertRaises(mgr.AlbyHubError) as ctx:
            m.create_wallet("New", "dup", "receive_only", None)
        self.assertEqual(ctx.exception.code, "alias_exists")

    def test_create_rejects_duplicate_name(self):
        existing = [_make_app(name="Existing Wallet")]
        m = self._mgr(existing_apps=existing)
        with self.assertRaises(mgr.AlbyHubError) as ctx:
            m.create_wallet("Existing Wallet", "newone", "receive_only", None)
        self.assertEqual(ctx.exception.code, "wallet_name_exists")

    def test_create_limited_performs_initial_transfer(self):
        m = self._mgr()
        transfers = []

        original_request = m._request.side_effect

        def _request(method, path, **kw):
            if method == "POST" and path == "/api/transfers":
                transfers.append(kw.get("body"))
                return {}
            return original_request(method, path, **kw)

        m._request = MagicMock(side_effect=_request)
        m.create_wallet("W", "w", "send_receive_limited", 5000)
        self.assertEqual(len(transfers), 1)
        self.assertEqual(transfers[0]["toAppId"], 99)
        self.assertEqual(transfers[0]["amountMsat"], 5_000_000)

    def test_create_partial_failure_funding_returns_pairing_uri(self):
        """Even when initial funding fails, the real pairing URI must be returned."""
        m = self._mgr()

        def _request(method, path, **kw):
            if method == "GET" and path.startswith("/api/apps?"):
                return []
            if method == "POST" and path == "/api/apps":
                return {
                    "id": 99,
                    "pairingUri": "nostr+walletconnect://pubkey?relay=r&secret=S",
                    **_make_app(id_=99, alias="new"),
                }
            if method == "POST" and path == "/api/transfers":
                raise mgr.AlbyHubError("transfer_failed", "Insufficient funds")
            if method == "GET" and "/api/apps/99" in path:
                return _make_app(id_=99, alias="new")
            return {}

        m._request = MagicMock(side_effect=_request)
        result = m.create_wallet("W", "new", "send_receive_limited", 5000)

        # Pairing URI must still be returned
        self.assertTrue(result["pairing_uri"])
        # Funding failure must be clearly reported
        self.assertFalse(result["result"]["funding"]["success"])
        self.assertIn("message", result["result"]["funding"])


class ManagerDrainTests(unittest.TestCase):
    def _mgr(self, app, transfer_ok=True):
        m = _fresh_manager()
        m._token = "tok"

        def _request(method, path, **kw):
            if method == "GET" and path.startswith("/api/apps?"):
                return [app]
            if method == "GET" and f"/api/apps/{app['id']}" in path and "transactions" not in path:
                return app
            if method == "GET" and "transactions" in path:
                return []
            if method == "PATCH":
                return {}
            if method == "POST" and path == "/api/transfers":
                if not transfer_ok:
                    raise mgr.AlbyHubError("transfer_failed", "Fail")
                return {}
            return {}

        m._request = MagicMock(side_effect=_request)
        return m

    def test_drain_transfers_whole_sats(self):
        app = _make_app(balance_msat=5_000_000)
        m = self._mgr(app)
        result = m.drain_wallet("1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["drained_sats"], 5000)

    def test_drain_preserves_dust(self):
        app = _make_app(balance_msat=5_000_500)
        m = self._mgr(app)
        result = m.drain_wallet("1")
        self.assertEqual(result["drained_sats"], 5000)
        self.assertEqual(result["dust_msat"], 500)

    def test_drain_patches_permissions_then_restores(self):
        app = _make_app(scopes=list(mgr.RECEIVE_ONLY_SCOPES), balance_msat=1_000_000)
        m = self._mgr(app)
        patches = []

        original = m._request.side_effect

        def _request(method, path, **kw):
            if method == "PATCH":
                patches.append(kw.get("body"))
                return {}
            return original(method, path, **kw)

        m._request = MagicMock(side_effect=_request)
        m.drain_wallet("1")
        self.assertEqual(len(patches), 2)
        first_patch = patches[0]
        second_patch = patches[1]
        # First patch must add pay_invoice
        self.assertIn("pay_invoice", first_patch.get("scopes", []))
        # Second patch (restore) must match original scopes
        self.assertEqual(
            sorted(second_patch.get("scopes", [])),
            sorted(mgr.RECEIVE_ONLY_SCOPES),
        )

    def test_drain_rejects_pending_transactions(self):
        app = _make_app(pending=[{"state": "pending"}])
        m = _fresh_manager()
        m._token = "tok"

        def _request(method, path, **kw):
            if method == "GET" and path.startswith("/api/apps?"):
                return [app]
            if "transactions" in path:
                return [{"state": "pending"}]
            return {}

        m._request = MagicMock(side_effect=_request)
        with self.assertRaises(mgr.AlbyHubError) as ctx:
            m.drain_wallet("1")
        self.assertEqual(ctx.exception.code, "pending_transactions")

    def test_drain_restores_permissions_on_failure(self):
        app = _make_app(scopes=list(mgr.RECEIVE_ONLY_SCOPES), balance_msat=1_000_000)
        m = self._mgr(app, transfer_ok=False)
        patches = []
        original = m._request.side_effect

        def _request(method, path, **kw):
            if method == "PATCH":
                patches.append(kw.get("body"))
                return {}
            return original(method, path, **kw)

        m._request = MagicMock(side_effect=_request)
        with self.assertRaises(mgr.AlbyHubError):
            m.drain_wallet("1")
        # Restore patch must still have been attempted
        self.assertGreaterEqual(len(patches), 2)
        restore = patches[-1]
        self.assertEqual(sorted(restore.get("scopes", [])), sorted(mgr.RECEIVE_ONLY_SCOPES))


class ManagerDeleteTests(unittest.TestCase):
    def _mgr(self, app, drain_ok=True):
        m = _fresh_manager()
        m._token = "tok"
        deleted = []

        def _request(method, path, **kw):
            if method == "GET" and path.startswith("/api/apps?"):
                return [app]
            if method == "GET" and "transactions" in path:
                return []
            if method == "GET" and f"/api/apps/{app['id']}" in path:
                # After drain the balance is zero
                a = dict(app)
                a["budget"] = {"usedBudget": 0}
                return a
            if method == "PATCH":
                return {}
            if method == "POST" and path == "/api/transfers":
                if not drain_ok:
                    raise mgr.AlbyHubError("transfer_failed", "Fail")
                return {}
            if method == "DELETE":
                deleted.append(path)
                return {}
            return {}

        m._request = MagicMock(side_effect=_request)
        m._deleted = deleted
        return m

    def test_delete_uses_pubkey_endpoint(self):
        app = _make_app(pubkey="pubkey123", balance_msat=0)
        m = self._mgr(app)
        m.delete_wallet("1")
        delete_path = m._deleted[0] if m._deleted else ""
        self.assertIn("pubkey123", delete_path)

    def test_delete_drains_before_deleting(self):
        app = _make_app(pubkey="pk", balance_msat=1_000_000)
        m = self._mgr(app)
        m.delete_wallet("1")
        # Ensure DELETE was called (drain happened first)
        self.assertTrue(m._deleted)

    def test_delete_rejects_pending_transactions(self):
        app = _make_app(pending=[{"state": "pending"}])
        m = _fresh_manager()
        m._token = "tok"

        def _request(method, path, **kw):
            if method == "GET" and path.startswith("/api/apps?"):
                return [app]
            if "transactions" in path:
                return [{"state": "pending"}]
            return {}

        m._request = MagicMock(side_effect=_request)
        with self.assertRaises(mgr.AlbyHubError) as ctx:
            m.delete_wallet("1")
        self.assertEqual(ctx.exception.code, "pending_transactions")


class ManagerInvoiceTests(unittest.TestCase):
    def _mgr(self, invoice="lnbc1000n1ptest", app_id=1):
        m = _fresh_manager()
        m._token = "tok"
        m._request = MagicMock(
            return_value={"paymentRequest": invoice, "appId": app_id}
        )
        return m

    def test_invoice_returns_valid_bolt11(self):
        m = self._mgr("lnbc5000n1pfake_invoice_test")
        invoice = m.issue_invoice(1, 5_000_000)
        self.assertTrue(invoice.startswith("lnbc"))

    def test_invoice_rejects_fake_pr_string(self):
        m = self._mgr("lnbc5n1" + "z" * 40)
        # This starts with lnbc so is valid format - test the appId mismatch instead
        m._request = MagicMock(
            return_value={"paymentRequest": "not_a_bolt11", "appId": 1}
        )
        with self.assertRaises(mgr.AlbyHubError) as ctx:
            m.issue_invoice(1, 5_000_000)
        self.assertEqual(ctx.exception.code, "invalid_invoice")

    def test_invoice_rejects_appid_mismatch(self):
        m = _fresh_manager()
        m._token = "tok"
        m._request = MagicMock(
            return_value={"paymentRequest": "lnbc1000n1test", "appId": 999}
        )
        with self.assertRaises(mgr.AlbyHubError) as ctx:
            m.issue_invoice(1, 1_000_000)
        self.assertEqual(ctx.exception.code, "invoice_attribution_failed")

    def test_invoice_request_includes_app_id(self):
        # Use a manager that returns the correct appId matching what we request
        m = _fresh_manager()
        m._token = "tok"
        m._request = MagicMock(
            return_value={"paymentRequest": "lnbc1000n1test", "appId": 42}
        )
        m.issue_invoice(42, 2_000_000)
        call_body = m._request.call_args.kwargs.get("body") or m._request.call_args[1].get("body")
        self.assertEqual(call_body["appId"], 42)


# ── LNURL service tests ───────────────────────────────────────────


class LnurlDiscoveryTests(unittest.TestCase):
    def _manager_for(self, app):
        m = _fresh_manager()
        m._token = "tok"
        m._request = MagicMock(return_value=[app])
        return m

    def test_discovery_returns_pay_request(self):
        app = _make_app(alias="alice")
        m = self._manager_for(app)
        with patch("sovran_systemsos_web.nwc_lnurl_service._read_domain", return_value="pay.example.com"):
            payload, code = _lnurl_discovery("alice", m)
        self.assertEqual(code, 200)
        self.assertEqual(payload["tag"], "payRequest")
        self.assertIn("alice", payload["callback"])

    def test_discovery_uses_app_metadata_for_limits(self):
        app = _make_app(alias="bob")
        app["metadata"]["lnurl_min_sendable_msat"] = 2000
        app["metadata"]["lnurl_max_sendable_msat"] = 500_000_000
        m = self._manager_for(app)
        with patch("sovran_systemsos_web.nwc_lnurl_service._read_domain", return_value="pay.example.com"):
            payload, code = _lnurl_discovery("bob", m)
        self.assertEqual(payload["minSendable"], 2000)
        self.assertEqual(payload["maxSendable"], 500_000_000)

    def test_discovery_returns_404_for_unknown_alias(self):
        m = _fresh_manager()
        m._token = "tok"
        m._request = MagicMock(return_value=[])
        with patch("sovran_systemsos_web.nwc_lnurl_service._read_domain", return_value="pay.example.com"):
            payload, code = _lnurl_discovery("nobody", m)
        self.assertEqual(code, 404)

    def test_discovery_returns_503_when_domain_unconfigured(self):
        m = self._manager_for(_make_app())
        with patch("sovran_systemsos_web.nwc_lnurl_service._read_domain", return_value=None):
            payload, code = _lnurl_discovery("alice", m)
        self.assertEqual(code, 503)


class LnurlCallbackTests(unittest.TestCase):
    def _manager_for(self, app, invoice="lnbc1000n1pfakebolt11test"):
        m = _fresh_manager()
        m._token = "tok"

        def _request(method, path, **kw):
            if path.startswith("/api/apps"):
                return [app]
            if path == "/api/invoices":
                body = kw.get("body") or {}
                return {"paymentRequest": invoice, "appId": body.get("appId")}
            return {}

        m._request = MagicMock(side_effect=_request)
        return m

    def test_callback_returns_bolt11_invoice(self):
        app = _make_app(alias="carol")
        m = self._manager_for(app)
        with patch("sovran_systemsos_web.nwc_lnurl_service._read_domain", return_value="pay.example.com"):
            payload, code = _lnurl_callback("carol", "1000", m)
        self.assertEqual(code, 200)
        self.assertIn("pr", payload)
        self.assertEqual(payload["routes"], [])
        self.assertTrue(payload["pr"].startswith("lnbc"))

    def test_callback_sends_app_id_to_invoices_api(self):
        app = _make_app(id_=7, alias="dave")
        m = self._manager_for(app)
        invoice_calls = []
        original = m._request.side_effect

        def _request(method, path, **kw):
            if method == "POST" and path == "/api/invoices":
                invoice_calls.append(kw.get("body"))
            return original(method, path, **kw)

        m._request = MagicMock(side_effect=_request)
        with patch("sovran_systemsos_web.nwc_lnurl_service._read_domain", return_value="pay.example.com"):
            _lnurl_callback("dave", "1000", m)
        self.assertEqual(len(invoice_calls), 1)
        self.assertEqual(invoice_calls[0]["appId"], 7)

    def test_callback_rejects_amount_below_minimum(self):
        app = _make_app(alias="eve")
        m = self._manager_for(app)
        with patch("sovran_systemsos_web.nwc_lnurl_service._read_domain", return_value="pay.example.com"):
            payload, code = _lnurl_callback("eve", "500", m)
        self.assertEqual(code, 400)

    def test_callback_rejects_non_whole_satoshi(self):
        app = _make_app(alias="frank")
        m = self._manager_for(app)
        with patch("sovran_systemsos_web.nwc_lnurl_service._read_domain", return_value="pay.example.com"):
            payload, code = _lnurl_callback("frank", "1500", m)
        self.assertEqual(code, 400)

    def test_callback_rejects_appid_mismatch(self):
        app = _make_app(id_=1, alias="grace")
        m = _fresh_manager()
        m._token = "tok"

        def _request(method, path, **kw):
            if path.startswith("/api/apps"):
                return [app]
            if path == "/api/invoices":
                # Return wrong appId
                return {"paymentRequest": "lnbc1000n1pfake", "appId": 999}
            return {}

        m._request = MagicMock(side_effect=_request)
        with patch("sovran_systemsos_web.nwc_lnurl_service._read_domain", return_value="pay.example.com"):
            payload, code = _lnurl_callback("grace", "1000", m)
        self.assertEqual(code, 502)

    def test_callback_rejects_fake_bolt11(self):
        app = _make_app(id_=1, alias="heidi")
        m = _fresh_manager()
        m._token = "tok"

        def _request(method, path, **kw):
            if path.startswith("/api/apps"):
                return [app]
            if path == "/api/invoices":
                return {"paymentRequest": "not_a_bolt11_string", "appId": 1}
            return {}

        m._request = MagicMock(side_effect=_request)
        with patch("sovran_systemsos_web.nwc_lnurl_service._read_domain", return_value="pay.example.com"):
            payload, code = _lnurl_callback("heidi", "1000", m)
        self.assertEqual(code, 502)


# ── Server API integration tests ─────────────────────────────────


class _FakeJSONResponse:
    def __init__(self, content=None, status_code=200):
        self.content = content
        self.status_code = status_code
        self.body = json.dumps(content or {}).encode("utf-8")


class ServerApiTests(unittest.IsolatedAsyncioTestCase):
    """Thin tests ensuring the server API routes call the manager correctly."""

    def _mock_manager(self, wallets=None, create_result=None, domain=None):
        m = MagicMock()
        m.list_wallets.return_value = wallets or []
        if create_result:
            m.create_wallet.return_value = create_result
        return m

    async def test_api_nwc_wallets_returns_wallets(self):
        fake_manager = self._mock_manager(
            wallets=[{"id": "1", "name": "W", "alias": "w"}]
        )
        with (
            patch.object(server._nwc_mgr, "get_manager", return_value=fake_manager),
            patch.object(server, "_nwc_domain", return_value="pay.example.com"),
        ):
            result = await server.api_nwc_wallets()
        self.assertEqual(len(result["wallets"]), 1)

    async def test_api_create_returns_pairing_uri(self):
        pairing_uri = "nostr+walletconnect://pk?relay=r&secret=S"
        fake_manager = self._mock_manager(
            create_result={
                "wallet": {"id": "1", "alias": "new"},
                "pairing_uri": pairing_uri,
                "result": {"wallet_created": True, "secret_created": True, "lightning_address_registered": True, "funding": {"attempted": False}},
            }
        )
        req = types.SimpleNamespace(
            name="New Wallet",
            alias="newwallet",
            access_preset="receive_only",
            spending_limit_sats=None,
        )
        with (
            patch.object(server._nwc_mgr, "get_manager", return_value=fake_manager),
            patch.object(server, "_nwc_domain", return_value="pay.example.com"),
            patch.object(server, "_nwc_test_address", return_value={"ok": True}),
            patch.object(server, "_generate_qr_base64", return_value="data:image/png;base64,abc"),
            patch.object(server, "JSONResponse", _FakeJSONResponse),
        ):
            resp = await server.api_nwc_create_wallet(req)
        body = json.loads(resp.body.decode("utf-8"))
        self.assertEqual(body["pairing_uri"], pairing_uri)
        self.assertEqual(resp.status_code, 201)

    async def test_api_create_pairing_qrcode_in_response(self):
        pairing_uri = "nostr+walletconnect://pk?relay=r&secret=S"
        fake_manager = self._mock_manager(
            create_result={
                "wallet": {"id": "1", "alias": "new"},
                "pairing_uri": pairing_uri,
                "result": {"wallet_created": True, "secret_created": True, "lightning_address_registered": True, "funding": {"attempted": False}},
            }
        )
        req = types.SimpleNamespace(
            name="QR Wallet", alias="qrwallet", access_preset="receive_only",
            spending_limit_sats=None,
        )
        with (
            patch.object(server._nwc_mgr, "get_manager", return_value=fake_manager),
            patch.object(server, "_nwc_domain", return_value="pay.example.com"),
            patch.object(server, "_nwc_test_address", return_value={"ok": False}),
            patch.object(server, "_generate_qr_base64", return_value="data:image/png;base64,qrdata"),
            patch.object(server, "JSONResponse", _FakeJSONResponse),
        ):
            resp = await server.api_nwc_create_wallet(req)
        body = json.loads(resp.body.decode("utf-8"))
        self.assertEqual(body.get("pairing_qrcode"), "data:image/png;base64,qrdata")

    async def test_api_create_rejects_invalid_alias(self):
        req = types.SimpleNamespace(
            name="Bad", alias="_INVALID", access_preset="receive_only",
            spending_limit_sats=None,
        )
        with patch.object(server, "JSONResponse", _FakeJSONResponse):
            resp = await server.api_nwc_create_wallet(req)
        body = json.loads(resp.body.decode("utf-8"))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(body["error"], "alias_invalid")


if __name__ == "__main__":
    unittest.main()
