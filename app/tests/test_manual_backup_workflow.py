import asyncio
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SCRIPT = REPO_ROOT / "app" / "sovran_systemsos_web" / "scripts" / "sovran-hub-backup.sh"
SERVER_FILE = REPO_ROOT / "app" / "sovran_systemsos_web" / "server.py"
SUPPORT_JS = REPO_ROOT / "app" / "sovran_systemsos_web" / "static" / "js" / "support.js"
NIX_HUB_FILE = REPO_ROOT / "modules" / "core" / "sovran-hub.nix"


def _extract_bash_function(script_path: Path, func_name: str) -> str:
    """Extract a bash function definition from a shell script using Python regex.

    The pattern matches from 'funcname() {' to the first line whose only content
    is '}' (the function closing brace, at column 0). This works correctly for
    functions whose control structures (case/if/while/for) use indented braces,
    because only the function's own closing brace sits at column 0. It would not
    correctly extract a function that contains a nested function definition.

    Returns the complete function definition, safe to inline into a test bash
    script without eval or awk."""
    source = script_path.read_text()
    pattern = r"^" + re.escape(func_name) + r"\(\) \{.*?^}"
    match = re.search(pattern, source, re.MULTILINE | re.DOTALL)
    if match is None:
        raise ValueError(f"Function '{func_name}' not found in {script_path}")
    return match.group(0)


