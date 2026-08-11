"""Sovran Hub — pure security validation helpers.

This module contains the dependency-light security helper functions used by
the Hub server.  Keeping them here allows tests to import and exercise the
exact production implementations rather than maintaining separate copies.

All functions in this module depend only on the Python standard library.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import tempfile
import time
import urllib.parse

# ── Nix string escaping ────────────────────────────────────────────────────────

def _nix_escape(value: str) -> str:
    """Escape *value* for use inside a Nix double-quoted string literal.

    Handles backslashes, double-quotes, newlines, carriage returns, tabs, and
    Nix-specific anti-quotation sequences (``${...}``).  The returned value is
    safe to embed as ``"<returned_value>"`` in generated Nix source.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("\n", "\\n")
    value = value.replace("\r", "\\r")
    value = value.replace("\t", "\\t")
    value = value.replace("${", "\\${")
    return value


# ── Nostr npub validation (NIP-19 / Bech32) ───────────────────────────────────

# Fast pre-filter: "npub1" followed by exactly 58 lower-case bech32 characters.
NPUB_RE = re.compile(r"^npub1[023456789acdefghjklmnpqrstuvwxyz]{58}$")

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32_GENERATOR = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)


def _bech32_polymod(values: list[int]) -> int:
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for i in range(5):
            if (top >> i) & 1:
                chk ^= _BECH32_GENERATOR[i]
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _bech32_create_checksum(hrp: str, data: list[int]) -> list[int]:
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> (5 * (5 - i))) & 31 for i in range(6)]


def _bech32_convertbits_decode(data: list[int]) -> list[int] | None:
    """Convert a 5-bit integer sequence to 8-bit bytes, stripping padding."""
    acc = 0
    bits = 0
    ret: list[int] = []
    for value in data:
        acc = (acc << 5) | value
        bits += 5
        while bits >= 8:
            bits -= 8
            ret.append((acc >> bits) & 0xFF)
    if bits >= 5 or ((acc << (8 - bits)) & 0xFF):
        return None  # invalid padding
    return ret


def _bech32_decode(bech: str) -> tuple[str, bytes] | None:
    """Decode a bech32 string.  Returns ``(hrp, payload_bytes)`` or ``None``.

    Verifies:
    - Lowercase-only (mixed case rejected per BIP-173).
    - Only valid bech32 charset characters.
    - Valid checksum.
    - Exactly one separator (``1``).
    - Minimum data part length (≥ 8 chars = 6 checksum + ≥ 2 data).
    """
    if bech != bech.lower():
        return None  # mixed case
    sep = bech.rfind("1")
    if sep < 1 or sep + 7 > len(bech):
        return None
    hrp = bech[:sep]
    data_part = bech[sep + 1:]
    if any(c not in _BECH32_CHARSET for c in data_part):
        return None
    decoded = [_BECH32_CHARSET.index(c) for c in data_part]
    if _bech32_polymod(_bech32_hrp_expand(hrp) + decoded) != 1:
        return None  # bad checksum
    converted = _bech32_convertbits_decode(decoded[:-6])
    if converted is None:
        return None
    return hrp, bytes(converted)


def _validate_npub(value: str) -> bool:
    """Return ``True`` iff *value* is a valid NIP-19 Nostr npub.

    Checks:
    - Lowercase ``npub`` HRP.
    - Valid bech32 charset (no uppercase, no invalid chars).
    - Valid bech32 checksum.
    - Exactly 32 decoded payload bytes (256-bit public key).
    - Retains the original regex as a fast pre-filter.
    """
    if not NPUB_RE.fullmatch(value):
        return False
    result = _bech32_decode(value)
    if result is None:
        return False
    hrp, payload = result
    return hrp == "npub" and len(payload) == 32


# ── DDNS URL validation ────────────────────────────────────────────────────────

_DDNS_URL_MAX_LEN = 2048
_DDNS_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

# Allowlist: only the official Njal.la provider hostnames are accepted for
# DDNS update URLs.  Any other host would allow SSRF against the Hub's
# internal network.
_DDNS_ALLOWED_HOSTNAMES: frozenset[str] = frozenset(["njal.la", "www.njal.la"])


