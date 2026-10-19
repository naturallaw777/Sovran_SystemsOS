"""system_password.py -- the one place that knows about the 'free' (and root) password.

Rules
  * /etc/shadow is the ONLY source of truth for authentication: Hub login == GDM login.
  * /var/lib/secrets/free-password (0600 root) is a DISPLAY copy for the Hub's credentials
    view. Only set_free_password() writes it, and it is verified against /etc/shadow before
    it is shown, so the Hub can never show a stale password.
  * Legacy / unknown-password machines go through the *migration* flow the onboarding already
    has: generate a new diceware password, show it, and apply it on acknowledgement. Until
    then the old password keeps working everywhere (shadow is untouched).
  * No keyring code anywhere: the GNOME login keyring is decoupled from the login password
    (blank-password keyring, pam_gnome_keyring off), so nothing has to be wiped or re-keyed.

Needs libxcrypt. On NixOS the Hub service gets:  environment.LIBCRYPT = "${pkgs.libxcrypt}/lib/libcrypt.so.1"
"""
from __future__ import annotations

import ctypes
import ctypes.util
import hmac
import os
import secrets
import subprocess
import threading
from typing import Callable

USER = "free"
SECRETS_DIR = "/var/lib/secrets"
DISPLAY_FILE = f"{SECRETS_DIR}/free-password"
ROOT_DISPLAY_FILE = f"{SECRETS_DIR}/root-password"
MIGRATION_FILE = f"{SECRETS_DIR}/free-password-migration-newpass"   # same path the onboarding UI already uses
LIVE_ISO_MARKER = "/iso"   # NixOS live media mounts the image here; never start a migration there

_lock = threading.Lock()   # crypt() returns a static buffer; serialise calls
_libcrypt_libs = None      # list of every loadable libcrypt, in preference order


# ── low level ──────────────────────────────────────────────────────────────

def _crypt_libs() -> list:
    """Every libcrypt we can load, best first ($LIBCRYPT, then system ones).

    More than one library can be *loadable* while only one can actually
    verify the system's hashes: e.g. a bare-soname libcrypt that loads fine
    but returns the "*0" failure sentinel for yescrypt ($y$) hashes, which
    NixOS uses by default. Verification therefore tries each library until
    one gives a conclusive answer instead of trusting the first that loads.
    A stale $LIBCRYPT (Nix store path from before an update / GC) is skipped,
    never fatal.
    """
    global _libcrypt_libs
    if _libcrypt_libs is None:
        candidates: list[str] = []
        env_path = os.environ.get("LIBCRYPT")
        if env_path:
            candidates.append(env_path)
        found = ctypes.util.find_library("crypt")
        if found:
            candidates.append(found)
        candidates += ["libcrypt.so.1", "libcrypt.so.2", "libcrypt.so"]
        libs = []
        seen = set()
        for path in candidates:
            try:
                lib = ctypes.CDLL(path)
                lib.crypt.restype = ctypes.c_char_p
                lib.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
            except (OSError, AttributeError):
                continue
            if lib._handle in seen:   # same library reached by two names
                continue
            seen.add(lib._handle)
            libs.append(lib)
        _libcrypt_libs = libs
    return _libcrypt_libs


def _crypt():
    libs = _crypt_libs()
    if not libs:
        raise OSError("could not load any libcrypt")
    return libs[0]


# ── PAM fallback ───────────────────────────────────────────────────────────
# crypt() only answers conclusively when a loaded library understands the
# shadow hash's algorithm. When none does (sentinel replies, no library),
# ask PAM instead -- it is literally the check GDM/sudo perform, so a
# password the desktop accepts can never be refused by the Hub just
# because libcrypt could not speak its hash format.

_PAM_SERVICE_CANDIDATES = ("login", "system-auth", "gdm-password", "sudo")


class _PamMessage(ctypes.Structure):
    _fields_ = [("msg_style", ctypes.c_int), ("msg", ctypes.c_char_p)]


class _PamResponse(ctypes.Structure):
    _fields_ = [("resp", ctypes.c_char_p), ("resp_retcode", ctypes.c_int)]


_PAM_CONV_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_int,
    ctypes.POINTER(ctypes.POINTER(_PamMessage)),
    ctypes.POINTER(ctypes.POINTER(_PamResponse)), ctypes.c_void_p,
)


class _PamConv(ctypes.Structure):
    _fields_ = [("conv", _PAM_CONV_FUNC), ("appdata_ptr", ctypes.c_void_p)]


