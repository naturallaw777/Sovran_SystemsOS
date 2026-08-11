"""Sovran Hub — injectable support session operations.

Functions here handle legacy migration, root-key removal, and support-session
expiry.  All filesystem paths, clocks, and callback functions are injectable
so that the test suite can exercise the exact production implementations with
temporary files and mocks rather than maintaining separate copies.

All functions depend only on the Python standard library and the co-located
``security_helpers`` module.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time as _time_module
from typing import Callable

# ── Legacy Njalla curl line regex ─────────────────────────────────────────────
#
# Matches both forms written by old Hub versions:
#   curl [flags] https://njal.la/...           (unquoted)
#   curl [flags] "https://njal.la/..."          (quoted — historical form)
#
# Optional flags (in order): --silent, --max-time N, --fail
#
# Rejected outright: semicolons, pipes, backticks, redirects, newlines,
# ${...} except the literal ${IP} placeholder, and any extra arguments.
_LEGACY_NJALLA_CURL_RE = re.compile(
    r'^curl\s+(?:--silent\s+)?(?:--max-time\s+\d+\s+)?(?:--fail\s+)?'
    r'(?:'
    r'"(https://(?:www\.)?njal\.la/(?:[^\s;|`$\x00-\x1f"]|\$\{IP\})+)"'   # group 1: quoted
    r'|(https://(?:www\.)?njal\.la/(?:[^\s;|`$\x00-\x1f"]|\$\{IP\})+)'    # group 2: unquoted
    r')$'
)

# The exact base64 blob of the historical fleet-wide root support key that
# was shipped with old releases of Sovran_SystemsOS and must be removed from
# /root/.ssh/authorized_keys on upgrade.
LEGACY_ROOT_KEY_BLOB = (
    "AAAAC3NzaC1lZDI1NTE5AAAAIPxPF2Qm11FQxC20wydKtlmn/Bo07YnDda3b9/CyXxQP"
)


def remove_legacy_root_key(
    authorized_keys_path: str,
    target_blob: str,
    *,
    audit_fn: Callable[[str, str], None] | None = None,
) -> bool:
    """Remove the exact historical fleet-wide support key from an authorized_keys file.

    Identifies the key by its exact base64 blob (``parts[1]``), regardless of
    algorithm prefix or comment field.  All other keys, blank lines, and comment
    lines are preserved unchanged.  The file is written back atomically.

    Args:
        authorized_keys_path: Path to the authorized_keys file to modify.
        target_blob: The exact base64 key blob to remove.  Only lines whose
            second whitespace-delimited field matches this value are removed;
            no substring or comment matching is performed.
        audit_fn: Optional callback ``(event: str, details: str)`` for audit
            logging.  The full key blob is **never** passed to this callback.

    Returns:
        ``True`` if the file was modified (at least one line removed),
        ``False`` if unchanged or absent.
    """

    def _audit(event: str, details: str = "") -> None:
        if audit_fn:
            audit_fn(event, details)

    try:
        with open(authorized_keys_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return False
    except OSError:
        return False

    kept: list[str] = []
    removed_count = 0
    for line in lines:
        stripped = line.rstrip("\n")
        parts = stripped.split()
        # Key lines have at least two space-separated fields: algorithm + blob.
        # Remove only lines whose blob (parts[1]) matches exactly — no
        # substring matching, no comment matching.
        if len(parts) >= 2 and parts[1] == target_blob:
            removed_count += 1
            # Audit without logging the key blob itself.
            _audit("LEGACY_ROOT_KEY_REMOVED", "removed exact historical root support key")
        else:
            kept.append(line)

    if removed_count == 0:
        return False

    # Atomic write: mkstemp in same directory + os.replace
    auth_dir = os.path.dirname(os.path.abspath(authorized_keys_path))
    fd, tmp = tempfile.mkstemp(dir=auth_dir, prefix=".authorized_keys_tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.writelines(kept)
        os.chmod(tmp, 0o600)
        os.replace(tmp, authorized_keys_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False

    _audit(
        "LEGACY_ROOT_KEY_CLEANUP_COMPLETE",
        f"removed={removed_count} keys_retained={len(kept)}",
    )
    return True


def migrate_legacy_njalla_script(
    script_path: str,
    validate_fn: Callable[[str], str],
    save_fn: Callable[[list[str]], None],
    load_fn: Callable[[], list[str]],
    *,
    audit_fn: Callable[[str, str], None] | None = None,
) -> None:
    """Safely migrate legacy curl DDNS lines from a njalla.sh script to JSON store.

    Reads the script **without** executing or sourcing it.  Parses only the
    exact narrow curl-pattern lines (quoted or unquoted) written by old Hub
    versions.  Any other line is silently discarded — never executed or logged
    (it may contain secret tokens).

    On successful persistence the script is archived with mode ``0o000`` so
    it can no longer be executed.  If persistence fails the script is left
    **untouched**.

    Args:
        script_path: Path to the legacy njalla.sh file.
        validate_fn: URL validation function; raises ``ValueError`` on invalid
            URLs.  Callers must substitute the ``${IP}`` placeholder before
            calling — this function passes ``url.replace("${IP}", "127.0.0.1")``
            to the validator.
        save_fn: Callable that atomically writes a ``list[str]`` URL list to
            the persistent JSON store.
        load_fn: Callable that returns the current ``list[str]`` URL list from
            the persistent store.
        audit_fn: Optional callback ``(event: str, details: str)`` for audit
            logging.  Token-bearing URLs are **never** passed to this callback.
    """

    def _audit(event: str, details: str = "") -> None:
        if audit_fn:
            audit_fn(event, details)

    try:
        with open(script_path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        return
    except OSError:
        return

    existing_urls = load_fn()

    new_urls: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("IP=") or line.startswith("#!/"):
            continue
        m = _LEGACY_NJALLA_CURL_RE.match(line)
        if not m:
            # Unrecognised line — discard silently, do NOT log (may contain tokens)
            continue
        # group(1) = quoted form, group(2) = unquoted form
        raw_url = m.group(1) or m.group(2)
        # Substitute placeholder so host/scheme/path validation works
        url_to_validate = raw_url.replace("${IP}", "127.0.0.1")
        try:
            validate_fn(url_to_validate)
        except ValueError:
            continue  # Silently discard invalid/non-Njal.la URLs
        if raw_url not in existing_urls and raw_url not in new_urls:
            new_urls.append(raw_url)

    if new_urls:
        combined = existing_urls + new_urls
        try:
            save_fn(combined)
        except Exception:
            # Persistence failed — leave the script untouched, return without
            # archiving so the migration can be retried.
            return
        _audit("NJALLA_MIGRATION", f"migrated {len(new_urls)} DDNS URLs from legacy script")

    # Archive: remove all permission bits so cron/any mechanism cannot run it
    try:
        os.chmod(script_path, 0o000)
    except OSError:
        pass


def expire_if_stale(
    status_file: str,
    *,
    clock_fn: Callable[[], float] | None = None,
    disable_fn: Callable[[], bool] | None = None,
    audit_fn: Callable[[str, str], None] | None = None,
    session_id: str | None = None,
    expected_expiry: float | None = None,
    max_session_seconds: float = 86400.0,
) -> bool:
    """Expire a support session if its deadline has passed.

    **Stale-timer guard:** when ``session_id`` and/or ``expected_expiry`` are
    provided (used by the server-side timer callback), the stored session
    metadata is compared field-by-field.  A mismatch means a replacement
    session has been started after this timer was scheduled; in that case the
    function returns ``False`` without touching anything.

    Args:
        status_file: Path to the JSON session metadata file.
        clock_fn: Callable returning current Unix time (default: ``time.time``).
        disable_fn: Callable that performs the full disable sequence — removes
            the support key, removes wallet-unlock metadata, restores deny
            ACLs, clears session metadata, and audits the event.  If ``None``,
            expiry is detected but no action is taken (useful for tests that
            want to inspect detection only).
        audit_fn: Optional callback ``(event: str, details: str)`` for audit
            logging.
        session_id: If given, expiry is skipped unless the stored
            ``session_id`` field matches exactly.
        expected_expiry: If given, expiry is skipped unless the stored
            ``expires_at`` field matches exactly.
        max_session_seconds: Legacy fallback: maximum age (from ``enabled_at``)
            when ``expires_at`` is absent.

    Returns:
        ``True`` if a session was expired, ``False`` otherwise.
    """
    _now = clock_fn if clock_fn is not None else _time_module.time

    def _audit(event: str, details: str = "") -> None:
        if audit_fn:
            audit_fn(event, details)

    def _disable() -> bool:
        return disable_fn() if disable_fn is not None else True

    try:
        with open(status_file, "r") as f:
            info = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False

    # Stale-timer guard
    if session_id is not None and info.get("session_id") != session_id:
        return False
    if expected_expiry is not None and info.get("expires_at") != expected_expiry:
        return False

    expires_at = info.get("expires_at")
    now = _now()

    if expires_at is None:
        enabled_at = info.get("enabled_at", 0)
        if enabled_at and (now - enabled_at) > max_session_seconds:
            _audit("SUPPORT_EXPIRED", "legacy session without expires_at exceeded max duration")
            _disable()
            return True
        return False

    if now >= expires_at:
        _audit("SUPPORT_EXPIRED", f"session expired at {expires_at:.0f}")
        _disable()
        return True

    return False
