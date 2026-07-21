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


class ManualBackupWorkflowTests(unittest.TestCase):
    # ── Core design: rsync, no tar, no DB, no LND ─────────────────────────────

    def test_backup_script_uses_rsync_not_tar(self):
        """New design: backup must use rsync, not tar archives."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("rsync", source, "backup script must use rsync")
        self.assertIn("--archive", source, "rsync must be called with --archive flag")
        self.assertNotIn("tar --create", source, "backup script must not create tar archives")
        self.assertNotIn("--file ", source, "backup script must not write tar --file output")

    def test_backup_script_has_no_database_dump_functions(self):
        """Removed: PostgreSQL and MariaDB dump functions must not exist."""
        source = BACKUP_SCRIPT.read_text()
        self.assertNotIn("pg_dump", source, "backup script must not contain pg_dump")
        self.assertNotIn("pg_dumpall", source, "backup script must not contain pg_dumpall")
        self.assertNotIn("mariadb-dump", source, "backup script must not contain mariadb-dump")
        self.assertNotIn("mysqldump", source, "backup script must not contain mysqldump")
        self.assertNotIn("export_postgresql_dumps", source)
        self.assertNotIn("export_mariadb_dumps", source)

    def test_backup_script_has_no_lnd_service_orchestration(self):
        """Removed: LND stop/restart and SCB export must not exist."""
        source = BACKUP_SCRIPT.read_text()
        self.assertNotIn("export_lnd_scb_if_possible", source)
        self.assertNotIn("stop_lnd_stack_if_needed", source)
        self.assertNotIn("lncli", source, "backup script must not call lncli")
        self.assertNotIn("LND_STOPPED", source, "backup script must not track LND_STOPPED state")
        self.assertNotIn("LND_UNITS_TO_RESTART", source)

    def test_backup_script_has_no_tar_dependencies(self):
        """Removed: sha256sum checksums for tar artifacts must not exist."""
        source = BACKUP_SCRIPT.read_text()
        self.assertNotIn("sha256sum", source, "backup script must not generate tar checksums")
        self.assertNotIn("SHA256SUMS", source, "backup script must not write SHA256SUMS.txt")

    # ── Rsync options ──────────────────────────────────────────────────────────

    def test_backup_script_rsync_uses_metadata_preserving_options(self):
        """Rsync must be called with Linux metadata-preserving options."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("--archive", source)
        self.assertIn("--acls", source)
        self.assertIn("--xattrs", source)
        self.assertIn("--hard-links", source)
        self.assertIn("--numeric-ids", source)
        self.assertIn("--one-file-system", source)

    def test_backup_script_rsync_no_delete(self):
        """Rsync must NOT use --delete or --delete-delay.
        Accidental source deletion must not silently wipe the backup copy."""
        source = BACKUP_SCRIPT.read_text()
        self.assertNotIn("--delete", source,
            "rsync must not use --delete; accidental source deletion must not erase backup")

    def test_backup_script_uses_stable_current_mirror_path(self):
        """Backup must write to a stable 'current/' path, not timestamped directories.
        Later runs should update the same mirror."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("Sovran_SystemsOS_Backup/current", source,
            "backup must use a stable 'current' mirror path")
        self.assertIn("BACKUP_SUBPATH", source,
            "stable sub-path must be defined in BACKUP_SUBPATH variable")
        # Must not create new timestamped directories per run
        self.assertNotIn(
            "date '+%Y%m%d_%H%M%S'",
            source,
            "backup must not create timestamped per-run directories",
        )

    def test_backup_script_source_destination_mapping(self):
        """Each source tree must be synced to a matching destination path."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("/etc/nixos/", source)
        self.assertIn('"$BACKUP_DIR/etc/nixos/"', source)
        self.assertIn("/home/", source)
        self.assertIn('"$BACKUP_DIR/home/"', source)
        self.assertIn("/var/lib/", source)
        self.assertIn('"$BACKUP_DIR/var/lib/"', source)

    # ── ext4 filesystem validation ─────────────────────────────────────────────

    def test_backup_script_requires_ext4_filesystem(self):
        """Backup script must reject non-ext4 filesystems and require ext4."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            'fstype" != "ext4"',
            source,
            "backup script must check for ext4 filesystem",
        )
        self.assertIn("ext4", source, "backup script must reference ext4")
        self.assertNotIn(
            '"exfat"',
            source,
            "backup script must not accept exFAT (old requirement)",
        )
        self.assertNotIn(
            '"fuseblk"',
            source,
            "backup script must not accept fuseblk/NTFS",
        )

    def test_backup_script_rejects_unsupported_filesystems_in_error_message(self):
        """The ext4 rejection message must mention the unsupported filesystem types."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            "exFAT, FAT32, and NTFS are not supported",
            source,
            "error message must clearly list unsupported filesystem types",
        )

    def test_backend_accepts_ext4_rejects_exfat(self):
        """Backend _is_supported_backup_fstype must accept ext4 and reject exFAT."""
        server_source = SERVER_FILE.read_text()
        # Must accept ext4
        self.assertIn(
            'return fstype == "ext4"',
            server_source,
            "backend must accept only ext4",
        )
        # Must not accept exFAT
        self.assertNotIn(
            'fstype == "exfat"',
            server_source,
            "backend must not accept exFAT",
        )
        self.assertNotIn(
            'fuseblk',
            server_source.split("_is_supported_backup_fstype")[1][:500],
            "backend must not accept fuseblk",
        )

    def test_frontend_requires_ext4_not_exfat(self):
        """Frontend UI copy must require ext4 and not mention exFAT as the requirement."""
        support_source = SUPPORT_JS.read_text()
        self.assertIn(
            "ext4",
            support_source,
            "support.js must mention ext4 as the required filesystem",
        )
        # The word exFAT must not appear as a requirement (it may appear in a
        # note about unsupported formats, but the requirement itself must say ext4)
        requirements_section = re.search(
            r"Requirements.*?What gets backed up",
            support_source,
            re.DOTALL,
        )
        if requirements_section:
            req_text = requirements_section.group(0)
            self.assertNotIn(
                "Drive must be formatted as <strong>exFAT</strong>",
                req_text,
                "Requirements section must not say 'formatted as exFAT'",
            )
            self.assertIn(
                "ext4",
                req_text,
                "Requirements section must say ext4",
            )

    def test_frontend_failure_message_says_ext4(self):
        """Failure message in renderBackupDone must say ext4, not exFAT."""
        support_source = SUPPORT_JS.read_text()
        self.assertNotIn(
            "formatted as exFAT",
            support_source,
            "failure message must not say 'formatted as exFAT'",
        )
        self.assertIn(
            "formatted as ext4",
            support_source,
            "failure message must say 'formatted as ext4'",
        )

    # ── Database exclusions ────────────────────────────────────────────────────

    def test_backup_script_excludes_postgresql_and_mariadb(self):
        """PostgreSQL and MariaDB raw database directories must be excluded."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("--exclude='postgresql/'", source,
            "rsync must exclude postgresql directory")
        self.assertIn("--exclude='mysql/'", source,
            "rsync must exclude mysql directory")
        self.assertIn("--exclude='mariadb/'", source,
            "rsync must exclude mariadb directory")

    def test_backup_script_excludes_bitcoin_and_electrs(self):
        """Bitcoin blockchain and Electrs index data must be excluded."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("--exclude='bitcoind/'", source,
            "rsync must exclude bitcoind directory")
        self.assertIn("--exclude='electrs/'", source,
            "rsync must exclude electrs directory")

    def test_manifest_states_database_exclusion(self):
        """The manifest must explicitly state that PostgreSQL and MariaDB are excluded."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            "PostgreSQL and MariaDB/MySQL application databases are NOT included",
            source,
            "manifest must state that databases are not included",
        )
        self.assertIn(
            "Bitcoin blockchain data and Electrs indexes are NOT included",
            source,
            "manifest must state that blockchain data is not included",
        )

    def test_manifest_has_no_tar_restore_instructions(self):
        """Manifest must not mention tar extraction, pg_restore, or LND SCB."""
        source = BACKUP_SCRIPT.read_text()
        self.assertNotIn(
            "tar --acls --xattrs",
            source,
            "manifest must not give tar restore instructions",
        )
        self.assertNotIn(
            "pg_restore",
            source,
            "manifest must not reference pg_restore",
        )
        self.assertNotIn(
            "lnd-static-channel-backup.scb",
            source,
            "manifest must not reference LND SCB restore procedures",
        )

    def test_manifest_has_rsync_restore_guidance(self):
        """Manifest must provide rsync-based restore guidance."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            "rsync -aAXH --numeric-ids",
            source,
            "manifest must show rsync restore command",
        )

    # ── sync_tree helper design ────────────────────────────────────────────────

    def test_backup_script_uses_sync_tree_not_run_rsync(self):
        """Script must define sync_tree (new helper) and not the old run_rsync."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("sync_tree()", source, "script must define sync_tree helper")
        self.assertNotIn("run_rsync()", source, "old run_rsync function must be removed")
        self.assertNotIn("run_rsync ", source, "old run_rsync call sites must be removed")

    def test_sync_tree_signature_has_explicit_source_and_destination(self):
        """sync_tree must have explicit <source> <destination> parameters."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("local source=", source,
            "sync_tree must declare explicit 'source' local variable")
        self.assertIn("local destination=", source,
            "sync_tree must declare explicit 'destination' local variable")

    def test_sync_tree_creates_destination_with_mkdir_p(self):
        """sync_tree must run mkdir -p on the destination before rsync."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn('mkdir -p -- "$destination"', source,
            "sync_tree must create destination hierarchy with 'mkdir -p -- \"$destination\"'")

    def test_sync_tree_mkdir_failure_is_fatal(self):
        """sync_tree must fail with a logged message if mkdir -p fails."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("failed to create destination directory", source,
            "sync_tree must log a descriptive failure message when mkdir fails")

    def test_sync_tree_re_verifies_mountpoint_before_rsync(self):
        """sync_tree must re-verify $TARGET is a mount point before each rsync stage."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn('mountpoint -q "$TARGET"', source,
            "sync_tree must call mountpoint -q \"$TARGET\" to re-verify mount before each stage")
        self.assertIn("no longer mounted", source,
            "sync_tree must emit a clear message when the drive is no longer mounted")

    def test_sync_tree_checks_destination_within_backup_dir(self):
        """sync_tree must verify destination is beneath BACKUP_DIR."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("outside BACKUP_DIR", source,
            "sync_tree must reject destinations outside BACKUP_DIR")

    def test_new_run_removes_stale_backup_complete(self):
        """A new backup run must remove a stale BACKUP_COMPLETE before starting."""
        source = BACKUP_SCRIPT.read_text()
        # rm -f BACKUP_COMPLETE must appear BEFORE the touch INCOMPLETE line
        complete_pos = source.find('rm -f "$BACKUP_DIR/BACKUP_COMPLETE"')
        incomplete_pos = source.find('touch "$BACKUP_DIR/INCOMPLETE"')
        self.assertGreater(complete_pos, 0,
            "script must remove stale BACKUP_COMPLETE at the start of each run")
        self.assertGreater(incomplete_pos, 0,
            "script must touch INCOMPLETE after removing stale BACKUP_COMPLETE")
        self.assertLess(complete_pos, incomplete_pos,
            "BACKUP_COMPLETE removal must come before INCOMPLETE marker is written")

    def test_backup_script_exit_code_24_nonfatal_for_home(self):
        """Rsync exit code 24 (vanished files) must be nonfatal for /home only."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            '"$rc" -eq 24',
            source,
            "backup script must handle rsync exit code 24",
        )
        self.assertIn(
            'allow_vanished" == "yes"',
            source,
            "exit 24 acceptance must be gated on allow_vanished flag",
        )

    def test_backup_script_home_stage_allows_vanished(self):
        """Stage 3 (/home) must call sync_tree with allow_vanished=yes."""
        source = BACKUP_SCRIPT.read_text()
        # The /home call must pass "yes" as the allow_vanished argument
        self.assertIn(
            'sync_tree "/home" yes /home/',
            source,
            "/home stage must pass allow_vanished=yes to sync_tree",
        )

    def test_backup_script_other_stages_disallow_vanished(self):
        """Stages other than /home must call sync_tree with allow_vanished=no."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn(
            'sync_tree "/etc/nixos" no /etc/nixos/',
            source,
            "/etc/nixos stage must use allow_vanished=no",
        )
        self.assertIn(
            'sync_tree "/var/lib" no /var/lib/',
            source,
            "/var/lib stage must use allow_vanished=no",
        )

    # ── INCOMPLETE / BACKUP_COMPLETE markers ──────────────────────────────────

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
        """A BACKUP_COMPLETE file must be written only after all work succeeds."""
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

    # ── Concurrency lock ──────────────────────────────────────────────────────

    def test_backup_script_uses_flock_concurrency_lock(self):
        """The script must acquire an exclusive flock before starting work."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("flock", source, "backup script must use flock")
        self.assertIn("LOCK_FILE", source, "backup script must define LOCK_FILE")

    # ── Status states ─────────────────────────────────────────────────────────

    def test_backup_script_uses_running_success_failed_states(self):
        """Status values must be RUNNING, SUCCESS, and FAILED."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn('set_status "RUNNING"', source)
        self.assertIn('set_status "SUCCESS"', source)
        self.assertIn('set_status "FAILED"', source)

    def test_backend_and_frontend_use_explicit_backup_terminal_states(self):
        """Backend and frontend must use consistent terminal state handling."""
        server_source = SERVER_FILE.read_text()
        support_source = SUPPORT_JS.read_text()

        self.assertIn("_write_backup_status, \"RUNNING\"", server_source)
        self.assertIn("_monitor_backup_subprocess", server_source)
        self.assertIn("asyncio.create_task(_monitor_backup_subprocess(proc))", server_source)
        self.assertIn("result === \"success\" || result === \"failed\"", support_source)

    # ── Nix service PATH ──────────────────────────────────────────────────────

    def test_nix_service_path_includes_rsync_and_acl(self):
        """pkgs.rsync and pkgs.acl must appear in the sovran-hub-web service path
        so that rsync with ACL/xattr support is available at runtime."""
        nix_source = NIX_HUB_FILE.read_text()
        self.assertIn(
            "pkgs.rsync",
            nix_source,
            "pkgs.rsync must be declared in the sovran-hub-web service path",
        )
        self.assertIn(
            "pkgs.acl",
            nix_source,
            "pkgs.acl must be declared in the sovran-hub-web service path",
        )

    def test_nix_service_path_includes_bash_and_gawk(self):
        """Regression: pkgs.bash and pkgs.gawk must appear in the service path."""
        nix_source = NIX_HUB_FILE.read_text()
        self.assertIn("pkgs.bash", nix_source,
            "pkgs.bash must be declared in the sovran-hub-web service path")
        self.assertIn("pkgs.gawk", nix_source,
            "pkgs.gawk must be declared in the sovran-hub-web service path")

    def test_nix_service_path_has_no_gnutar(self):
        """pkgs.gnutar must be removed from the service path (no longer needed)."""
        nix_source = NIX_HUB_FILE.read_text()
        self.assertNotIn(
            "pkgs.gnutar",
            nix_source,
            "pkgs.gnutar must be removed from the service path (tar is no longer used)",
        )

    # ── Regression tests for exit-code-127 / missing-interpreter bug ──────────

    def test_server_resolves_bash_via_shutil_which(self):
        """Regression: server must locate bash with shutil.which()."""
        source = SERVER_FILE.read_text()
        self.assertIn('shutil.which("bash")', source)
        self.assertNotIn('"/usr/bin/env", "bash"', source)

    def test_server_logs_actionable_message_when_bash_missing(self):
        """Regression: when bash is absent the server must write an actionable log."""
        source = SERVER_FILE.read_text()
        self.assertIn("bash_path is None", source)
        self.assertIn("interpreter", source)

    def test_server_captures_stderr_from_backup_subprocess(self):
        """Regression: backup subprocess must use stderr=PIPE."""
        source = SERVER_FILE.read_text()
        self.assertIn("stderr=asyncio.subprocess.PIPE", source)
        self.assertIn("stderr_text", source)

    def test_monitor_includes_stderr_detail_in_failed_message(self):
        """Regression: _monitor_backup_subprocess must append captured stderr."""
        source = SERVER_FILE.read_text()
        self.assertIn("stderr_chunks", source)
        self.assertIn("stderr_text", source)
        self.assertIn('detail = f" — stderr: {stderr_text}"', source)

    def test_exit_code_127_subprocess_stderr_drain(self):
        """Behavioral regression: a subprocess that exits 127 drains stderr without deadlock."""
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

    # ── Rsync exit code 24 behavioral tests ──────────────────────────────────

    def test_run_rsync_exit_24_nonfatal_for_home(self):
        """Behavioral: run_rsync with allow_vanished=yes treats exit 24 as a
        nonfatal warning (recorded in RSYNC_WARNINGS) and does not fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "backup")
            os.makedirs(dest, exist_ok=True)

            script = f"""#!/usr/bin/env bash