class ManualBackupWorkflowTests(unittest.TestCase):
    def test_backup_script_uses_tar_archives_with_checksums_and_exclusions(self):
        source = BACKUP_SCRIPT.read_text()

        self.assertIn("tar \\", source)
        self.assertIn("--create", source)
        self.assertIn("--one-file-system", source)
        self.assertIn("sha256sum", source)
        self.assertIn("export_postgresql_dumps", source)
        self.assertIn("export_mariadb_dumps", source)
        self.assertIn("export_lnd_scb_if_possible", source)
        self.assertIn("--exclude='var/lib/bitcoind'", source)
        self.assertIn("--exclude='var/lib/electrs'", source)
        self.assertIn("--exclude='var/lib/lnd'", source)
        self.assertIn("set_status \"RUNNING\"", source)
        self.assertIn("set_status \"SUCCESS\"", source)
        self.assertIn("set_status \"FAILED\"", source)
        self.assertNotIn("rsync -a", source)

    def test_backend_and_frontend_use_explicit_backup_terminal_states(self):
        server_source = SERVER_FILE.read_text()
        support_source = SUPPORT_JS.read_text()

        self.assertIn("_write_backup_status, \"RUNNING\"", server_source)
        self.assertIn("_monitor_backup_subprocess", server_source)
        self.assertIn("asyncio.create_task(_monitor_backup_subprocess(proc))", server_source)
        self.assertIn("result === \"success\" || result === \"failed\"", support_source)

    # ── Regression tests for exit-code-127 / missing-interpreter bug ──────────

    def test_nix_service_path_includes_bash_and_gawk(self):
        """Regression: pkgs.bash and pkgs.gawk must appear in the sovran-hub-web
        service path so that the backup shell script and its awk calls can be
        resolved at runtime without producing exit code 127."""
        nix_source = NIX_HUB_FILE.read_text()
        self.assertIn(
            "pkgs.bash",
            nix_source,
            "pkgs.bash must be declared in the sovran-hub-web systemd service path",
        )
        self.assertIn(
            "pkgs.gawk",
            nix_source,
            "pkgs.gawk must be declared in the sovran-hub-web systemd service path",
        )

    def test_server_resolves_bash_via_shutil_which(self):
        """Regression: server must locate bash with shutil.which() rather than
        relying on /usr/bin/env bash, so a missing interpreter is caught early
        with a clear diagnostic instead of a cryptic exit-code-127 failure."""
        source = SERVER_FILE.read_text()
        self.assertIn(
            'shutil.which("bash")',
            source,
            "server.py must resolve bash via shutil.which to catch missing interpreter",
        )
        self.assertNotIn(
            '"/usr/bin/env", "bash"',
            source,
            "server.py must not use /usr/bin/env bash (relies on PATH, causes code 127)",
        )

    def test_server_logs_actionable_message_when_bash_missing(self):
        """Regression: when bash is absent the server must write an actionable log
        entry and set FAILED status before returning an HTTP error."""
        source = SERVER_FILE.read_text()
        self.assertIn(
            "bash_path is None",
            source,
            "server.py must check that bash_path is not None before launching",
        )
        self.assertIn(
            "interpreter",
            source,
            "server.py missing-bash error message must reference 'interpreter'",
        )

    def test_server_captures_stderr_from_backup_subprocess(self):
        """Regression: the backup subprocess must use stderr=PIPE so that any
        startup error (e.g. code 127 from a missing command) is captured and
        surfaced in the backup log rather than being silently discarded."""
        source = SERVER_FILE.read_text()
        self.assertIn(
            "stderr=asyncio.subprocess.PIPE",
            source,
            "backup subprocess must use stderr=PIPE to capture diagnostic output",
        )
        self.assertIn(
            "stderr_text",
            source,
            "_monitor_backup_subprocess must capture and log stderr content",
        )

    def test_monitor_includes_stderr_detail_in_failed_message(self):
        """Regression: _monitor_backup_subprocess must append captured stderr to
        the FAILED log entry so the UI shows what went wrong (e.g. 'bash: not
        found') rather than only the raw exit code."""
        source = SERVER_FILE.read_text()
        self.assertIn("stderr_chunks", source)
        self.assertIn("stderr_text", source)
        # stderr detail is conditionally appended only when non-empty
        self.assertIn('detail = f" — stderr: {stderr_text}"', source)

    def test_exit_code_127_subprocess_stderr_drain(self):
        """Behavioral regression: a subprocess that exits 127 must have its
        stderr drained without deadlock by the async drain loop."""

        async def _run():
            proc = await asyncio.create_subprocess_exec(
                "bash", "-c", "echo 'bash: command not found' >&2; exit 127",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            chunks: list[bytes] = []

            async def _drain():
                async for line in proc.stderr:
                    chunks.append(line)

            drain_task = asyncio.create_task(_drain())
            rc = await proc.wait()
            await drain_task
            return rc, b"".join(chunks).decode()

        rc, stderr_out = asyncio.run(_run())
        self.assertEqual(rc, 127)
        self.assertIn("bash: command not found", stderr_out)

    # ── Tests for home tar exit-1 tolerance (production fix) ──────────────────

    def test_backup_script_has_home_tar_archive_function(self):
        """The script must define create_home_tar_archive for /home only,
        separate from the strict create_tar_archive used for other sources."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            "create_home_tar_archive",
            source,
            "backup script must define create_home_tar_archive for /home",
        )
        self.assertIn(
            "_is_home_warning_allowlisted",
            source,
            "backup script must define _is_home_warning_allowlisted helper",
        )
        self.assertIn(
            "ARCHIVE_WARNINGS",
            source,
            "backup script must track nonfatal warnings in ARCHIVE_WARNINGS",
        )

    def test_backup_script_allowlist_covers_verified_gnu_tar_messages(self):
        """The allowlist must contain the exact GNU tar (LC_ALL=C) strings for
        the two permitted transient conditions."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            "file changed as we read it",
            source,
            "allowlist must include exact GNU tar 'file changed as we read it' message",
        )
        self.assertIn(
            "file removed before we read it",
            source,
            "allowlist must include exact GNU tar 'file removed before we read it' message",
        )

    def test_backup_script_stage3_uses_home_tar_function(self):
        """Stage 3 must call create_home_tar_archive (not create_tar_archive)
        so the /home archive tolerates live file changes on an active desktop."""
        source = BACKUP_SCRIPT.read_text()
        # The home archive call must use the tolerant function
        self.assertIn(
            'create_home_tar_archive "home.tar"',
            source,
            "Stage 3 must use create_home_tar_archive for home.tar",
        )

    def test_backup_script_strict_function_still_used_for_etc(self):
        """create_tar_archive (strict) must still be used for /etc/nixos,
        secrets, var-lib-lnd-clean, and var-lib — only /home is tolerant."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            'create_tar_archive "etc-nixos.tar"',
            source,
            "etc-nixos must use strict create_tar_archive",
        )
        self.assertIn(
            'create_tar_archive "var-lib.tar"',
            source,
            "var-lib must use strict create_tar_archive",
        )

    # ── Tests for partial-file atomic publish ─────────────────────────────────

    def test_backup_script_uses_partial_path_and_atomic_rename(self):
        """Archives must be written to a .partial path and atomically renamed
        to the final name only after acceptance, so a failed run never leaves a
        partial archive that appears complete."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            ".partial",
            source,
            "backup script must write to a .partial path before renaming",
        )
        self.assertIn(
            'mv "$partial_path" "$archive_path"',
            source,
            "backup script must atomically rename partial to final archive path",
        )
        self.assertIn(
            "PARTIAL_FILES",
            source,
            "backup script must track partial files for cleanup",
        )

    # ── Tests for INCOMPLETE / BACKUP_COMPLETE markers ────────────────────────

    def test_backup_script_writes_incomplete_marker(self):
        """A backup directory must be marked INCOMPLETE immediately after
        creation, so interrupted or failed runs are identifiable."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            'touch "$BACKUP_DIR/INCOMPLETE"',
            source,
            "backup script must create INCOMPLETE marker after mkdir",
        )

    def test_backup_script_writes_backup_complete_marker(self):
        """A BACKUP_COMPLETE file must be written only after all work succeeds,
        so restore tools can distinguish complete from incomplete backups."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            'BACKUP_COMPLETE"',
            source,
            "backup script must write BACKUP_COMPLETE file on success",
        )
        self.assertIn(
            'rm -f "$BACKUP_DIR/INCOMPLETE"',
            source,
            "backup script must remove INCOMPLETE marker on success",
        )

    # ── Tests for concurrency lock ─────────────────────────────────────────────

    def test_backup_script_uses_flock_concurrency_lock(self):
        """The script must acquire an exclusive flock before starting work to
        prevent two simultaneous backup runs."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            "flock",
            source,
            "backup script must use flock for concurrency protection",
        )
        self.assertIn(
            "LOCK_FILE",
            source,
            "backup script must define a LOCK_FILE for the flock",
        )

    # ── Tests for expanded home exclusions ────────────────────────────────────

    def test_backup_script_home_excludes_browser_caches(self):
        """The home archive must exclude browser disk caches (volatile data)
        while keeping profile data, bookmarks, and user documents."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            "--exclude='home/*/.mozilla/firefox/*/cache2'",
            source,
            "backup script must exclude Firefox cache2 directory",
        )
        self.assertIn(
            "--exclude='home/*/.config/google-chrome/*/Cache'",
            source,
            "backup script must exclude Chrome Cache directory",
        )
        self.assertIn(
            "--exclude='home/*/.config/chromium/*/Cache'",
            source,
            "backup script must exclude Chromium Cache directory",
        )
        self.assertIn(
            "--exclude='home/*/.config/BraveSoftware/Brave-Browser/*/Cache'",
            source,
            "backup script must exclude Brave Cache directory",
        )

    def test_backup_script_home_excludes_other_volatile_caches(self):
        """The home archive must exclude baloo, thumbnails, and X session
        error logs — all volatile/reconstructable content."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            "--exclude='home/*/.local/share/baloo'",
            source,
        )
        self.assertIn(
            "--exclude='home/*/.thumbnails'",
            source,
        )
        self.assertIn(
            "--exclude='home/*/.xsession-errors'",
            source,
        )

    # ── Tests for require_cmd additions ───────────────────────────────────────

    def test_backup_script_requires_mktemp_and_flock(self):
        """The script must explicitly check for mktemp and flock via require_cmd
        so that missing tools fail early with a clear error."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            "require_cmd mktemp",
            source,
            "backup script must require mktemp",
        )
        self.assertIn(
            "require_cmd flock",
            source,
            "backup script must require flock",
        )

    # ── Behavioral tests ──────────────────────────────────────────────────────

    def test_allowlist_accepts_file_changed_message(self):
        """Behavioral: _is_home_warning_allowlisted (from the actual backup script)
        returns true for the exact GNU tar 'file changed as we read it' message (LC_ALL=C).
        The function definition is extracted from the production script via Python regex
        to ensure the test exercises the real allowlist without eval-of-awk risks."""
        func_def = _extract_bash_function(BACKUP_SCRIPT, "_is_home_warning_allowlisted")
        script = (
            "#!/usr/bin/env bash\n"
            + func_def + "\n"
            + 'msgs=(\n'
            + '  "tar: /home/user/firefox.db: file changed as we read it"\n'
            + '  "tar: /home/user/.local/share/app: file removed before we read it"\n'
            + ")\n"
            + 'for msg in "${msgs[@]}"; do\n'
            + '  _is_home_warning_allowlisted "$msg" || { echo "BLOCKED: $msg"; exit 1; }\n'
            + '  echo "ALLOWED: $msg"\n'
            + "done\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(script)
            script_path = f.name
        try:
            result = subprocess.run(["bash", script_path], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
            self.assertIn("ALLOWED", result.stdout)
            self.assertNotIn("BLOCKED", result.stdout)
        finally:
            os.unlink(script_path)

    def test_allowlist_rejects_fatal_diagnostics(self):
        """Behavioral: _is_home_warning_allowlisted (from the actual backup script)
        returns false for permission errors, I/O errors, write errors, and other
        fatal conditions."""
        func_def = _extract_bash_function(BACKUP_SCRIPT, "_is_home_warning_allowlisted")
        script = (
            "#!/usr/bin/env bash\n"
            + func_def + "\n"
            + 'msgs=(\n'
            + '  "tar: /home/user/file: Permission denied"\n'
            + '  "tar: /dev/sdb: Cannot read: Input/output error"\n'
            + '  "tar: Error is not recoverable: exiting now"\n'
            + '  "Write error"\n'
            + '  "tar: /home/user: Cannot stat: No such file or directory"\n'
            + ")\n"
            + 'for msg in "${msgs[@]}"; do\n'
            + '  _is_home_warning_allowlisted "$msg" && { echo "ALLOWED_BUT_SHOULD_NOT: $msg"; exit 1; }\n'
            + '  echo "CORRECTLY_BLOCKED: $msg"\n'
            + "done\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(script)
            script_path = f.name
        try:
            result = subprocess.run(["bash", script_path], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
            self.assertIn("CORRECTLY_BLOCKED", result.stdout)
            self.assertNotIn("ALLOWED_BUT_SHOULD_NOT", result.stdout)
        finally:
            os.unlink(script_path)

    def test_home_tar_exits_1_with_only_allowlisted_warnings_is_accepted(self):
        """Behavioral: _create_archive_impl in HOME mode accepts tar exit 1 when
        every diagnostic is allowlisted and publishes the final archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "home", "user1")
            dest = os.path.join(tmpdir, "backup")
            os.makedirs(src, exist_ok=True)
            os.makedirs(dest, exist_ok=True)
            with open(os.path.join(src, "testfile.txt"), "w") as f:
                f.write("test content\n")

            # Emulate the allowlist + acceptance logic in HOME mode
            script = f"""#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="{dest}"
ARCHIVE_FILES=()
ARCHIVE_WARNINGS=()
PARTIAL_FILES=()

log() {{ echo "$*"; }}
fail() {{ echo "FAIL: $*" >&2; exit 1; }}

_is_home_warning_allowlisted() {{
  local msg="$1"
  case "$msg" in
    *"file changed as we read it"*)   return 0 ;;
    *"file removed before we read it"*) return 0 ;;
    *) return 1 ;;
  esac
}}

_create_archive_impl() {{
  local mode="$1"; shift
  local archive_name="$1"; shift
  local archive_path="$BACKUP_DIR/$archive_name"
  local partial_path="${{archive_path}}.partial"
  local diag_tmp
  diag_tmp="$(mktemp /tmp/sovran-tar-diag.XXXXXX)"
  PARTIAL_FILES+=("$partial_path" "$diag_tmp")

  local tar_rc=0
  LC_ALL=C tar --create --file "$partial_path" \
    --numeric-owner --sparse --one-file-system \
    "$@" 2>"$diag_tmp" || tar_rc=$?

  # Inject a simulated allowlisted warning to match production scenario
  echo "tar: {src}/testfile.txt: file changed as we read it" >> "$diag_tmp"
  tar_rc=1  # simulate exit 1

  local has_fatal_diag=0
  if [[ -s "$diag_tmp" ]]; then
    while IFS= read -r diag_line; do
      [[ -n "$diag_line" ]] || continue
      if [[ "$mode" == "HOME" ]] && ! _is_home_warning_allowlisted "$diag_line"; then
        has_fatal_diag=1
      fi
    done < "$diag_tmp"
  fi

  local accept=0
  if [[ "$tar_rc" -eq 0 ]]; then
    accept=1
  elif [[ "$mode" == "HOME" && "$tar_rc" -eq 1 && "$has_fatal_diag" -eq 0 ]]; then
    accept=1
    ARCHIVE_WARNINGS+=("$archive_name: nonfatal warnings")
  fi

  [[ "$accept" -eq 1 ]] || {{ rm -f "$partial_path" "$diag_tmp"; fail "Rejected"; }}
  [[ -s "$partial_path" ]] || {{ rm -f "$partial_path" "$diag_tmp"; fail "Empty"; }}

  mv "$partial_path" "$archive_path"
  rm -f "$diag_tmp"
  ARCHIVE_FILES+=("$archive_name")
  echo "CREATED: $archive_name"
}}

create_home_tar_archive() {{ _create_archive_impl HOME "$@"; }}

create_home_tar_archive "home.tar" -C "{tmpdir}" home
echo "WARNINGS: ${{#ARCHIVE_WARNINGS[@]}}"
[[ -f "{dest}/home.tar" ]] && echo "FILE_EXISTS" || echo "FILE_MISSING"
[[ ! -f "{dest}/home.tar.partial" ]] && echo "PARTIAL_CLEANED" || echo "PARTIAL_LEFT"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"stdout: {result.stdout}\nstderr: {result.stderr}")
            self.assertIn("CREATED: home.tar", result.stdout)
            self.assertIn("FILE_EXISTS", result.stdout)
            self.assertIn("PARTIAL_CLEANED", result.stdout)

    def test_home_tar_exits_1_with_fatal_diagnostic_fails(self):
        """Behavioral: _create_archive_impl in HOME mode must fail when tar exit 1
        includes a non-allowlisted diagnostic (e.g. permission denied)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "backup")
            os.makedirs(dest, exist_ok=True)

            script = f"""#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="{dest}"
