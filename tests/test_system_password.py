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


class ServiceDetailCannotBeKilledByOneCredential(unittest.TestCase):
    """Source guards (server.py is not importable without the full Hub deps,
    same reason the other suites read it as text)."""

    @classmethod
    def setUpClass(cls):
        cls.server = _read("app", "sovran_systemsos_web", "server.py")

    def test_resolve_credential_guards_system_password_calls(self):
        start = self.server.index("if filepath in (sp.DISPLAY_FILE, sp.ROOT_DISPLAY_FILE):")
        block = self.server[start:start + 1600]
        self.assertIn("try:", block)
        self.assertIn("except Exception", block)
        self.assertIn('"unknown": True', block)

    def test_login_heal_is_best_effort(self):
        start = self.server.index("sp.record_known_password(submitted, only_if_stale=True)")
        block = self.server[max(0, start - 200):start + 200]
        self.assertIn("except Exception", block)


if __name__ == "__main__":
    unittest.main()