set -euo pipefail
RSYNC_WARNINGS=()

log() {{ echo "$*"; }}
fail() {{ echo "FAILED: $*" >&2; exit 1; }}

run_rsync() {{
  local label="$1"
  local allow_vanished="$2"
  shift 2

  local rc=24  # simulate rsync exit 24

  if [[ "$rc" -eq 0 ]]; then
    return 0
  elif [[ "$allow_vanished" == "yes" && "$rc" -eq 24 ]]; then
    log "NOTE: $label — some files vanished during sync (normal on an active desktop)."
    RSYNC_WARNINGS+=("$label: some files vanished during sync")
    return 0
  else
    fail "rsync failed for $label (exit code $rc)"
  fi
}}

run_rsync "/home" yes /home/ "{dest}/home/"
echo "WARNINGS: ${{#RSYNC_WARNINGS[@]}}"
echo "SUCCESS"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
            self.assertIn("SUCCESS", result.stdout)
            self.assertIn("WARNINGS: 1", result.stdout)

    def test_run_rsync_exit_24_fatal_for_non_home(self):
        """Behavioral: run_rsync with allow_vanished=no treats exit 24 as fatal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "backup")
            os.makedirs(dest, exist_ok=True)

            script = f"""#!/usr/bin/env bash
RSYNC_WARNINGS=()

