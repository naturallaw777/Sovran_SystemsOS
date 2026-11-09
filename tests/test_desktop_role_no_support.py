"""Desktop Only has no Tech Support tile/window and no SSH Remote Access.

The removal is spread across four layers, and every one of them is guarded
here so a future refactor cannot quietly reintroduce the feature:

  * Nix config   — the Hub config emits no Tech Support service; the sshd
                   feature is forced off; the support account is not built.
  * Hub backend  — role maps, a guard on every /api/support endpoint, the
                   feature-toggle allowlist, and startup cleanup of stale
                   overrides/session files.
  * Frontend     — no entry point can open the window or toggle SSH.
  * Docs         — README and SECURITY.md state the role difference.

Like the other nix-file checks these read the shipped source files: nothing is
run, nothing touches the network, no SSH keys or system paths are modified.
Server-backed tests only run where server.py is importable (it needs fastapi
and the sovran_nwc module from the Sovran_Bitcoin flake).
"""

import ast
import asyncio
import os
import re
import sys
import unittest
from unittest import mock

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_APP_PARENT = os.path.join(_ROOT, "app")
if _APP_PARENT not in sys.path:
    sys.path.insert(0, _APP_PARENT)


def _read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _without_comments(src):
    return "\n".join(line for line in src.splitlines()
                     if not line.lstrip().startswith("#"))


def _server_ast():
    return ast.parse(_read("app", "sovran_systemsos_web", "server.py"))