def _validate_ddns_url(url: str) -> str:
    """Validate *url* as a safe DDNS update URL and return it normalised.

    Rules:
    - Must be a valid URL parseable by urllib.parse.
    - Scheme must be ``https`` (case-insensitive).
    - No userinfo (credentials must not be embedded in the URL).
    - No fragment.
    - No control characters.
    - Must not exceed ``_DDNS_URL_MAX_LEN`` bytes.
    - Hostname must be the exact Njal.la provider hostname (njal.la or www.njal.la).
    - Port must be absent or the default HTTPS port 443.
    - No percent-encoded null bytes.

    Raises ``ValueError`` with a safe (non-secret) message on failure.
    """
    if not url:
        raise ValueError("DDNS URL must not be empty")
    if len(url) > _DDNS_URL_MAX_LEN:
        raise ValueError("DDNS URL exceeds maximum length")
    if _DDNS_CONTROL_RE.search(url):
        raise ValueError("DDNS URL contains control characters")
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        raise ValueError("DDNS URL could not be parsed")
    if parsed.scheme.lower() != "https":
        raise ValueError("DDNS URL must use the https scheme")
    if parsed.username or parsed.password:
        raise ValueError("DDNS URL must not contain credentials")
    if parsed.fragment:
        raise ValueError("DDNS URL must not contain a fragment")
    if parsed.port is not None and parsed.port != 443:
        raise ValueError("DDNS URL must use the default HTTPS port")
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("DDNS URL must contain a hostname")
    # Reject raw IP addresses
    try:
        ipaddress.ip_address(hostname)
        raise ValueError("DDNS URL hostname must not be a raw IP address")
    except ValueError as exc:
        if "raw IP" in str(exc):
            raise
    # Allowlist: only Njal.la
    if hostname.lower() not in _DDNS_ALLOWED_HOSTNAMES:
        raise ValueError(
            f"DDNS URL hostname is not an allowed Njal.la host "
            f"(got {hostname!r})"
        )
    if "%00" in url.lower():
        raise ValueError("DDNS URL must not contain encoded null bytes")
    # Reject any remaining $ expressions — after ${IP} substitution there
    # must be none.  Callers that store ${IP} placeholder URLs must substitute
    # before calling this function.
    if "$" in url:
        raise ValueError("DDNS URL must not contain $ expressions")
    # Require the exact /update/ path used by Njal.la
    if parsed.path != "/update/":
        raise ValueError("DDNS URL path must be exactly /update/")
    return url


# ── SSH public-key validation ─────────────────────────────────────────────────

_SSH_PUBKEY_ALGORITHMS = frozenset([
    "ssh-ed25519",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
])


def _validate_ssh_pubkey(key: str) -> str:
    """Validate *key* as a single OpenSSH public key and return it normalised.

    Accepts only single-line keys with a supported algorithm, valid base64
    payload, and an optional comment.  Rejects options, multiple lines,
    control characters, and unsupported algorithms.

    Raises ``ValueError`` with a safe message on failure.
    """
    key = key.strip()
    if not key:
        raise ValueError("SSH public key must not be empty")
    if _DDNS_CONTROL_RE.search(key):
        raise ValueError("SSH public key contains control characters")
    if "\n" in key or "\r" in key:
        raise ValueError("SSH public key must be a single line")
    parts = key.split()
    if len(parts) < 2:
        raise ValueError("SSH public key is malformed")
    algo, b64 = parts[0], parts[1]
    if algo not in _SSH_PUBKEY_ALGORITHMS:
        raise ValueError(f"Unsupported SSH key algorithm: {algo!r}")
    try:
        decoded = base64.b64decode(b64, validate=True)
    except Exception:
        raise ValueError("SSH public key payload is not valid base64")
    if len(decoded) < 20:
        raise ValueError("SSH public key payload is too short")
    return key


# ── Persistent Hub session store ─────────────────────────────────────────────

def load_session_store(path: str) -> dict[str, float]:
    """Load persisted Hub sessions from *path*.

    Returns a mapping of session token → expiry timestamp (epoch seconds).
    Expired entries are discarded.  A missing, unreadable or malformed file
    yields an empty mapping — losing sessions is a UX inconvenience (the user
    must log in again), never a fatal error.

    Persistence exists so that authenticated sessions survive a restart of
    the Hub service itself.  ``nixos-rebuild switch`` restarts
    ``sovran-hub-web.service`` during activation (its unit definition changes
    with every feature toggle), and without persistence the in-progress
    rebuild/update status polling loses authentication and the UI hangs.
    """
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    now = time.time()
    sessions: dict[str, float] = {}
    for token, expiry in data.items():
        if not isinstance(token, str) or not token:
            continue
        if isinstance(expiry, bool) or not isinstance(expiry, (int, float)):
            continue
        if expiry > now:
            sessions[token] = float(expiry)
    return sessions


def save_session_store(path: str, sessions: dict[str, float]) -> bool:
    """Atomically persist *sessions* (token → expiry) to *path* with mode 0600.

    Writes to a temp file in the same directory and renames it into place so
    the store is never left partially written.  Returns True on success,
    False otherwise (persistence is best-effort).
    """
    directory = os.path.dirname(path) or "."
    fd = None
    tmp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".hub_sessions_tmp")
        with os.fdopen(fd, "w") as f:
            fd = None  # os.fdopen takes ownership of the descriptor
            json.dump(sessions, f)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
        return True
    except OSError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False
