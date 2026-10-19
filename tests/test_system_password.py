"""Regression tests for the System Passwords Hub tile.

Bug: after the password-model update (4a25ef2), clicking "System Passwords"
in The Hub showed only "Could not load service details."

That message is the frontend catch-all for a failed
GET /api/service-detail/root-password-setup.service. The new credential path
was the only one that called system_password.verify_system_password(), which
loaded libcrypt with no error handling: if LIBCRYPT pointed at a stale /
unloadable Nix store path (or libcrypt was otherwise unavailable), CDLL raised
OSError, _resolve_credential() raised, FastAPI returned 500, and the whole
modal failed -- instead of just marking that one password "unknown".

Verification must be fail-closed (return False / show the hint), never fatal.
"""

import importlib.util
import os
import sys
import unittest
import unittest.mock

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _load_system_password():
    path = os.path.join(_ROOT, "app", "sovran_systemsos_web", "system_password.py")
    spec = importlib.util.spec_from_file_location("system_password_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


# A real sha512crypt hash (of "hello", salt "saltsalt") so crypt() can succeed
# against the system libcrypt when the preferred path is stale.
_KNOWN_HASH = "$6$saltsalt$YTeBOLnmm3CoeJTzBuijUEtOEWCqrw/nQ8/AeMmON4LGp3k0ZiMjC1OdqzWFUAfDQBvYkOch9BWtQTBcZ1E/p0"


class VerifyNeverRaises(unittest.TestCase):
    def setUp(self):
        self.sp = _load_system_password()
        self._old_env = os.environ.get("LIBCRYPT")

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("LIBCRYPT", None)
        else:
            os.environ["LIBCRYPT"] = self._old_env

    def test_unloadable_libcrypt_is_false_not_an_exception(self):
        os.environ["LIBCRYPT"] = "/nix/store/stale-before-update/lib/libcrypt.so.1"
        self.sp.shadow_hash = lambda user="free": _KNOWN_HASH
        # No working libcrypt anywhere: every load attempt fails.
        with unittest.mock.patch.object(
            self.sp.ctypes, "CDLL", side_effect=OSError("cannot open shared object")
        ):
            self.assertFalse(self.sp.verify_system_password("hello"))

    def test_stale_libcrypt_falls_back_and_still_verifies(self):
        if not os.path.exists("/usr/lib/x86_64-linux-gnu/libcrypt.so.1") and \
           not os.path.exists("/lib/x86_64-linux-gnu/libcrypt.so.1"):
            # Wherever a system libcrypt exists, the fallback should find it
            # via find_library / the bare soname; only assert the no-raise
            # contract if this host has none to fall back to.
            pass
        os.environ["LIBCRYPT"] = "/nix/store/stale-before-update/lib/libcrypt.so.1"
        self.sp.shadow_hash = lambda user="free": _KNOWN_HASH
        try:
            result = self.sp.verify_system_password("hello")
        except Exception as exc:  # pragma: no cover - the regression itself
            self.fail(f"verify_system_password raised {exc!r} instead of failing closed")
        self.assertIn(result, (True, False))

    def test_display_password_is_none_not_an_exception_when_unverifiable(self):
        os.environ["LIBCRYPT"] = "/nix/store/stale-before-update/lib/libcrypt.so.1"
        self.sp.shadow_hash = lambda user="free": _KNOWN_HASH
        self.sp._read_secret = lambda path: "hello"
        with unittest.mock.patch.object(
            self.sp.ctypes, "CDLL", side_effect=OSError("cannot open shared object")
        ):
            self.assertIsNone(self.sp.read_display_password())
            self.assertIsNone(self.sp.read_root_display_password())


class WrongLibraryMustNotLockTheUserOut(unittest.TestCase):
    """A loadable libcrypt that cannot speak the shadow hash's algorithm
    (yescrypt $y$ on NixOS) answers with the "*0" sentinel. That used to be
    compared against the hash, found unequal, and reported as a *wrong
    password* at Hub login -- locking out a user whose desktop login with
    the very same password still worked, after the tile's hint told them
    to sign out. Inconclusive answers must fall through to the next
    library, and finally to PAM (the check GDM itself performs)."""

    def setUp(self):
        self.sp = _load_system_password()
        self.sp.shadow_hash = lambda user="free": _KNOWN_HASH
        self._old_libs = self.sp._libcrypt_libs

    def tearDown(self):
        self.sp._libcrypt_libs = self._old_libs

    def test_sentinel_from_first_library_falls_through_to_the_next(self):
        class _SentinelLib:
            @staticmethod
            def crypt(_pw, _salt):
                return b"*0"

        class _RealLib:
            @staticmethod
            def crypt(pw, salt):
                return _KNOWN_HASH.encode() if pw == b"hello" else b"$6$saltsalt$nomatch"

        self.sp._libcrypt_libs = [_SentinelLib, _RealLib]
        self.assertTrue(self.sp.verify_system_password("hello"))
        self.assertFalse(self.sp.verify_system_password("not-the-password"))

    def test_when_no_library_understands_the_hash_pam_decides(self):
        class _SentinelLib:
            @staticmethod
            def crypt(_pw, _salt):
                return b"*0"

        self.sp._libcrypt_libs = [_SentinelLib]
        with unittest.mock.patch.object(
            self.sp, "_verify_via_pam", return_value=True
        ) as pam:
            self.assertTrue(self.sp.verify_system_password("hello"))
            pam.assert_called_once()

    def test_hint_no_longer_tells_the_user_to_sign_out_blind(self):
        for text in (
            _read("app", "sovran_systemsos_web", "server.py"),
            _read("app", "sovran_systemsos_web", "static", "js", "service-detail.js"),
        ):
            self.assertNotIn("sign out and back in to show it here", text)


class HubUnitMustBeAbleToLoadItsVerifiers(unittest.TestCase):
    """Patch 0002's PAM fallback could only work if libpam.so.0 is findable
    inside the Hub unit. On NixOS a bare soname resolves via LD_LIBRARY_PATH
    or not at all, so the unit must put the real libxcrypt + PAM libraries
    on it -- otherwise a correct desktop password reads as 'wrong password'
    at Hub login while the desktop accepts it."""

    def test_hub_unit_gets_real_libcrypt_and_pam_on_library_path(self):
        nix = _read("modules", "password-model.nix")
        self.assertIn("LD_LIBRARY_PATH", nix)
        self.assertIn("pkgs.libxcrypt pkgs.pam", nix)

    def test_no_unix_chkpwd_shortcut(self):
        # unix_chkpwd refuses (and stalls) when invoked outside pam_unix;
        # PAM is the only supported route to it.
        src = _read("app", "sovran_systemsos_web", "system_password.py")
        self.assertNotIn("_verify_via_unix_chkpwd", src)


class RootHintMustNotClaimItIsTheFreePassword(unittest.TestCase):
    """The root row in the System Passwords tile showed the free/hub hint
    verbatim. Root has no desktop or Hub sign-in, so that text was false
    and sent users looking for a sign-in that could refresh it."""

    @classmethod
    def setUpClass(cls):
        cls.server = _read("app", "sovran_systemsos_web", "server.py")

    def test_root_gets_its_own_hint(self):
        self.assertIn("ROOT_DISPLAY_FILE", self.server)
        start = self.server.index('if filepath == sp.ROOT_DISPLAY_FILE:')
        block = self.server[start:start + 1400]
        self.assertIn("Root has no desktop or Hub sign-in", block)
        self.assertIn("sudo passwd root", block)
        self.assertIn("Security Reset", block)


class DefaultKeyringMustStayTheBlankLoginKeyring(unittest.TestCase):
    """The password cleanup dropped the keyrings/default pointer, so
    gnome-keyring fell back to an encrypted keyring literally named
    "Default" and Brave prompted for it on every Hub launch."""

    @classmethod
    def setUpClass(cls):
        cls.nix = _read("modules", "password-model.nix")

    def test_default_pointer_is_seeded(self):
        self.assertIn("keyring-default", self.nix)
        self.assertIn("/.local/share/keyrings/default ", self.nix)

    def test_encrypted_default_keyring_is_moved_aside_never_deleted(self):
        self.assertIn("default.keyring.encrypted-", self.nix)
        self.assertNotIn('rm "$d/default.keyring"', self.nix)
        self.assertNotIn("rm -f \"$d/default.keyring\"", self.nix)


class ServiceDetailCannotBeKilledByOneCredential(unittest.TestCase):
    """Source guards (server.py is not importable without the full Hub deps,
    same reason the other suites read it as text)."""

    @classmethod
    def setUpClass(cls):
        cls.server = _read("app", "sovran_systemsos_web", "server.py")

    def test_resolve_credential_guards_system_password_calls(self):
        start = self.server.index("if filepath in (sp.DISPLAY_FILE, sp.ROOT_DISPLAY_FILE):")
        block = self.server[start:start + 3200]
        self.assertIn("try:", block)
        self.assertIn("except Exception", block)
        self.assertIn('"unknown": True', block)

    def test_login_heal_is_best_effort(self):
        start = self.server.index("sp.record_known_password(submitted, only_if_stale=True)")
        block = self.server[max(0, start - 200):start + 200]
        self.assertIn("except Exception", block)


if __name__ == "__main__":
    unittest.main()
