import unittest
from pathlib import Path
from unittest.mock import mock_open, patch
import sys
import types

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
from sovran_systemsos_web import server


class ServiceDetailRouterWordingTests(unittest.IsolatedAsyncioTestCase):
    async def test_livekit_service_detail_includes_internal_ip(self):
        service_cfg = {
            "services": [
                {"unit": "livekit.service", "icon": "element-call", "enabled": True, "type": "system"}
            ]
        }
        domain_eval = {
            "domain_status": {"status": "ok"},
            "domain_reachable": {"reachable": True},
            "domain_check_steps": [],
            "has_issues": False,
        }

        with (
            patch.object(server, "load_config", return_value=service_cfg),
            patch.object(server, "_read_hub_overrides", return_value=({}, None, None)),
            patch.object(server.sysctl, "is_active", return_value="active"),
            patch.dict(server.SERVICE_DOMAIN_MAP, {"livekit.service": "element-call"}, clear=False),
            patch.dict(
                server.SERVICE_PORT_REQUIREMENTS,
                {"livekit.service": [{"port": "7881", "protocol": "TCP", "description": "LiveKit"}]},
                clear=False,
            ),
            patch("builtins.open", mock_open(read_data="call.example.com\n")),
            patch.object(server, "_evaluate_domain_checklist", return_value=domain_eval),
            patch.object(server, "_get_internal_ip", return_value="192.168.1.44"),
            patch.object(server, "_save_internal_ip"),
            patch.object(server, "_get_listening_ports", return_value={"tcp": {7881}, "udp": set()}),
            patch.object(server, "_get_firewall_allowed_ports", return_value={"tcp": set(), "udp": set()}),
        ):
            result = await server.api_service_detail("livekit.service")

        self.assertEqual(result["internal_ip"], "192.168.1.44")
        self.assertEqual(result["extra_ports"][0]["status"], "listening")
        self.assertEqual(result["domain_check_steps"][-1]["label"], "Router Setup Needed")

    async def test_livekit_router_step_uses_not_ready_yet_wording(self):
        service_cfg = {
            "services": [
                {"unit": "livekit.service", "icon": "element-call", "enabled": True, "type": "system"}
            ]
        }
        domain_eval = {
            "domain_status": {"status": "ok"},
            "domain_reachable": {"reachable": True},
            "domain_check_steps": [],
            "has_issues": False,
        }

        with (
            patch.object(server, "load_config", return_value=service_cfg),
            patch.object(server, "_read_hub_overrides", return_value=({}, None, None)),
            patch.object(server.sysctl, "is_active", return_value="active"),
            patch.dict(server.SERVICE_DOMAIN_MAP, {"livekit.service": "element-call"}, clear=False),
            patch.dict(
                server.SERVICE_PORT_REQUIREMENTS,
                {"livekit.service": [{"port": "7881", "protocol": "TCP", "description": "LiveKit"}]},
                clear=False,
            ),
            patch("builtins.open", mock_open(read_data="call.example.com\n")),
            patch.object(server, "_evaluate_domain_checklist", return_value=domain_eval),
            patch.object(server, "_get_internal_ip", return_value="192.168.1.44"),
            patch.object(server, "_save_internal_ip"),
            patch.object(server, "_get_listening_ports", return_value={"tcp": set(), "udp": set()}),
            patch.object(server, "_get_firewall_allowed_ports", return_value={"tcp": set(), "udp": set()}),
        ):
            result = await server.api_service_detail("livekit.service")

        self.assertEqual(result["extra_ports"][0]["status"], "closed")
        self.assertIn("Not ready yet", result["domain_check_steps"][-1]["detail"])


if __name__ == "__main__":
    unittest.main()
