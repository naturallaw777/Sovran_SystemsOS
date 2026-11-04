"""Regression tests for the Tech Support modal's SSH power control.

The bug: once a support session ended (expired after 24h, or the modal was
reopened after it ended), the Hub landed on the "SSH on, no active session"
screen, which had no Disable SSH button. The only way to reach a Disable SSH
control was to grant support access again and then end the session. The user
could not turn SSH off on their own.

The fix has two halves, both guarded here:

  * Frontend — a Disable SSH control is available whenever SSH is on,
    independent of the support session state, and the active-session screen
    offers a one-click "end session and disable SSH".
  * Backend — disabling the sshd feature also revokes any active support
    session, so the support key never outlives the service it rides on.

Like the other Hub tests, the wiring is asserted from source so it always
runs; the backend helper is additionally exercised directly when server.py is
importable (it needs fastapi and the sovran_nwc module from the Sovran_Bitcoin
flake, so those tests skip rather than fail otherwise).

Nothing here reboots, rebuilds, touches real SSH keys, or uses the network.
"""

import os
import re
import sys
import types
import unittest
from unittest import mock

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_APP_PARENT = os.path.join(_REPO_ROOT, "app")
if _APP_PARENT not in sys.path:
    sys.path.insert(0, _APP_PARENT)