def _verify_via_pam(password: str, user: str) -> bool | None:
    """True/False if PAM gave a verdict, None if PAM is unavailable here."""
    try:
        libpam = None
        for candidate in dict.fromkeys(
                filter(None, [ctypes.util.find_library("pam"), "libpam.so.0"])):
            try:
                libpam = ctypes.CDLL(candidate)
                break
            except OSError:
                continue
        if libpam is None:
            return None
        libc = ctypes.CDLL(None)
        libc.calloc.restype = ctypes.c_void_p
        libc.calloc.argtypes = [ctypes.c_size_t, ctypes.c_size_t]
        libc.strdup.restype = ctypes.c_void_p
        libc.strdup.argtypes = [ctypes.c_char_p]
        libpam.pam_start.restype = ctypes.c_int
        libpam.pam_start.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                     ctypes.POINTER(_PamConv), ctypes.POINTER(ctypes.c_void_p)]
        libpam.pam_authenticate.restype = ctypes.c_int
        libpam.pam_authenticate.argtypes = [ctypes.c_void_p, ctypes.c_int]
        libpam.pam_end.restype = ctypes.c_int
        libpam.pam_end.argtypes = [ctypes.c_void_p, ctypes.c_int]

        pw_bytes = password.encode()

        def _conv(num_msg, msg, resp, _appdata):
            if num_msg <= 0:
                return 1  # PAM_CONV_ERR
            responses = libc.calloc(num_msg, ctypes.sizeof(_PamResponse))
            if not responses:
                return 1
            resp_array = ctypes.cast(responses, ctypes.POINTER(_PamResponse))
            for i in range(num_msg):
                style = msg[i].contents.msg_style
                if style in (1, 2):  # PROMPT_ECHO_OFF / PROMPT_ECHO_ON
                    resp_array[i].resp = ctypes.cast(libc.strdup(pw_bytes), ctypes.c_char_p)
            resp[0] = ctypes.cast(responses, ctypes.POINTER(_PamResponse))
            return 0  # PAM_SUCCESS

        conv_fn = _PAM_CONV_FUNC(_conv)   # keep alive for the pam_* calls
        conv = _PamConv(conv=conv_fn, appdata_ptr=None)
        for service in _PAM_SERVICE_CANDIDATES:
            handle = ctypes.c_void_p()
            if libpam.pam_start(service.encode(), user.encode(),
                                ctypes.byref(conv), ctypes.byref(handle)) != 0:
                continue
            try:
                return libpam.pam_authenticate(handle, 0) == 0
            finally:
                libpam.pam_end(handle, 0)
        return None
    except Exception:
        return None


def shadow_hash(user: str = USER) -> str | None:
    """Password hash from /etc/shadow, or None if the account has none / is locked."""
    try:
        with open("/etc/shadow", encoding="utf-8") as f:
            for line in f:
                fields = line.rstrip("\n").split(":")
                if fields[0] == user:
                    h = fields[1]
                    return h if h and h[0] not in "!*" else None
    except OSError:
        return None
    return None


def verify_system_password(password: str, user: str = USER) -> bool:
    """True iff `password` is the account's current login password
    (yescrypt, sha512crypt, ... whatever chpasswd produced)."""
    h = shadow_hash(user)
    if not h or not password:
        return False
    # Try every loadable libcrypt. A reply of None or "*0"/"*1" is a library
    # saying "I don't understand this hash" (e.g. no yescrypt support) --
    # inconclusive, NOT a wrong password -- so keep trying, and finally ask
    # PAM. A real hash that simply doesn't match is conclusive: wrong
    # password. Nothing here may raise: raising crashed the System
    # Passwords tile ("Could not load service details."), and returning a
    # false "wrong password" at login would lock a user whose desktop
    # login still works out of the Hub.
    try:
        with _lock:
            for lib in _crypt_libs():
                try:
                    out = lib.crypt(password.encode(), h.encode())
                except Exception:
                    continue
                if isinstance(out, str):
                    out = out.encode()
                if out is None or out.startswith(b"*"):
                    continue
                return hmac.compare_digest(out, h.encode())
    except Exception:
        pass
    pam_result = _verify_via_pam(password, user)
    return bool(pam_result)