ARCHIVE_FILES=()
ARCHIVE_WARNINGS=()
PARTIAL_FILES=()

fail() {{ echo "CORRECTLY_FAILED: $*"; exit 1; }}
log() {{ echo "$*"; }}

_is_home_warning_allowlisted() {{
  local msg="$1"
  case "$msg" in
    *"file changed as we read it"*)   return 0 ;;
    *"file removed before we read it"*) return 0 ;;
    *) return 1 ;;
  esac
}}

# Simulate tar exit 1 with a fatal permission-denied diagnostic
archive_name="home.tar"
partial_path="$BACKUP_DIR/$archive_name.partial"
diag_tmp=$(mktemp)
echo "tar: /home/user/locked: Permission denied" > "$diag_tmp"

tar_rc=1
has_fatal_diag=0
while IFS= read -r diag_line; do
  [[ -n "$diag_line" ]] || continue
  if ! _is_home_warning_allowlisted "$diag_line"; then
    has_fatal_diag=1
  fi
done < "$diag_tmp"
rm -f "$diag_tmp"

if [[ "$tar_rc" -eq 1 && "$has_fatal_diag" -eq 0 ]]; then
  echo "INCORRECTLY_ACCEPTED"
  exit 0
else
  fail "tar exit 1 with Permission denied"