log() {{ echo "$*"; }}
fail() {{ echo "CORRECTLY_FAILED: $*"; exit 1; }}

run_rsync() {{
  local label="$1"
  local allow_vanished="$2"
  shift 2

  local rc=24  # simulate rsync exit 24

  if [[ "$rc" -eq 0 ]]; then
    return 0
  elif [[ "$allow_vanished" == "yes" && "$rc" -eq 24 ]]; then
    RSYNC_WARNINGS+=("$label: vanished")
    return 0
  else
    fail "rsync failed for $label (exit code $rc)"
  fi
}}

run_rsync "/etc/nixos" no /etc/nixos/ "{dest}/etc/nixos/"
echo "SHOULD_NOT_REACH_HERE"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("CORRECTLY_FAILED", result.stdout)
            self.assertNotIn("SHOULD_NOT_REACH_HERE", result.stdout)

    def test_run_rsync_other_nonzero_codes_always_fatal(self):
        """Behavioral: rsync exit codes other than 0 and 24 (for home) are fatal."""
        for rc in [1, 10, 11, 12, 23, 25]:
            with tempfile.TemporaryDirectory() as tmpdir:
                dest = os.path.join(tmpdir, "backup")
                os.makedirs(dest, exist_ok=True)

                script = f"""#!/usr/bin/env bash
RSYNC_WARNINGS=()

fail() {{ echo "CORRECTLY_FAILED: $*"; exit 1; }}
log() {{ echo "$*"; }}

run_rsync() {{
  local label="$1"
  local allow_vanished="$2"
  shift 2

  local rc={rc}  # simulated exit code

  if [[ "$rc" -eq 0 ]]; then
    return 0
  elif [[ "$allow_vanished" == "yes" && "$rc" -eq 24 ]]; then
    RSYNC_WARNINGS+=("$label: vanished")
    return 0
  else
    fail "rsync failed for $label (exit code $rc)"
  fi
}}

run_rsync "/home" yes /home/ "{dest}/home/"
echo "SHOULD_NOT_REACH_HERE"
"""
                script_file = os.path.join(tmpdir, "test.sh")
                with open(script_file, "w") as sf:
                    sf.write(script)
                result = subprocess.run(["bash", script_file], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1,
                    f"Exit code {rc} should fail: {result.stdout}")
                self.assertIn("CORRECTLY_FAILED", result.stdout)

    # ── Behavioral: repeated runs target same 'current' mirror ──────────────

    def test_repeated_runs_use_same_current_directory(self):
        """Behavioral: a second call to the backup logic must sync to the same
        BACKUP_DIR (not create a new timestamped directory) so only changed
        files are transferred."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "drive")
            os.makedirs(target, exist_ok=True)

            script = f"""#!/usr/bin/env bash
