"""
Dedicated LNURL service for Wallet Connections.

Runs as ``nwc-lnurl.service`` on 127.0.0.1:8181 (loopback only).
Caddy proxies the public Lightning Address domain's LNURL routes to this port.

Routes:
  GET /.well-known/lnurlp/{alias}
  GET /lnurlp/{alias}/callback?amount=<msat>

All error responses are safe for public consumption — raw Alby Hub bodies
and internal credentials are never returned to callers.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

from . import nwc_hub_manager as _mgr_mod

if TYPE_CHECKING:
    from .nwc_hub_manager import AlbyHubManager

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────

LNURL_BIND_HOST = "127.0.0.1"
LNURL_PORT = int(os.environ.get("NWC_LNURL_PORT", "8181"))
DOMAIN_FILE = "/var/lib/domains/lightning"

NWC_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

# ── Helpers ───────────────────────────────────────────────────────


def _read_domain() -> str | None:
    try:
        with open(DOMAIN_FILE, "r") as fh:
            raw = fh.read(256).strip().lower()
        # Basic validation: must look like a hostname
        if re.match(r"^[a-z0-9][a-z0-9.\-]{1,253}$", raw):
            return raw
    except OSError:
        pass
    return None


def _lnurl_discovery(alias: str, manager: "AlbyHubManager") -> tuple[dict, int]:
    alias = alias.strip().lower()
    if not NWC_ALIAS_RE.match(alias):
        return {"status": "ERROR", "reason": "Unknown Lightning Address alias"}, 404

    domain = _read_domain()
    if not domain:
        return {"status": "ERROR", "reason": "Lightning domain is not configured"}, 503

    try:
        app = manager.find_app_by_alias(alias)
    except _mgr_mod.AlbyHubError:
        return {"status": "ERROR", "reason": "Service temporarily unavailable"}, 503

    if app is None:
        return {"status": "ERROR", "reason": "Unknown Lightning Address alias"}, 404

    meta = _mgr_mod.AlbyHubManager._parse_metadata(app.get("metadata"))
    min_sendable = int(
        meta.get("lnurl_min_sendable_msat", _mgr_mod.NWC_MIN_SENDABLE_MSAT)
    )
    max_sendable = int(
        meta.get("lnurl_max_sendable_msat", _mgr_mod.NWC_MAX_SENDABLE_MSAT)
    )

    callback_alias = urllib.parse.quote(alias, safe="")
    callback = f"https://{domain}/lnurlp/{callback_alias}/callback"
    description = meta.get("lnurl_description") or f"Pay {alias}"
    metadata = json.dumps([["text/plain", description]], separators=(",", ":"))

    return {
        "tag": "payRequest",
        "callback": callback,
        "minSendable": min_sendable,
        "maxSendable": max_sendable,
        "metadata": metadata,
        "commentAllowed": 0,
    }, 200


def _lnurl_callback(
    alias: str, amount_str: str | None, manager: "AlbyHubManager"
) -> tuple[dict, int]:
    payload, status_code = _lnurl_discovery(alias, manager)
    if status_code != 200:
        return payload, status_code

    if amount_str is None:
        return {"status": "ERROR", "reason": "Missing amount parameter"}, 400
    if not re.match(r"^\d+$", amount_str):
        return {
            "status": "ERROR",
            "reason": "Amount must be an integer millisatoshi value",
        }, 400

    amount_msat = int(amount_str)
    min_sendable = int(payload["minSendable"])
    max_sendable = int(payload["maxSendable"])

    if amount_msat < min_sendable:
        return {
            "status": "ERROR",
            "reason": "Amount is below the minimum sendable value",
        }, 400
    if amount_msat > max_sendable:
        return {
            "status": "ERROR",
            "reason": "Amount is above the maximum sendable value",
        }, 400
    if amount_msat % 1000 != 0:
        return {
            "status": "ERROR",
            "reason": "Amount must be a whole-satoshi value",
        }, 400

    try:
        app = manager.find_app_by_alias(alias)
    except _mgr_mod.AlbyHubError:
        return {"status": "ERROR", "reason": "Service temporarily unavailable"}, 503

    if app is None:
        return {"status": "ERROR", "reason": "Unknown Lightning Address alias"}, 404

    meta = _mgr_mod.AlbyHubManager._parse_metadata(app.get("metadata"))
    description = meta.get("lnurl_description") or f"Pay {alias}"

    try:
        app_id = int(app["id"])
        invoice = manager.issue_invoice(app_id, amount_msat, description)
    except _mgr_mod.AlbyHubError:
        return {"status": "ERROR", "reason": "Invoice creation failed"}, 502

    return {"pr": invoice, "routes": []}, 200


# ── HTTP server ───────────────────────────────────────────────────


def _make_handler(manager: "AlbyHubManager") -> type:
    """Return a handler class bound to the given manager."""

    class LnurlHandler(BaseHTTPRequestHandler):
        _manager = manager

        def log_message(self, fmt: str, *args: object) -> None:
            logger.debug(f"LNURL {self.address_string()} {fmt % args}")

        def _send_json(self, status: int, body: dict) -> None:
            raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query)

            # /.well-known/lnurlp/{alias}
            m = re.fullmatch(
                r"/.well-known/lnurlp/([^/]+)", path
            )
            if m:
                alias = urllib.parse.unquote(m.group(1))
                payload, code = _lnurl_discovery(alias, self._manager)
                self._send_json(code, payload)
                return

            # /lnurlp/{alias}/callback
            m = re.fullmatch(r"/lnurlp/([^/]+)/callback", path)
            if m:
                alias = urllib.parse.unquote(m.group(1))
                amount_values = qs.get("amount")
                if not amount_values:
                    amount_str = None
                elif len(amount_values) != 1:
                    self._send_json(
                        400,
                        {
                            "status": "ERROR",
                            "reason": "A single amount parameter is required",
                        },
                    )
                    return
                else:
                    amount_str = amount_values[0]
                payload, code = _lnurl_callback(alias, amount_str, self._manager)
                self._send_json(code, payload)
                return

            self._send_json(404, {"status": "ERROR", "reason": "Not found"})

    return LnurlHandler


def run(
    host: str = LNURL_BIND_HOST,
    port: int = LNURL_PORT,
    manager: "AlbyHubManager | None" = None,
) -> None:
    """Start the blocking LNURL HTTP server."""
    if manager is None:
        manager = _mgr_mod.get_manager()
    handler_class = _make_handler(manager)
    server = HTTPServer((host, port), handler_class)
    logger.info("nwc-lnurl service listening on %s:%d", host, port)
    server.serve_forever()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run()


if __name__ == "__main__":
    main()