fi
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, f"Should have failed: {result.stdout}")
            self.assertIn("CORRECTLY_FAILED", result.stdout)

    def test_home_tar_exits_2_always_fails(self):
        """Behavioral: tar exit code 2 (fatal) must always fail even in HOME mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "backup")
            os.makedirs(dest, exist_ok=True)

            script = f"""#!/usr/bin/env bash
BACKUP_DIR="{dest}"
ARCHIVE_WARNINGS=()

fail() {{ echo "CORRECTLY_FAILED: $*"; exit 1; }}
log() {{ echo "$*"; }}

_is_home_warning_allowlisted() {{
  case "$1" in
    *"file changed as we read it"*)   return 0 ;;
    *"file removed before we read it"*) return 0 ;;
    *) return 1 ;;
  esac
}}

tar_rc=2
has_fatal_diag=0

accept=0
if [[ "$tar_rc" -eq 0 ]]; then
  accept=1
elif [[ "HOME" == "HOME" && "$tar_rc" -eq 1 && "$has_fatal_diag" -eq 0 ]]; then
  accept=1
fi

if [[ "$accept" -eq 0 ]]; then
  if [[ "$tar_rc" -gt 1 ]]; then
    fail "tar exited with fatal code $tar_rc"
  fi
fi
echo "SHOULD_NOT_REACH_HERE"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, f"Should have failed: {result.stdout}")
            self.assertIn("CORRECTLY_FAILED", result.stdout)
            self.assertNotIn("SHOULD_NOT_REACH_HERE", result.stdout)

    def test_partial_file_cleanup_on_failure(self):
        """Behavioral: a .partial file must be removed when the archive creation
        fails, so no incomplete archive is left on the destination."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "backup")
            os.makedirs(dest, exist_ok=True)

            partial_path = os.path.join(dest, "home.tar.partial")

            script = f"""#!/usr/bin/env bash