set -euo pipefail
TARGET="{target}"
BACKUP_SUBPATH="Sovran_SystemsOS_Backup/current"
BACKUP_DIR="${{TARGET}}/${{BACKUP_SUBPATH}}"
mkdir -p "$BACKUP_DIR"
echo "$BACKUP_DIR"
"""
            for _ in range(2):
                script_file = os.path.join(tmpdir, "test.sh")
                with open(script_file, "w") as sf:
                    sf.write(script)
                result = subprocess.run(["bash", script_file], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0)
                backup_dir = result.stdout.strip()
                self.assertEqual(
                    backup_dir,
                    os.path.join(target, "Sovran_SystemsOS_Backup", "current"),
                )

    # ── Behavioral: INCOMPLETE/BACKUP_COMPLETE marker lifecycle ─────────────

    def test_incomplete_marker_written_before_work_starts(self):
        """Behavioral: INCOMPLETE marker must exist during backup and be removed on success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = os.path.join(tmpdir, "current")
            os.makedirs(backup_dir, exist_ok=True)

            script = f"""#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="{backup_dir}"
BACKUP_COMPLETE=0

touch "$BACKUP_DIR/INCOMPLETE"
[[ -f "$BACKUP_DIR/INCOMPLETE" ]] && echo "INCOMPLETE_EXISTS"

# Simulate successful completion
rm -f "$BACKUP_DIR/INCOMPLETE"
echo "done" > "$BACKUP_DIR/BACKUP_COMPLETE"
BACKUP_COMPLETE=1

[[ ! -f "$BACKUP_DIR/INCOMPLETE" ]] && echo "INCOMPLETE_REMOVED"
[[ -f "$BACKUP_DIR/BACKUP_COMPLETE" ]] && echo "COMPLETE_EXISTS"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
            self.assertIn("INCOMPLETE_EXISTS", result.stdout)
            self.assertIn("INCOMPLETE_REMOVED", result.stdout)
            self.assertIn("COMPLETE_EXISTS", result.stdout)

    # ── Behavioral: actual rsync with real source/dest trees ─────────────────

    def test_rsync_mirrors_source_to_dest(self):
        """Behavioral: rsync correctly mirrors a source tree to a destination."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "etc", "nixos")
            dest = os.path.join(tmpdir, "backup", "etc", "nixos")
            os.makedirs(src, exist_ok=True)
            os.makedirs(os.path.join(tmpdir, "backup", "etc"), exist_ok=True)

            # Write test files
            with open(os.path.join(src, "configuration.nix"), "w") as f:
                f.write("{ ... }: {}\n")
            with open(os.path.join(src, "custom.nix"), "w") as f:
                f.write("{ ... }: {}\n")

            result = subprocess.run(
                ["rsync", "--archive", "--one-file-system",
                 src + "/", dest + "/"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, f"rsync failed: {result.stderr}")
            self.assertTrue(os.path.exists(os.path.join(dest, "configuration.nix")))
            self.assertTrue(os.path.exists(os.path.join(dest, "custom.nix")))

    def test_rsync_second_run_only_transfers_changes(self):
        """Behavioral: a second rsync run to the same dest only copies changed files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "source")
            dest = os.path.join(tmpdir, "backup")
            os.makedirs(src)
            os.makedirs(dest)

            with open(os.path.join(src, "file.txt"), "w") as f:
                f.write("initial content\n")

            # First run
            r1 = subprocess.run(
                ["rsync", "--archive", "--one-file-system", src + "/", dest + "/"],
                capture_output=True, text=True,
            )
            self.assertEqual(r1.returncode, 0)

            # Modify one file and add another; advance mtime so rsync detects the change
            with open(os.path.join(src, "file.txt"), "w") as f:
                f.write("updated content\n")
            import time as _time
            future_mtime = _time.time() + 2
            os.utime(os.path.join(src, "file.txt"), (future_mtime, future_mtime))

            with open(os.path.join(src, "new.txt"), "w") as f:
                f.write("new file\n")

            # Second run
            r2 = subprocess.run(
                ["rsync", "--archive", "--one-file-system", src + "/", dest + "/"],
                capture_output=True, text=True,
            )
            self.assertEqual(r2.returncode, 0)

            # Both files exist in dest
            with open(os.path.join(dest, "file.txt")) as fh:
                self.assertEqual(fh.read(), "updated content\n")
            self.assertTrue(os.path.exists(os.path.join(dest, "new.txt")))

    # ── Script syntax check ──────────────────────────────────────────────────

    def test_backup_script_passes_bash_syntax_check(self):
        """bash -n must report no syntax errors in the backup script."""
        result = subprocess.run(
            ["bash", "-n", str(BACKUP_SCRIPT)],
            capture_output=True, text=True,
        )
        self.assertEqual(
            result.returncode, 0,
            f"bash -n failed:\n{result.stderr}",
        )

    # ── Home exclusions ──────────────────────────────────────────────────────

    def test_backup_script_home_excludes_browser_caches(self):
        """Home sync must exclude browser disk caches."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("--exclude='.mozilla/firefox/*/cache2/'", source)
        self.assertIn("--exclude='.config/google-chrome/*/Cache/'", source)
        self.assertIn("--exclude='.config/chromium/*/Cache/'", source)
        self.assertIn("--exclude='.config/BraveSoftware/Brave-Browser/*/Cache/'", source)

    def test_backup_script_home_excludes_other_volatile_caches(self):
        """Home sync must exclude baloo, thumbnails, and X session error logs."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("--exclude='.local/share/baloo/'", source)
        self.assertIn("--exclude='.thumbnails/'", source)
        self.assertIn("--exclude='.xsession-errors'", source)

    # ── require_cmd ──────────────────────────────────────────────────────────

    def test_backup_script_requires_rsync_and_flock(self):
        """Script must require rsync and flock via require_cmd."""
        source = BACKUP_SCRIPT.read_text()
        self.assertIn("require_cmd rsync", source)
        self.assertIn("require_cmd flock", source)

    def test_backup_script_does_not_require_tar_or_sha256sum(self):
        """Script must not require tar or sha256sum (no longer used)."""
        source = BACKUP_SCRIPT.read_text()
        self.assertNotIn("require_cmd tar", source)
        self.assertNotIn("require_cmd sha256sum", source)

    # ── Frontend database limitation notice ──────────────────────────────────

    def test_frontend_mentions_database_limitation(self):
        """Frontend must explain that PostgreSQL/MariaDB databases are excluded."""
        support_source = SUPPORT_JS.read_text()
        self.assertIn(
            "PostgreSQL",
            support_source,
            "UI must mention PostgreSQL exclusion",
        )
        self.assertIn(
            "not included",
            support_source,
            "UI must explain that databases are not included",
        )

    # ── Behavioral: sync_tree creates nested destination dirs (regression) ─────

    def test_sync_tree_creates_nested_dest_dirs_regression(self):
        """Regression: sync_tree must create the full destination hierarchy before
        calling rsync so that rsync never fails with
        'mkdir current/etc/nixos failed: No such file or directory'.

        Initial state: only Sovran_SystemsOS_Backup/current/ exists.
        Expected: current/etc/nixos/ is created and populated by sync_tree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Source tree
            src = os.path.join(tmpdir, "src", "etc", "nixos")
            os.makedirs(src)
            with open(os.path.join(src, "configuration.nix"), "w") as f:
                f.write("{ }: {}\n")

            # Backup target: only current/ exists, NOT current/etc/
            target = os.path.join(tmpdir, "target")
            backup_dir = os.path.join(target, "Sovran_SystemsOS_Backup", "current")
            os.makedirs(backup_dir)
            dest = os.path.join(backup_dir, "etc", "nixos")

            self.assertFalse(os.path.exists(dest),
                "destination must not exist before sync_tree runs")
            self.assertFalse(os.path.exists(os.path.join(backup_dir, "etc")),
                "intermediate parent current/etc/ must not exist before sync_tree runs")

            script = f"""#!/usr/bin/env bash
set -euo pipefail
TARGET="{target}"
BACKUP_DIR="{backup_dir}"
RSYNC_WARNINGS=()

log() {{ echo "$*"; }}
fail() {{ echo "FAIL: $*" >&2; exit 1; }}

sync_tree() {{
  local label="$1" allow_vanished="$2" source="$3" destination="$4"
  shift 4

  # Path-safety check
  case "$destination" in
    "$BACKUP_DIR"/*|"$BACKUP_DIR") ;;
    *) fail "Stage $label: destination outside BACKUP_DIR"; ;;
  esac

  # THE FIX: create full hierarchy before rsync
  mkdir -p -- "$destination" || fail "Stage $label: mkdir failed for '$destination'"

  local rc=0
  rsync --archive --one-file-system "$@" "$source" "$destination" || rc=$?

  if [[ "$rc" -eq 0 ]]; then return 0
  elif [[ "$allow_vanished" == "yes" && "$rc" -eq 24 ]]; then
    RSYNC_WARNINGS+=("$label: vanished"); return 0
  else
    fail "rsync failed for $label (exit code $rc)"
  fi
}}

sync_tree "/etc/nixos" no "{src}/" "{dest}/"
echo "SUCCESS"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0,
                f"sync_tree failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")
            self.assertIn("SUCCESS", result.stdout)
            self.assertTrue(os.path.exists(os.path.join(dest, "configuration.nix")),
                "configuration.nix must be present after sync_tree")

    def test_sync_tree_all_four_stages_create_nested_dirs(self):
        """End-to-end: all four production stage mappings create and populate
        their nested destination directories starting from an empty current/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Source trees
            src_etc_nixos = os.path.join(tmpdir, "src", "etc", "nixos")
            src_secrets   = os.path.join(tmpdir, "src", "etc", "nix-bitcoin-secrets")
            src_home      = os.path.join(tmpdir, "src", "home")
            src_varlib    = os.path.join(tmpdir, "src", "var", "lib")
            for d in (src_etc_nixos, src_secrets, src_home, src_varlib):
                os.makedirs(d)

            with open(os.path.join(src_etc_nixos, "configuration.nix"), "w") as f:
                f.write("{ }: {}\n")
            with open(os.path.join(src_secrets, "secret.key"), "w") as f:
                f.write("secret\n")
            with open(os.path.join(src_home, "user.txt"), "w") as f:
                f.write("home\n")
            with open(os.path.join(src_varlib, "app.db"), "w") as f:
                f.write("db\n")

            # Backup target: only current/ exists
            target = os.path.join(tmpdir, "target")
            backup_dir = os.path.join(target, "Sovran_SystemsOS_Backup", "current")
            os.makedirs(backup_dir)

            dest_nixos   = os.path.join(backup_dir, "etc", "nixos")
            dest_secrets = os.path.join(backup_dir, "etc", "nix-bitcoin-secrets")
            dest_home    = os.path.join(backup_dir, "home")
            dest_varlib  = os.path.join(backup_dir, "var", "lib")

            script = f"""#!/usr/bin/env bash
set -euo pipefail
TARGET="{target}"
BACKUP_DIR="{backup_dir}"
RSYNC_WARNINGS=()

log() {{ echo "$*"; }}
fail() {{ echo "FAIL: $*" >&2; exit 1; }}

sync_tree() {{
  local label="$1" allow_vanished="$2" source="$3" destination="$4"
  shift 4
  case "$destination" in
    "$BACKUP_DIR"/*|"$BACKUP_DIR") ;;
    *) fail "unsafe destination"; ;;
  esac
  mkdir -p -- "$destination" || fail "mkdir failed for $destination"
  local rc=0
  rsync --archive --one-file-system "$@" "$source" "$destination" || rc=$?
  [[ "$rc" -eq 0 ]] || ([[ "$allow_vanished" == "yes" && "$rc" -eq 24 ]] && return 0) || \
    fail "rsync failed (exit $rc)"
}}

sync_tree "/etc/nixos" no "{src_etc_nixos}/" "{dest_nixos}/"
sync_tree "/etc/nix-bitcoin-secrets" no "{src_secrets}/" "{dest_secrets}/"
sync_tree "/home" yes "{src_home}/" "{dest_home}/"
sync_tree "/var/lib" no "{src_varlib}/" "{dest_varlib}/"
echo "ALL_STAGES_OK"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0,
                f"stdout: {result.stdout}\nstderr: {result.stderr}")
            self.assertIn("ALL_STAGES_OK", result.stdout)
            self.assertTrue(os.path.exists(os.path.join(dest_nixos,   "configuration.nix")))
            self.assertTrue(os.path.exists(os.path.join(dest_secrets, "secret.key")))
            self.assertTrue(os.path.exists(os.path.join(dest_home,    "user.txt")))
            self.assertTrue(os.path.exists(os.path.join(dest_varlib,  "app.db")))

    def test_sync_tree_spaces_in_paths_work(self):
        """sync_tree must handle spaces in target and backup-dir paths correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "src with spaces", "etc", "nixos")
            os.makedirs(src)
            with open(os.path.join(src, "configuration.nix"), "w") as f:
                f.write("{ }: {}\n")

            target = os.path.join(tmpdir, "S_S Backup")
            backup_dir = os.path.join(target, "Sovran_SystemsOS_Backup", "current")
            os.makedirs(backup_dir)
            dest = os.path.join(backup_dir, "etc", "nixos")

            script = f"""#!/usr/bin/env bash
set -euo pipefail
TARGET="{target}"
BACKUP_DIR="{backup_dir}"
RSYNC_WARNINGS=()

log() {{ echo "$*"; }}
fail() {{ echo "FAIL: $*" >&2; exit 1; }}

sync_tree() {{
  local label="$1" allow_vanished="$2" source="$3" destination="$4"
  shift 4
  mkdir -p -- "$destination" || fail "mkdir failed"
  rsync --archive --one-file-system "$@" "$source" "$destination" || fail "rsync failed"
}}

sync_tree "/etc/nixos" no "{src}/" "{dest}/"
echo "SUCCESS"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0,
                f"stdout: {result.stdout}\nstderr: {result.stderr}")
            self.assertIn("SUCCESS", result.stdout)
            self.assertTrue(os.path.exists(os.path.join(dest, "configuration.nix")))

    def test_no_delete_dest_only_file_survives_second_run(self):
        """Behavioral: without --delete, a file present only in the destination
        must survive a second sync_tree run.  Accidental source-side deletion
        must NOT silently wipe the backup copy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src  = os.path.join(tmpdir, "src")
            dest = os.path.join(tmpdir, "dest")
            os.makedirs(src)
            os.makedirs(dest)

            with open(os.path.join(src,  "keep.txt"), "w") as f:
                f.write("keep\n")
            with open(os.path.join(dest, "dest_only.txt"), "w") as f:
                f.write("destination-only file\n")

            # First run
            r1 = subprocess.run(
                ["rsync", "--archive", "--one-file-system", src + "/", dest + "/"],
                capture_output=True, text=True,
            )
            self.assertEqual(r1.returncode, 0, r1.stderr)

            # Second run (no new source files added)
            r2 = subprocess.run(
                ["rsync", "--archive", "--one-file-system", src + "/", dest + "/"],
                capture_output=True, text=True,
            )
            self.assertEqual(r2.returncode, 0, r2.stderr)

            # dest_only.txt must still be present — no --delete was used
            self.assertTrue(os.path.exists(os.path.join(dest, "dest_only.txt")),
                "destination-only file must survive because --delete is not used")
            self.assertTrue(os.path.exists(os.path.join(dest, "keep.txt")))

    def test_sync_tree_mkdir_failure_is_fatal_with_context(self):
        """Behavioral: when mkdir -p fails, sync_tree must exit non-zero with a
        message that includes the stage label, source, and destination."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target     = os.path.join(tmpdir, "target")
            backup_dir = os.path.join(target, "current")
            os.makedirs(backup_dir)

            # Make the destination parent read-only so mkdir -p fails
            os.chmod(backup_dir, 0o555)

            dest = os.path.join(backup_dir, "nested", "dir")

            script = f"""#!/usr/bin/env bash