def _write_secret(path: str, value: str) -> None:
    os.makedirs(SECRETS_DIR, mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        f.write(value + "\n")
    os.replace(tmp, path)


def _read_secret(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            v = f.read().rstrip("\n")
        return v or None
    except OSError:
        return None


def _chpasswd(user: str, password: str) -> None:
    import shutil
    bin_ = shutil.which("chpasswd") or "/run/current-system/sw/bin/chpasswd"
    subprocess.run([bin_], input=f"{user}:{password}\n", text=True, check=True, capture_output=True)


# ── the single writers ─────────────────────────────────────────────────────

def set_free_password(new_password: str) -> None:
    """System password first, then the display copy. Used by: change-password, reset,
    migration acknowledgement, the CLI."""
    if not new_password:
        raise ValueError("empty password")
    _chpasswd(USER, new_password)
    _write_secret(DISPLAY_FILE, new_password)


def set_root_password(new_password: str) -> None:
    """Same contract for root (the credentials view lists it too)."""
    if not new_password:
        raise ValueError("empty password")
    _chpasswd("root", new_password)
    _write_secret(ROOT_DISPLAY_FILE, new_password)


# ── what the Hub shows ─────────────────────────────────────────────────────

def read_display_password() -> str | None:
    """The 'free' password to SHOW -- only if it really is the current one."""
    pw = _read_secret(DISPLAY_FILE)
    return pw if pw and verify_system_password(pw) else None


def read_root_display_password() -> str | None:
    pw = _read_secret(ROOT_DISPLAY_FILE)
    if not pw or ":" in pw:          # ':' = scrypt hash written by older reset code -> not showable
        return None
    return pw if verify_system_password(pw, "root") else None


def _display_state(path: str) -> str:
    """"missing" | "legacy" | "present" -- "present" only means a plaintext copy
    exists; it can still be stale (use read_display_password() to check that)."""
    pw = _read_secret(path)
    if pw is None:
        return "missing"
    return "legacy" if ":" in pw else "present"


# ── migration flow (legacy machines) ────────────────────────────────────────

def migration_pending() -> str | None:
    """The generated password awaiting acknowledgement, if any."""
    return _read_secret(MIGRATION_FILE)


def ensure_migration_pending(generate: Callable[[], str]) -> bool:
    """Legacy detection. Call it where onboarding status is computed.

    Condition: the account HAS a password (so this is not the first boot) but the Hub
    has NO display copy of it at all (file missing or still the old hash format).
    Then generate a new password once and park it for the onboarding "migration
    password" step. Nothing is applied until the user acknowledges, so the old
    password keeps working at GDM and in the Hub. Returns True when a migration is
    pending (caller re-opens onboarding).

    A copy that exists but merely fails to verify (password changed in GNOME
    Settings, `passwd`, or the pre-upgrade Hub) is DRIFT, not a legacy install:
    it never triggers a migration and never changes any password -- it is healed
    automatically at the next login via record_known_password(pw, only_if_stale=True).

    Never fires on the live ISO (/iso) or while shadow is still locked."""
    if os.path.exists(LIVE_ISO_MARKER):
        return False
    if migration_pending():
        return True
    if shadow_hash() is None:
        return False
    if _display_state(DISPLAY_FILE) == "present":
        return False            # copy exists: current, or just stale (drift)
    _write_secret(MIGRATION_FILE, generate())
    return True


def acknowledge_migration() -> bool:
    """User has written the new password down: make it real, then clear the pending file."""
    pw = migration_pending()
    if not pw:
        return False
    set_free_password(pw)
    os.remove(MIGRATION_FILE)
    return True


def record_known_password(password: str, only_if_stale: bool = False) -> bool:
    """"Keep my current password" (migration step): if the user types the correct
    current password, store it as the display copy and cancel the migration.

    only_if_stale=True is the login-handler heal: write ONLY when an existing
    plaintext copy is stale, never create a missing one (a missing copy is the
    legacy case and belongs to the migration flow)."""
    if not verify_system_password(password):
        return False
    if only_if_stale and _display_state(DISPLAY_FILE) != "present":
        return False
    if _read_secret(DISPLAY_FILE) != password:
        _write_secret(DISPLAY_FILE, password)
    try:
        os.remove(MIGRATION_FILE)
    except FileNotFoundError:
        pass
    return True


def generate_diceware_password(words: list[str] | None = None, n: int = 4) -> str:
    """word-word-word-word-NN, same shape the installer/reset produce (CSPRNG)."""
    words = words or ("apple barn brook cabin cedar cloud coral crane delta eagle ember fern field "
                      "flame flora flint frost grove haven hedge holly heron jade juniper kelp larch "
                      "lemon lilac linden loch lotus maple marsh meadow mist mossy mount oak ocean "
                      "olive petal pine pixel plum pond prism quartz raven ridge river robin rocky "
                      "rose rowan sage sand sierra silver slate snow solar spark spruce stone storm "
                      "summit swift thorn tide timber torch trout vale vault vine walnut wave willow "
                      "wren amber aspen birch blaze bloom bluff coast copper crest dune elder fjord "
                      "forge glade glen glow gulf").split()
    return "-".join(secrets.choice(words) for _ in range(n)) + f"-{secrets.randbelow(100):02d}"


if __name__ == "__main__":   # tiny CLI for credentials.nix:  echo NEW | system_password.py set-free
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd in ("set-free", "set-root"):
        pw = sys.stdin.readline().rstrip("\n")
        (set_free_password if cmd == "set-free" else set_root_password)(pw)
        print("ok")
    elif cmd == "verify":
        sys.exit(0 if verify_system_password(sys.stdin.readline().rstrip("\n")) else 1)
    else:
        print("usage: system_password.py set-free|set-root|verify  (password on stdin)", file=sys.stderr)
        sys.exit(2)
