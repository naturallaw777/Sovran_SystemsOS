import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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
    responses_module.RedirectResponse = object

    class _JSONResponse:
        def __init__(self, content=None, status_code=200):
            self.content = content
            self.status_code = status_code
            self.body = json.dumps(content or {}).encode("utf-8")

    responses_module.JSONResponse = _JSONResponse
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
from sovran_systemsos_web import server


class FakeJSONResponse:
    def __init__(self, content=None, status_code=200):
        self.content = content
        self.status_code = status_code
        self.body = json.dumps(content or {}).encode("utf-8")


class WalletConnectionsRegistryTests(unittest.TestCase):
    def test_node_role_feature_allow_list_includes_nwc_wallets(self):
        self.assertIn("nwc-wallets", server.ROLE_FEATURES["node"])
        self.assertNotIn("nwc-wallets", server.ROLE_FEATURES["desktop"])

    def test_wallet_connections_feature_metadata(self):
        feat = next(f for f in server.FEATURE_REGISTRY if f["id"] == "nwc-wallets")
        self.assertEqual(feat["name"], "Wallet Connections")
        self.assertTrue(feat["needs_domain"])
        self.assertEqual(feat["domain_name"], "lightning")
        self.assertEqual(
            [(p["port"], p["protocol"]) for p in feat["port_requirements"]],
            [("80", "TCP"), ("443", "TCP")],
        )


class WalletConnectionsBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_alias_validation_rules(self):
        self.assertTrue(server._nwc_validate_alias("app_1"))
        self.assertTrue(server._nwc_validate_alias("a-1"))
        self.assertFalse(server._nwc_validate_alias("_bad"))
        self.assertFalse(server._nwc_validate_alias("Upper"))
        self.assertFalse(server._nwc_validate_alias("a" * 33))

    async def test_pairing_uri_returned_only_on_create(self):
        with tempfile.TemporaryDirectory() as td:
            state_file = Path(td) / "state.json"
            domain_file = Path(td) / "lightning"
            domain_file.write_text("pay.example.com\n")
            with (
                patch.object(server, "JSONResponse", FakeJSONResponse),
                patch.object(server, "NWC_STATE_FILE", str(state_file)),
                patch.object(server, "NWC_DOMAIN_FILE", str(domain_file)),
                patch.object(server, "_nwc_test_address", return_value={"ok": False, "error": "public_endpoint_unreachable"}),
                patch.object(server, "_generate_qr_base64", return_value="data:image/png;base64,abc"),
            ):
                req = types.SimpleNamespace(
                    name="My Wallet",
                    alias="my-wallet",
                    access_preset="receive_only",
                    spending_limit_sats=None,
                )
                create_resp = await server.api_nwc_create_wallet(req)
                create_body = json.loads(create_resp.body.decode("utf-8"))
                self.assertIn("pairing_uri", create_body)
                self.assertEqual(create_body.get("pairing_qrcode"), "data:image/png;base64,abc")

                list_resp = await server.api_nwc_wallets()
                self.assertEqual(len(list_resp["wallets"]), 1)
                self.assertNotIn("pairing_uri", list_resp["wallets"][0])
                self.assertNotIn("pairing_qrcode", list_resp["wallets"][0])

    async def test_create_reports_public_verification_success(self):
        with tempfile.TemporaryDirectory() as td:
            state_file = Path(td) / "state.json"
            domain_file = Path(td) / "lightning"
            domain_file.write_text("pay.example.com\n")
            with (
                patch.object(server, "JSONResponse", FakeJSONResponse),
                patch.object(server, "NWC_STATE_FILE", str(state_file)),
                patch.object(server, "NWC_DOMAIN_FILE", str(domain_file)),
                patch.object(server, "_nwc_test_address", return_value={"ok": True}),
            ):
                req = types.SimpleNamespace(
                    name="Wallet Success",
                    alias="wallet-success",
                    access_preset="receive_only",
                    spending_limit_sats=None,
                )
                create_resp = await server.api_nwc_create_wallet(req)
                create_body = json.loads(create_resp.body.decode("utf-8"))
                self.assertTrue(create_body["result"]["wallet_created"])
                self.assertTrue(create_body["result"]["public_endpoint_verification"]["ok"])

    async def test_lnurl_callback_rejects_appid_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            state_file = Path(td) / "state.json"
            domain_file = Path(td) / "lightning"
            domain_file.write_text("pay.example.com\n")
            state_file.write_text(
                json.dumps(
                    {
                        "wallets": [
                            {
                                "id": "wallet-1",
                                "pubkey": "pubkey-1",
                                "name": "Wallet 1",
                                "alias": "wallet1",
                                "access_preset": "receive_only",
                                "spending_limit_sats": None,
                                "remaining_budget_sats": None,
                                "balance_sats": 0,
                                "dust_msat": 0,
                                "pending_transactions": 0,
                                "min_sendable_msat": 1000,
                                "max_sendable_msat": 1000000,
                                "created_at": 0,
                            }
                        ]
                    }
                )
            )
            with (
                patch.object(server, "JSONResponse", FakeJSONResponse),
                patch.object(server, "NWC_STATE_FILE", str(state_file)),
                patch.object(server, "NWC_DOMAIN_FILE", str(domain_file)),
                patch.object(server, "_nwc_issue_invoice", return_value={"appId": "wrong", "pr": "lnbc1..."}),
            ):
                resp = await server.api_lnurl_callback("wallet1", amount="1000")
                body = json.loads(resp.body.decode("utf-8"))
                self.assertEqual(resp.status_code, 502)
                self.assertEqual(body["error"], "invoice_attribution_failed")


if __name__ == "__main__":
    unittest.main()
