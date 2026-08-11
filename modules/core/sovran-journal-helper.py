#!/usr/bin/env python3
"""Sovran restricted journal helper.

A root-owned, non-user-writable diagnostic tool that wraps journalctl with
a strict allowlist of safe flags.  Replaces the ``journalctl *`` sudo rule
in tech-support.nix.

Accepted flags:
  --unit / -u <name>        unit name (letters, digits, @, ., _, - only; .service suffix required)
  --lines / -n <N>          positive integer (max 10000)
  --priority / -p <level>   0-7 or emerg/alert/crit/err/warning/notice/info/debug
  --since <datetime>        ISO 8601 date/datetime (no paths, no filesystem roots)
  --until <datetime>        ISO 8601 date/datetime (no paths, no filesystem roots)
  --output / -o <format>    short | short-iso | cat | json | verbose

All other flags, paths, directories, roots, namespaces, and output
destinations are rejected with a non-zero exit code.
"""

import re
import subprocess
import sys

# ── Allowlists ────────────────────────────────────────────────────────────────

_ALLOWED_UNITS_RE = re.compile(
    r'^[a-zA-Z0-9@._\-]+\.(service|socket|timer|target|mount|path|slice|scope)$'
)

_ALLOWED_PRIORITIES = frozenset([
    "0", "1", "2", "3", "4", "5", "6", "7",
    "emerg", "alert", "crit", "err", "warning", "notice", "info", "debug",
])

_ALLOWED_OUTPUT_FORMATS = frozenset([
    "short", "short-iso", "cat", "json", "verbose",
])

# ISO 8601 date or datetime: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS (no paths)
_DATETIME_RE = re.compile(r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$')

_MAX_LINES = 10000

# ── Argument parser ───────────────────────────────────────────────────────────


def _die(msg: str) -> None:
    print(f"sovran-journal-helper: {msg}", file=sys.stderr)
    sys.exit(1)


def _validate_unit(val: str) -> str:
    if not _ALLOWED_UNITS_RE.match(val):
        _die(f"rejected unit name: {val!r} (only letters/digits/@._- with a known suffix)")
    return val


def _validate_lines(val: str) -> str:
    try:
        n = int(val)
    except ValueError:
        _die(f"rejected: --lines must be a positive integer, got {val!r}")
    if n <= 0 or n > _MAX_LINES:
        _die(f"rejected: --lines must be between 1 and {_MAX_LINES}, got {n}")
    return str(n)


def _validate_priority(val: str) -> str:
    if val not in _ALLOWED_PRIORITIES:
        _die(f"rejected priority: {val!r}")
    return val


def _validate_datetime(val: str) -> str:
    if not _DATETIME_RE.match(val):
        _die(f"rejected: datetime {val!r} (must be YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)")
    return val


def _validate_output(val: str) -> str:
    if val not in _ALLOWED_OUTPUT_FORMATS:
        _die(f"rejected output format: {val!r}")
    return val


def main() -> None:
    args = sys.argv[1:]
    cmd = ["journalctl"]

    i = 0
    while i < len(args):
        arg = args[i]

        if arg in ("--unit", "-u"):
            i += 1
            if i >= len(args):
                _die("--unit requires a value")
            cmd += ["--unit", _validate_unit(args[i])]
        elif arg.startswith("--unit="):
            cmd += ["--unit", _validate_unit(arg[len("--unit="):])]

        elif arg in ("--lines", "-n"):
            i += 1
            if i >= len(args):
                _die("--lines requires a value")
            cmd += ["--lines", _validate_lines(args[i])]
        elif arg.startswith("--lines="):
            cmd += ["--lines", _validate_lines(arg[len("--lines="):])]
        elif re.match(r'^-n\d+$', arg):
            cmd += ["--lines", _validate_lines(arg[2:])]

        elif arg in ("--priority", "-p"):
            i += 1
            if i >= len(args):
                _die("--priority requires a value")
            cmd += ["--priority", _validate_priority(args[i])]
        elif arg.startswith("--priority="):
            cmd += ["--priority", _validate_priority(arg[len("--priority="):])]

        elif arg == "--since":
            i += 1
            if i >= len(args):
                _die("--since requires a value")
            cmd += ["--since", _validate_datetime(args[i])]
        elif arg.startswith("--since="):
            cmd += ["--since", _validate_datetime(arg[len("--since="):])]

        elif arg == "--until":
            i += 1
            if i >= len(args):
                _die("--until requires a value")
            cmd += ["--until", _validate_datetime(args[i])]
        elif arg.startswith("--until="):
            cmd += ["--until", _validate_datetime(arg[len("--until="):])]

        elif arg in ("--output", "-o"):
            i += 1
            if i >= len(args):
                _die("--output requires a value")
            cmd += ["--output", _validate_output(args[i])]
        elif arg.startswith("--output="):
            cmd += ["--output", _validate_output(arg[len("--output="):])]

        else:
            _die(
                f"rejected flag: {arg!r}. "
                "Allowed flags: --unit, --lines, --priority, --since, --until, --output"
            )

        i += 1

    if not cmd[1:]:
        _die("at least one flag is required (try --unit <name>)")

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
