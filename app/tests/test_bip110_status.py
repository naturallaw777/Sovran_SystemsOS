import unittest
from unittest.mock import patch
from pathlib import Path
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


class Bip110StatusTests(unittest.TestCase):
    def _status(self, deploy_info, net_info):
        with patch.object(server, "_get_bitcoin_deployment_info", return_value=deploy_info), patch.object(
            server, "_get_bitcoin_version_info", return_value=net_info
        ):
            return server._get_bip110_status()

    def test_started_reduced_data_reports_signaling(self):
        deploy_info = {
            "deployments": {
                "reduced_data": {
                    "type": "bip9",
                    "active": False,
                    "bip9": {
                        "bit": 4,
                        "status": "started",
                        "statistics": {"elapsed": 833, "count": 4, "threshold": 1109},
                        "signalling": "--#--",
                    },
                }
            }
        }

        result = self._status(deploy_info, {"subversion": "/Satoshi:29.0.0/"})
        self.assertEqual(
            result,
            {"supported": True, "signaling": True, "state": "signaling", "source": "getdeploymentinfo"},
        )

    def test_active_reduced_data_reports_active(self):
        deploy_info = {
            "deployments": {"reduced_data": {"active": True, "bip9": {"bit": 4, "status": "active"}}}
        }

        result = self._status(deploy_info, {"subversion": "/Satoshi:29.0.0/"})
        self.assertEqual(result["state"], "active")
        self.assertTrue(result["supported"])
        self.assertTrue(result["signaling"])
        self.assertEqual(result["source"], "getdeploymentinfo")

    def test_locked_in_reduced_data_reports_locked_in(self):
        deploy_info = {
            "deployments": {"reduced_data": {"active": False, "bip9": {"bit": 4, "status": "locked_in"}}}
        }

        result = self._status(deploy_info, {"subversion": "/Satoshi:29.0.0/"})
        self.assertEqual(result["state"], "locked_in")
        self.assertTrue(result["supported"])
        self.assertTrue(result["signaling"])
        self.assertEqual(result["source"], "getdeploymentinfo")

    def test_no_bip110_deployment_and_plain_subversion_reports_unsupported(self):
        deploy_info = {
            "deployments": {
                "taproot": {"type": "bip9", "active": True, "bip9": {"bit": 2, "status": "active"}},
            }
        }
        result = self._status(deploy_info, {"subversion": "/Satoshi:27.0.0/"})
        self.assertEqual(
            result,
            {"supported": False, "signaling": False, "state": "unsupported", "source": "subversion"},
        )

    def test_node_unreachable_reports_unknown(self):
        result = self._status(None, None)
        self.assertEqual(result, {"supported": False, "signaling": False, "state": "unknown", "source": "none"})


if __name__ == "__main__":
    unittest.main()