def _fn(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


def _fn_source(tree, name, src):
    return ast.get_source_segment(src, _fn(tree, name)) or ""


def _module_value(tree, name):
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        if target == name:
            return ast.literal_eval(value)
    raise AssertionError(f"module constant {name} not found")


def _js_function(src, name):
    """Slice a top-level named JS function (same convention as the other tests)."""
    m = re.search(r"(?:async\s+)?function\s+" + re.escape(name) + r"\s*\(", src)
    assert m, f"function {name} not found"
    nxt = re.search(r"\n(?:async\s+)?function\s+\w+\s*\(", src[m.end():])
    end = m.end() + nxt.start() if nxt else len(src)
    return src[m.start():end]


# ── Nix layer ────────────────────────────────────────────────────────────────

class NixRoleGates(unittest.TestCase):

    def test_support_tile_is_not_emitted_on_desktop(self):
        src = _read("modules", "core", "sovran-hub.nix")
        section = src[src.index("── Support ("):]
        section = section[:section.index("];") + 2]
        self.assertIn("name = \"Tech Support\"", section)
        self.assertIn("lib.optionals (!cfg.roles.desktop)", section)
        # The tile must not be in an unconditional list any more.
        self.assertNotIn("++ [", section)
        self.assertNotIn("Support (always present)", src)

    def test_other_roles_still_get_the_tile(self):
        code = _without_comments(_read("modules", "core", "sovran-hub.nix"))
        self.assertRegex(code, r"lib\.optionals\s+\(!cfg\.roles\.desktop\)")

    def test_sshd_is_forced_off_on_desktop(self):
        code = _without_comments(_read("modules", "core", "role-logic.nix"))
        block = code[code.index("lib.mkIf config.sovran_systemsOS.roles.desktop"):]
        block = block[:block.index("lib.mkIf config.sovran_systemsOS.roles.node")]
        self.assertRegex(block, r"sshd\s*=\s*lib\.mkForce\s+false\s*;")

    def test_support_account_is_not_built_on_desktop(self):
        src = _read("modules", "core", "tech-support.nix")
        self.assertIn("lib.mkIf (!config.sovran_systemsOS.roles.desktop)", src)
        # Still defined for the roles that do have Tech Support.
        self.assertIn("users.users.sovran-support", src)
        self.assertLess(src.index("lib.mkIf (!config.sovran_systemsOS.roles.desktop)"),
                        src.index("users.users.sovran-support"))


# ── Hub backend layer ────────────────────────────────────────────────────────

class HubRoleConfig(unittest.TestCase):

    def setUp(self):
        self.src = _read("app", "sovran_systemsos_web", "server.py")
        self.tree = _server_ast()

    def test_desktop_categories_and_features_exclude_support(self):
        cats = _module_value(self.tree, "ROLE_CATEGORIES")
        feats = _module_value(self.tree, "ROLE_FEATURES")
        self.assertNotIn("support", cats["desktop"])
        self.assertIn("feature-manager", cats["desktop"])
        self.assertNotIn("sshd", feats["desktop"])
        self.assertIn("rdp", feats["desktop"])

    def test_other_roles_keep_support_and_ssh(self):
        cats = _module_value(self.tree, "ROLE_CATEGORIES")
        feats = _module_value(self.tree, "ROLE_FEATURES")
        self.assertIn("support", cats["node"])
        self.assertIn("sshd", feats["node"])
        self.assertIsNone(cats["server_plus_desktop"])
        self.assertIsNone(feats["server_plus_desktop"])

    def test_support_role_helper_excludes_only_desktop(self):
        body = _fn_source(self.tree, "_support_role_available", self.src)
        self.assertIn('load_config().get("role", "server_plus_desktop") != "desktop"', body)

    def test_guard_returns_not_found(self):
        body = _fn_source(self.tree, "_require_support_role", self.src)
        self.assertIn("_support_role_available()", body)
        self.assertIn("status_code=404", body)

    def test_every_support_endpoint_is_guarded(self):
        guarded = 0
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            paths = [
                d.args[0].value for d in node.decorator_list
                if isinstance(d, ast.Call) and d.args
                and isinstance(d.args[0], ast.Constant)
                and isinstance(d.args[0].value, str)
                and d.args[0].value.startswith("/api/support/")
            ]
            if not paths:
                continue
            guarded += 1
            has_guard = any(
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)
                and stmt.value.func.id == "_require_support_role"
                for stmt in node.body
            )
            self.assertTrue(has_guard, f"{node.name} ({paths}) has no Desktop Only guard")
        self.assertEqual(guarded, 6, "expected all six /api/support endpoints")

    def test_feature_toggle_enforces_the_role_allowlist(self):
        body = _fn_source(self.tree, "api_features_toggle", self.src)
        self.assertIn("ROLE_FEATURES.get(role)", body)
        self.assertIn("allowed_features is not None and req.feature not in allowed_features", body)
        self.assertIn("status_code=404", body)

    def test_sshd_status_cannot_be_faked_by_a_stale_override(self):
        body = _fn_source(self.tree, "_is_sshd_feature_enabled", self.src)
        self.assertIn("if not _support_role_available():", body)
        self.assertIn("return False", body)

    def test_startup_removes_stale_sshd_override_and_session_state(self):
        cleanup = _fn_source(self.tree, "_startup_desktop_role_cleanup", self.src)
        self.assertIn("_migrate_strip_desktop_sshd", cleanup)
        self.assertIn("_cleanup_desktop_support_state", cleanup)
        strip = _fn_source(self.tree, "_migrate_strip_desktop_sshd", self.src)
        self.assertIn("if _support_role_available():", strip)
        self.assertIn('features.pop("sshd", None)', strip)
        self.assertIn("_write_hub_overrides", strip)
        purge = _fn_source(self.tree, "_cleanup_desktop_support_state", self.src)
        self.assertIn("SUPPORT_USER_AUTH_KEYS", purge)
        self.assertIn("SUPPORT_STATUS_FILE", purge)
        self.assertIn("shutil.rmtree(SUPPORT_USER_HOME", purge)

    def test_startup_support_timers_do_not_run_on_desktop(self):
        body = _fn_source(self.tree, "_startup_security_migrations", self.src)
        condition = body.index("if _support_role_available():")
        self.assertLess(condition, body.index("_expire_support_if_stale"))
        self.assertLess(condition, body.index("_reconcile_expiry_timer"))


class DesktopHasNoSshAtAll(unittest.TestCase):
    """Every SSH remnant is gone from Desktop Only, opt-in via custom.nix."""

    def test_no_loopback_sshd(self):
        code = _without_comments(_read("modules", "core", "sshd-localhost.nix"))
        self.assertRegex(
            code, r"lib\.mkIf\s+\(!config\.sovran_systemsOS\.roles\.desktop\)")
        # The loopback sshd still exists for the other two roles.
        self.assertIn("openFirewall = lib.mkDefault false;", code)

    def test_no_factory_ssh_key_bootstrap(self):
        code = _without_comments(_read("modules", "core", "ssh-bootstrap.nix"))
        self.assertRegex(
            code, r"lib\.mkIf\s+\(userExists\s+&&\s+!config\.sovran_systemsOS\.roles\.desktop\)")

    def test_no_ssh_passphrase_credential(self):
        src = _read("modules", "core", "sovran-hub.nix")
        block = src[src.index('name = "System Passwords"'):]
        block = block[:block.index("]; }") + 4]
        self.assertIn("lib.optionals (!cfg.roles.desktop)", block)
        self.assertLess(block.index("lib.optionals (!cfg.roles.desktop)"),
                        block.index("SSH Passphrase"))

    def test_remote_deploy_mode_is_rejected(self):
        code = _without_comments(_read("modules", "core", "remote-deploy.nix"))
        self.assertRegex(code, r"assertions\s*=\s*\[\{")
        self.assertRegex(
            code, r"assertion\s*=\s*!config\.sovran_systemsOS\.roles\.desktop")
        # Other roles keep the deploy path.
        self.assertRegex(code, r"lib\.mkIf\s+cfg\.enable")

    def test_headless_installer_rejects_deploy_on_desktop(self):
        src = _read("iso", "sovran-install-headless.sh")
        self.assertIn("Remote deploy/SSH is not available with --role desktop", src)
        self.assertIn('[[ "$ROLE" == "desktop"', src)
        self.assertIn("--deploy-key/--headscale-*", src)

    def test_stock_ssh_module_is_documented_in_custom_template(self):
        src = _read("custom.template.nix")
        self.assertIn("# services.openssh = {", src)
        self.assertIn("#   enable = true;", src)
        self.assertIn("PasswordAuthentication = false;", src)
        self.assertIn("Desktop Only ships none by default", src)