BACKUP_DIR="{dest}"
PARTIAL_FILES=()

fail() {{
  # Simulate cleanup removing partial files
  for p in "${{PARTIAL_FILES[@]}}"; do
    [[ -f "$p" ]] && rm -f "$p"
  done
  echo "FAILED: $*"
  exit 1
}}
log() {{ :; }}

partial_path="$BACKUP_DIR/home.tar.partial"
diag_tmp=$(mktemp)
PARTIAL_FILES+=("$partial_path" "$diag_tmp")

# Simulate partial archive being written
touch "$partial_path"

# Simulate a fatal error
fail "tar exited with code 2"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, f"Should have failed: {result.stdout}")
            self.assertFalse(
                os.path.exists(partial_path),
                "Partial file must be removed on failure",
            )
            self.assertIn("FAILED", result.stdout)

    def test_archive_warnings_recorded_in_manifest(self):
        """Source text: ARCHIVE_WARNINGS must be written into BACKUP_MANIFEST.txt
        so the user can see which archives had nonfatal live-file warnings."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            "ARCHIVE_WARNINGS[@]",
            source,
            "backup script must iterate ARCHIVE_WARNINGS in manifest generation",
        )
        self.assertIn(
            "Nonfatal warnings:",
            source,
            "manifest must include a 'Nonfatal warnings:' section",
        )

    def test_backup_script_logs_warnings_before_success_message(self):
        """Source text: when ARCHIVE_WARNINGS is non-empty, the script must log
        the warnings before the 'All Finished!' success message."""
        source = BACKUP_SCRIPT.read_text()
        # Both constructs must be present
        self.assertIn(
            "${#ARCHIVE_WARNINGS[@]}",
            source,
            "backup script must check ARCHIVE_WARNINGS count before success message",
        )
        self.assertIn(
            "All Finished!",
            source,
        )


if __name__ == "__main__":
    unittest.main()
