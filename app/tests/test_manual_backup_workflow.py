import asyncio
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SCRIPT = REPO_ROOT / "app" / "sovran_systemsos_web" / "scripts" / "sovran-hub-backup.sh"
SERVER_FILE = REPO_ROOT / "app" / "sovran_systemsos_web" / "server.py"
SUPPORT_JS = REPO_ROOT / "app" / "sovran_systemsos_web" / "static" / "js" / "support.js"
NIX_HUB_FILE = REPO_ROOT / "modules" / "core" / "sovran-hub.nix"


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


if __name__ == "__main__":
    unittest.main()