# ── Frontend layer ───────────────────────────────────────────────────────────

class FrontendGuards(unittest.TestCase):

    def test_support_modal_cannot_open_on_desktop(self):
        src = _read("app", "sovran_systemsos_web", "static", "js", "support.js")
        for name in ("openSupportModal", "enableSshd", "disableSshd"):
            self.assertIn('_currentRole === "desktop"', _js_function(src, name),
                          f"{name} lacks a Desktop Only guard")
        # The shared dialog still serves Manual Backup and Security.
        self.assertIn("function openBackupModal", src)

    def test_feature_toggle_cannot_enable_ssh_on_desktop(self):
        src = _read("app", "sovran_systemsos_web", "static", "js", "features.js")
        body = _js_function(src, "performFeatureToggle")
        self.assertIn('featId === "sshd"', body)
        self.assertIn('_currentRole === "desktop"', body)

    def test_support_tiles_are_never_rendered_on_desktop(self):
        src = _read("app", "sovran_systemsos_web", "static", "js", "tiles.js")
        body = _js_function(src, "renderSidebarSupport")
        self.assertIn('_currentRole === "desktop"', body)
        self.assertIn("visibleSupportServices", body)


# ── Docs ─────────────────────────────────────────────────────────────────────

class DocsDescribeTheRoleDifference(unittest.TestCase):

    def test_readme(self):
        text = " ".join(_read("README.md").split()).replace("**", "")
        self.assertIn("Desktop Only: Tech Support is not available on this role", text)
        self.assertIn("SSH on Desktop Only: that role ships no SSH daemon at all", text)
        self.assertIn("services.openssh", text)

    def test_security_policy(self):
        text = " ".join(_read("SECURITY.md").split()).replace("**", "")
        self.assertIn("Tech Support does not exist on Desktop Only", text)
        self.assertIn("Desktop Only ships no SSH at all", text)
        self.assertIn("opens no TCP port", text)


# ── Server-backed checks (optional, as in test_support_ssh_control.py) ────────

try:
    from sovran_systemsos_web import server  # noqa: E402
    HAVE_SERVER = True
except Exception:
    HAVE_SERVER = False


@unittest.skipUnless(HAVE_SERVER, "server.py is not importable here")
class ServerBehaviourOnDesktop(unittest.TestCase):

    def setUp(self):
        self.desktop = mock.patch.object(server, "load_config", return_value={"role": "desktop"})
        self.desktop.start()
        self.addCleanup(self.desktop.stop)

    def test_guard_raises_404(self):
        with self.assertRaises(server.HTTPException) as ctx:
            server._require_support_role()
        self.assertEqual(ctx.exception.status_code, 404)

    def test_support_status_is_unavailable(self):
        with mock.patch.object(server, "_is_support_active") as active:
            with self.assertRaises(server.HTTPException) as ctx:
                asyncio.run(server.api_support_status())
            active.assert_not_called()
        self.assertEqual(ctx.exception.status_code, 404)

    def test_sshd_override_cannot_report_ssh_as_on(self):
        with mock.patch.object(server, "_read_hub_overrides",
                               return_value=({"sshd": True}, None, None, None)) as read:
            self.assertFalse(server._is_sshd_feature_enabled())
            read.assert_not_called()

    def test_sshd_toggle_is_rejected_before_any_write(self):
        req = server.FeatureToggleRequest(feature="sshd", enabled=True)
        with mock.patch.object(server, "_read_hub_overrides") as read, \
             mock.patch.object(server, "_write_hub_overrides") as write:
            with self.assertRaises(server.HTTPException) as ctx:
                asyncio.run(server.api_features_toggle(req))
            read.assert_not_called()
            write.assert_not_called()
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
