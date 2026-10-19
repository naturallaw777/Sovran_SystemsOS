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
_libcrypt = None


# ── low level ──────────────────────────────────────────────────────────────

def _crypt():
    global _libcrypt
    if _libcrypt is None:
        candidates: list[str] = []
        env_path = os.environ.get("LIBCRYPT")
        if env_path:
            candidates.append(env_path)
        found = ctypes.util.find_library("crypt")
        if found:
            candidates.append(found)
        candidates += ["libcrypt.so.1", "libcrypt.so.2", "libcrypt.so"]
        last_exc: Exception | None = None
        for path in dict.fromkeys(candidates):
            try:
                lib = ctypes.CDLL(path)
                lib.crypt.restype = ctypes.c_char_p
                lib.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
            except (OSError, AttributeError) as exc:
                # A stale LIBCRYPT path (e.g. a Nix store path from before an
                # update / GC) must not be fatal: try the next candidate.
                last_exc = exc
                continue
            _libcrypt = lib
            break
        if _libcrypt is None:
            raise OSError(f"could not load libcrypt (tried {candidates!r})") from last_exc
    return _libcrypt


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
    try:
        with _lock:
            out = _crypt().crypt(password.encode(), h.encode())
    except Exception:
        # Verification is fail-closed, never fatal. libcrypt can be missing /
        # unloadable (stale LIBCRYPT Nix store path, library not yet in the
        # Hub's environment after an update, unsupported hash): that must
        # degrade to "password not verified / not showable", not raise into
        # callers. Raising here crashed GET /api/service-detail/<unit> for
        # the System Passwords tile, so the Hub showed only
        # "Could not load service details." for that one tile.
        return False
    if isinstance(out, str):
        out = out.encode()
    return out is not None and hmac.compare_digest(out, h.encode())


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