def _read(*parts):
    with open(os.path.join(_REPO_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _support_js():
    return _read("app", "sovran_systemsos_web", "static", "js", "support.js")


def _server_source():
    return _read("app", "sovran_systemsos_web", "server.py")


def _js_function(src, name):
    """Return the source of a top-level named function in support.js.

    Functions in this file are top-level and separated by a newline followed
    by the next named declaration, so we slice from this declaration to the
    next one. Anonymous ``function(...)`` callbacks inside the body do not
    match the named-declaration pattern and are kept in the slice.
    """
    m = re.search(r"(?:async\s+)?function\s+" + re.escape(name) + r"\s*\(", src)
    assert m, f"function {name} not found"
    nxt = re.search(r"\n(?:async\s+)?function\s+\w+\s*\(", src[m.end():])
    end = m.end() + nxt.start() if nxt else len(src)
    return src[m.start():end]


# ── Frontend wiring (always runs) ─────────────────────────────────────────────

class InactiveScreenHasDisableSshd(unittest.TestCase):
    """The reported bug: SSH on + no active session must offer Disable SSH."""

    def test_disable_button_is_present(self):
        body = _js_function(_support_js(), "renderSupportInactive")
        self.assertIn('id="btn-sshd-disable"', body)
        self.assertIn("Disable SSH", body)

    def test_disable_button_is_wired_to_the_handler(self):
        body = _js_function(_support_js(), "renderSupportInactive")
        self.assertIn('getElementById("btn-sshd-disable")', body)
        self.assertIn("disableSshd", body)

    def test_it_does_not_require_granting_support_first(self):
        # The control must sit outside the "enable support access" flow, i.e.
        # it is rendered unconditionally, not gated on a session being active.
        body = _js_function(_support_js(), "renderSupportInactive")
        self.assertIn("do not need an active support session", body)


class ActiveScreenOffersFullLockdown(unittest.TestCase):
    """While a session is active the user can end it and disable SSH in one click."""

    def test_combined_end_and_disable_button(self):
        body = _js_function(_support_js(), "renderSupportActive")
        self.assertIn('id="btn-support-disable-sshd"', body)
        self.assertIn("disableSshd", body)

    def test_end_session_only_option_is_still_available(self):
        body = _js_function(_support_js(), "renderSupportActive")
        self.assertIn('id="btn-support-disable"', body)
        self.assertIn("disableSupport", body)


class DisableSshdCleansUpTheSession(unittest.TestCase):

    def test_stops_the_session_timers(self):
        body = _js_function(_support_js(), "disableSshd")
        self.assertIn("stopSupportTimer()", body)
        self.assertIn("stopWalletUnlockTimer()", body)

    def test_toggles_the_sshd_feature_off(self):
        body = _js_function(_support_js(), "disableSshd")
        self.assertIn('feature: "sshd", enabled: false', body)


class ModalLifecycleCancelsTheRebuildPoll(unittest.TestCase):

    def test_close_stops_the_sshd_poll(self):
        body = _js_function(_support_js(), "closeSupportModal")
        self.assertIn("stopSshdPoll()", body)

    def test_open_stops_a_stale_sshd_poll(self):
        body = _js_function(_support_js(), "openSupportModal")
        self.assertIn("stopSshdPoll()", body)

    def test_state_declares_the_poll_timer(self):
        state = _read("app", "sovran_systemsos_web", "static", "js", "state.js")
        self.assertIn("_sshdPollTimer", state)


# ── Backend wiring (always runs) ──────────────────────────────────────────────

def _toggle_source():
    src = _server_source()
    start = src.index("async def api_features_toggle")
    end = src.index("@app.", start)
    return src[start:end]


class SshdDisableRevokesSupportWiring(unittest.TestCase):

    def test_the_disable_branch_revokes_support_for_sshd(self):
        toggle = _toggle_source()
        else_idx = toggle.index("    else:\n")
        false_idx = toggle.index("features[req.feature] = False", else_idx)
        block = toggle[else_idx:false_idx]
        self.assertIn('req.feature == "sshd"', block)
        self.assertIn("_revoke_support_for_sshd_disable", block)

    def test_the_revoke_helper_exists(self):
        self.assertIn("def _revoke_support_for_sshd_disable(", _server_source())


# ── Backend helper, exercised directly when importable ───────────────────────

# server.py imports sovran_nwc from the Sovran_Bitcoin flake, which is not part
# of this repo. Provide a minimal stub when it is absent so the module can be
# imported for testing; only two constants are read at import time.
try:
    import sovran_nwc  # noqa: F401
except Exception:
    _pkg = types.ModuleType("sovran_nwc")
    _mgr = types.ModuleType("sovran_nwc.nwc_hub_manager")
    _mgr.NWC_MIN_SENDABLE_MSAT = 1
    _mgr.NWC_MAX_SENDABLE_MSAT = 10 ** 9

    class _AlbyHubError(Exception):
        pass

    _mgr.AlbyHubError = _AlbyHubError
    _mgr.get_manager = lambda: None
    _pkg.nwc_hub_manager = _mgr
    sys.modules["sovran_nwc"] = _pkg
    sys.modules["sovran_nwc.nwc_hub_manager"] = _mgr

try:
    from sovran_systemsos_web import server  # noqa: E402
    HAVE_SERVER = True
except Exception:
    HAVE_SERVER = False


@unittest.skipUnless(HAVE_SERVER, "server.py is not importable here")
class RevokeSupportForSshdDisable(unittest.TestCase):

    def test_noop_when_no_session_is_active(self):
        with mock.patch.object(server, "_is_support_active", return_value=False), \
             mock.patch.object(server, "_disable_support") as dis, \
             mock.patch.object(server, "_log_support_audit") as audit:
            result = server._revoke_support_for_sshd_disable()
        self.assertFalse(result)
        dis.assert_not_called()
        audit.assert_not_called()

    def test_revokes_and_verifies_when_a_session_is_active(self):
        with mock.patch.object(server, "_is_support_active", return_value=True), \
             mock.patch.object(server, "_disable_support", return_value=True) as dis, \
             mock.patch.object(server, "_verify_support_removed", return_value=True), \
             mock.patch.object(server, "_log_support_audit") as audit:
            result = server._revoke_support_for_sshd_disable()
        self.assertTrue(result)
        dis.assert_called_once()
        audit.assert_called_once()
        self.assertEqual(audit.call_args[0][0], "SUPPORT_REVOKED_SSHD_OFF")

    def test_reports_unverified_when_the_key_cannot_be_removed(self):
        with mock.patch.object(server, "_is_support_active", return_value=True), \
             mock.patch.object(server, "_disable_support", return_value=False), \
             mock.patch.object(server, "_verify_support_removed", return_value=False), \
             mock.patch.object(server, "_log_support_audit") as audit:
            result = server._revoke_support_for_sshd_disable()
        self.assertFalse(result)
        # The attempt is still audited even when verification fails.
        audit.assert_called_once()
        self.assertIn("key_removed_verified=False", audit.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