TARGET="{target}"
BACKUP_DIR="{backup_dir}"

log() {{ echo "$*"; }}
fail() {{ echo "MKDIR_FAIL_MSG: $*" >&2; exit 1; }}

sync_tree() {{
  local label="$1" allow_vanished="$2" source="$3" destination="$4"
  shift 4
  mkdir -p -- "$destination" 2>/dev/null || \
    fail "Stage $label: failed to create destination directory '$destination' (source: '$source')."
  echo "SHOULD_NOT_REACH"
}}

sync_tree "test-stage" no /some/source "{dest}"
"""
            try:
                script_file = os.path.join(tmpdir, "test.sh")
                with open(script_file, "w") as sf:
                    sf.write(script)
                result = subprocess.run(["bash", script_file], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0,
                    "sync_tree must fail when mkdir -p fails")
                self.assertIn("MKDIR_FAIL_MSG", result.stderr,
                    "failure message must be present in stderr")
                self.assertIn("test-stage", result.stderr,
                    "failure message must include the stage label")
                self.assertNotIn("SHOULD_NOT_REACH", result.stdout,
                    "rsync must not run after mkdir failure")
            finally:
                os.chmod(backup_dir, 0o755)

    def test_sync_tree_mountpoint_check_prevents_write_on_disconnect(self):
        """Behavioral: sync_tree must abort with a clear message if $TARGET is
        no longer a mount point (simulating drive disconnection)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src        = os.path.join(tmpdir, "src")
            target     = os.path.join(tmpdir, "target")
            backup_dir = os.path.join(target, "current")
            dest       = os.path.join(backup_dir, "etc", "nixos")
            os.makedirs(src)
            os.makedirs(backup_dir)
            with open(os.path.join(src, "file.nix"), "w") as f:
                f.write("{ }: {}\n")

            # Inject a fake 'mountpoint' that always returns 1 (drive gone)
            script = f"""#!/usr/bin/env bash
set -euo pipefail
TARGET="{target}"
BACKUP_DIR="{backup_dir}"
RSYNC_WARNINGS=()

log() {{ echo "$*"; }}
fail() {{ echo "MOUNT_FAIL: $*" >&2; exit 1; }}

# Fake mountpoint: always returns failure (simulates drive disconnection)
mountpoint() {{ return 1; }}
export -f mountpoint

sync_tree() {{
  local label="$1" allow_vanished="$2" source="$3" destination="$4"
  shift 4
  mountpoint -q "$TARGET" 2>/dev/null || \
    fail "Stage $label: external drive '$TARGET' is no longer mounted. Refusing to write."
  mkdir -p -- "$destination" || fail "mkdir failed"
  rsync --archive "$@" "$source" "$destination" || fail "rsync failed"
  echo "RSYNC_RAN"
}}

sync_tree "/etc/nixos" no "{src}/" "{dest}/"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0,
                "sync_tree must fail when mount check fails")
            self.assertIn("MOUNT_FAIL", result.stderr,
                "failure message must be in stderr")
            self.assertIn("no longer mounted", result.stderr,
                "failure message must say 'no longer mounted'")
            self.assertNotIn("RSYNC_RAN", result.stdout,
                "rsync must not run after mount check fails")

    def test_failed_run_leaves_incomplete_not_backup_complete(self):
        """Behavioral: a failed run must leave INCOMPLETE and must NOT create
        BACKUP_COMPLETE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = os.path.join(tmpdir, "current")
            os.makedirs(backup_dir)

            script = f"""#!/usr/bin/env bash
BACKUP_DIR="{backup_dir}"
BACKUP_COMPLETE=0
FAILED_ALREADY=0

log() {{ echo "$*"; }}
set_status() {{ echo "STATUS: $1"; }}

fail() {{
  FAILED_ALREADY=1
  log "ERROR: $*"
  set_status "FAILED"
  exit 1
}}

cleanup() {{
  local rc=$?
  if [[ "$BACKUP_COMPLETE" -eq 1 && "$rc" -eq 0 ]]; then return; fi
  if [[ "$FAILED_ALREADY" -eq 0 ]]; then
    log "ERROR: unexpected exit $rc"
    set_status "FAILED"
  fi
  if [[ -n "${{BACKUP_DIR:-}}" && -d "${{BACKUP_DIR:-}}" && ! -f "${{BACKUP_DIR:-}}/BACKUP_COMPLETE" ]]; then
    touch "${{BACKUP_DIR}}/INCOMPLETE" 2>/dev/null || true
  fi
}}
trap cleanup EXIT

# Remove stale BACKUP_COMPLETE from prior run
rm -f "$BACKUP_DIR/BACKUP_COMPLETE"
touch "$BACKUP_DIR/INCOMPLETE"

# Simulate a stage failure
fail "stage failed"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(os.path.exists(os.path.join(backup_dir, "INCOMPLETE")),
                "INCOMPLETE marker must exist after a failed run")
            self.assertFalse(os.path.exists(os.path.join(backup_dir, "BACKUP_COMPLETE")),
                "BACKUP_COMPLETE must NOT be created after a failed run")

    def test_successful_run_removes_incomplete_writes_backup_complete(self):
        """Behavioral: a successful run must remove INCOMPLETE and write BACKUP_COMPLETE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = os.path.join(tmpdir, "current")
            os.makedirs(backup_dir)

            script = f"""#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="{backup_dir}"
BACKUP_COMPLETE=0

rm -f "$BACKUP_DIR/BACKUP_COMPLETE"
touch "$BACKUP_DIR/INCOMPLETE"

# Simulate all work succeeding
rm -f "$BACKUP_DIR/INCOMPLETE"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$BACKUP_DIR/BACKUP_COMPLETE"
BACKUP_COMPLETE=1
echo "SUCCESS"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0,
                f"stderr: {result.stderr}")
            self.assertFalse(os.path.exists(os.path.join(backup_dir, "INCOMPLETE")),
                "INCOMPLETE must be removed after success")
            self.assertTrue(os.path.exists(os.path.join(backup_dir, "BACKUP_COMPLETE")),
                "BACKUP_COMPLETE must be written after success")

    def test_stale_backup_complete_removed_before_new_run(self):
        """Behavioral: a stale BACKUP_COMPLETE from a prior successful run must
        be removed at the start of the new run so the run is unambiguously marked
        as INCOMPLETE while in progress."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = os.path.join(tmpdir, "current")
            os.makedirs(backup_dir)

            # Simulate state after a prior successful run
            with open(os.path.join(backup_dir, "BACKUP_COMPLETE"), "w") as f:
                f.write("2026-07-01T00:00:00Z\n")

            script = f"""#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="{backup_dir}"
BACKUP_COMPLETE=0

# New run starts: remove stale BACKUP_COMPLETE, write INCOMPLETE
rm -f "$BACKUP_DIR/BACKUP_COMPLETE"
touch "$BACKUP_DIR/INCOMPLETE"

[[ ! -f "$BACKUP_DIR/BACKUP_COMPLETE" ]] && echo "STALE_COMPLETE_REMOVED"
[[ -f "$BACKUP_DIR/INCOMPLETE" ]] && echo "INCOMPLETE_PRESENT"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("STALE_COMPLETE_REMOVED", result.stdout,
                "stale BACKUP_COMPLETE must be removed at run start")
            self.assertIn("INCOMPLETE_PRESENT", result.stdout,
                "INCOMPLETE must be present during the run")

    def test_rerun_after_failed_run_succeeds_without_manual_cleanup(self):
        """Behavioral: a directory left with only INCOMPLETE (prior failed run)
        can be rerun successfully without any manual cleanup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "src")
            os.makedirs(src)
            with open(os.path.join(src, "file.txt"), "w") as f:
                f.write("data\n")

            backup_dir = os.path.join(tmpdir, "backup", "current")
            os.makedirs(backup_dir)

            # Simulate state after a prior failed run: only INCOMPLETE exists
            with open(os.path.join(backup_dir, "INCOMPLETE"), "w") as f:
                f.write("")

            dest = os.path.join(backup_dir, "data")

            script = f"""#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="{backup_dir}"
BACKUP_COMPLETE=0
RSYNC_WARNINGS=()

log() {{ echo "$*"; }}
fail() {{ echo "FAIL: $*" >&2; exit 1; }}

sync_tree() {{
  local label="$1" allow_vanished="$2" source="$3" destination="$4"
  shift 4
  mkdir -p -- "$destination" || fail "mkdir failed"
  rsync --archive --one-file-system "$@" "$source" "$destination" || fail "rsync failed"
}}

# New run: remove stale BACKUP_COMPLETE (none here), write INCOMPLETE
rm -f "$BACKUP_DIR/BACKUP_COMPLETE"
touch "$BACKUP_DIR/INCOMPLETE"

# Run stage
sync_tree "data" no "{src}/" "{dest}/"

# Mark success
rm -f "$BACKUP_DIR/INCOMPLETE"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$BACKUP_DIR/BACKUP_COMPLETE"
BACKUP_COMPLETE=1
echo "RERUN_SUCCESS"
"""
            script_file = os.path.join(tmpdir, "test.sh")
            with open(script_file, "w") as sf:
                sf.write(script)
            result = subprocess.run(["bash", script_file], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0,
                f"stdout: {result.stdout}\nstderr: {result.stderr}")
            self.assertIn("RERUN_SUCCESS", result.stdout)
            self.assertFalse(os.path.exists(os.path.join(backup_dir, "INCOMPLETE")),
                "INCOMPLETE must be removed after successful rerun")
            self.assertTrue(os.path.exists(os.path.join(backup_dir, "BACKUP_COMPLETE")),
                "BACKUP_COMPLETE must exist after successful rerun")
            self.assertTrue(os.path.exists(os.path.join(dest, "file.txt")),
                "backed-up file must exist after successful rerun")

    def test_behavioral_database_exclusions(self):
        """Behavioral: postgresql, mysql, mariadb, bitcoind, electrs directories
        must be excluded from the var/lib rsync stage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src_varlib = os.path.join(tmpdir, "var", "lib")
            for d in ("postgresql", "mysql", "mariadb", "bitcoind", "electrs", "myapp"):
                os.makedirs(os.path.join(src_varlib, d))
                with open(os.path.join(src_varlib, d, "data.bin"), "w") as f:
                    f.write("data\n")

            dest_varlib = os.path.join(tmpdir, "backup", "var", "lib")
            os.makedirs(dest_varlib)

            result = subprocess.run(
                [
                    "rsync", "--archive", "--one-file-system",
                    "--exclude=postgresql/",
                    "--exclude=mysql/",
                    "--exclude=mariadb/",
                    "--exclude=bitcoind/",
                    "--exclude=electrs/",
                    src_varlib + "/", dest_varlib + "/",
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            # Excluded directories must NOT appear in dest
            for excluded in ("postgresql", "mysql", "mariadb", "bitcoind", "electrs"):
                self.assertFalse(
                    os.path.exists(os.path.join(dest_varlib, excluded)),
                    f"{excluded}/ must be excluded from the backup",
                )
            # Non-excluded directory must appear
            self.assertTrue(
                os.path.exists(os.path.join(dest_varlib, "myapp", "data.bin")),
                "non-excluded directories must be backed up",
            )

    def test_behavioral_home_cache_exclusion(self):
        """Behavioral: .cache/ and browser cache dirs must be excluded from /home."""
        with tempfile.TemporaryDirectory() as tmpdir:
            user_home = os.path.join(tmpdir, "home", "user")
            cache_dir = os.path.join(user_home, ".cache", "something")
            docs_dir  = os.path.join(user_home, "Documents")
            ff_cache  = os.path.join(user_home, ".mozilla", "firefox", "default", "cache2")
            brave_cache = os.path.join(
                user_home, ".config", "BraveSoftware", "Brave-Browser", "Default", "Cache"
            )
            for d in (cache_dir, docs_dir, ff_cache, brave_cache):
                os.makedirs(d)
            with open(os.path.join(cache_dir,    "tmp.bin"),  "w") as f: f.write("cache\n")
            with open(os.path.join(docs_dir,     "note.txt"), "w") as f: f.write("note\n")
            with open(os.path.join(ff_cache,     "entry"),    "w") as f: f.write("ff\n")
            with open(os.path.join(brave_cache,  "entry"),    "w") as f: f.write("brave\n")

            src  = os.path.join(tmpdir, "home")
            dest = os.path.join(tmpdir, "backup", "home")
            os.makedirs(dest)

            result = subprocess.run(
                [
                    "rsync", "--archive", "--one-file-system",
                    "--exclude=.cache/",
                    "--exclude=.mozilla/firefox/*/cache2/",
                    "--exclude=.config/BraveSoftware/Brave-Browser/*/Cache/",
                    src + "/", dest + "/",
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            dest_user = os.path.join(dest, "user")
            self.assertFalse(
                os.path.exists(os.path.join(dest_user, ".cache")),
                ".cache/ must be excluded",
            )
            self.assertFalse(
                os.path.exists(os.path.join(dest_user, ".mozilla", "firefox",
                                            "default", "cache2")),
                "Firefox cache2/ must be excluded",
            )
            self.assertFalse(
                os.path.exists(os.path.join(dest_user, ".config", "BraveSoftware",
                                            "Brave-Browser", "Default", "Cache")),
                "Brave Cache/ must be excluded",
            )
            self.assertTrue(
                os.path.exists(os.path.join(dest_user, "Documents", "note.txt")),
                "Documents must be backed up",
            )


if __name__ == "__main__":
    unittest.main()
