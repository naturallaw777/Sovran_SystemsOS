import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SCRIPT = REPO_ROOT / "app" / "sovran_systemsos_web" / "scripts" / "sovran-hub-backup.sh"
SERVER_FILE = REPO_ROOT / "app" / "sovran_systemsos_web" / "server.py"
SUPPORT_JS = REPO_ROOT / "app" / "sovran_systemsos_web" / "static" / "js" / "support.js"


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


if __name__ == "__main__":
    unittest.main()
