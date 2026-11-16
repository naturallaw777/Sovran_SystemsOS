"""Exercise the automatic PostgreSQL migration script with fake PostgreSQL tools."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "postgresql-major-upgrade.sh"


class PostgreSQLMajorUpgradeScript(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.data_root = self.root / "var" / "lib" / "postgresql"
        self.data_root.mkdir(parents=True)
        self.source_major = 14
        self.source_data = self.data_root / str(self.source_major)
        self.source_data.mkdir()
        (self.source_data / "PG_VERSION").write_text("14\n", encoding="ascii")

        self.old_bin = self.root / "old-bin"
        self.new_bin = self.root / "new-bin"
        self.fake_bin = self.root / "fake-bin"
        self.old_bin.mkdir()
        self.new_bin.mkdir()
        self.fake_bin.mkdir()
        self.state_file = self.data_root / ".upgrade.state"
        self.log_file = self.data_root / ".upgrade.log"
        self.fake_log = self.root / "fake-tools.log"
        self.initdb_args_file = self.root / "initdb-args.log"
        self._write_fake_tools()

    def _write_executable(self, path, content):
        path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + content, encoding="utf-8")
        path.chmod(0o755)

    def _write_fake_tools(self):
        self._write_executable(
            self.fake_bin / "df",
            "printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'\nprintf 'fake 100000000 1 99999999 1%% /fake\\n'\n",
        )
        self._write_executable(
            self.old_bin / "pg_controldata",
            "printf '%s\\n' 'Data page checksum version: 0'\n",
        )
        self._write_executable(
            self.old_bin / "pg_ctl",
            """printf 'pg_ctl %s\n' "$*" >> "$FAKE_LOG"
case " $* " in
  *" status "*) [[ -f "$PG_CTL_ACTIVE" ]] ;;
  *" start "*) touch "$PG_CTL_ACTIVE" ;;
  *" stop "*) rm -f "$PG_CTL_ACTIVE" ;;
esac
""",
        )
        self._write_executable(
            self.old_bin / "psql",
            """if [[ "$*" == *datlocprovider* ]]; then
  printf 'c\\n'
else
  printf 'UTF8|C.UTF-8|C.UTF-8\\n'
fi
""",
        )
        self._write_executable(
            self.new_bin / "initdb",
            """printf 'initdb %s\\n' "$*" >> "$FAKE_LOG"
printf '%s\\n' "$*" > "$INITDB_ARGS_FILE"
while (($#)); do
  if [[ "$1" == -D ]]; then
    target="$2"
    shift 2
  else
    shift
  fi
done
mkdir -p "$target"
if [[ "${FAKE_FAIL_INITDB:-0}" == 1 ]]; then
  printf 'partial\\n' > "$target/partial-initdb"
  exit 43
fi
printf '%s\\n' "$SOVRAN_PG_TARGET_MAJOR" > "$target/PG_VERSION"
""",
        )
        self._write_executable(
            self.new_bin / "pg_upgrade",
            """printf 'pg_upgrade %s\\n' "$*" >> "$FAKE_LOG"
if [[ "${FAKE_FAIL_UPGRADE:-0}" == 1 ]]; then
  exit 42
fi
""",
        )

    def _environment(self, target_major=18, source_major=None, fail_upgrade=False, fail_initdb=False):
        source_major = self.source_major if source_major is None else source_major
        env = os.environ.copy()
        env.update(
            {
                "SOVRAN_PG_TARGET_MAJOR": str(target_major),
                "SOVRAN_PG_DATA_DIR": str(self.data_root / str(target_major)),
                "SOVRAN_PG_DATA_ROOT": str(self.data_root),
                "SOVRAN_PG_NEW_BIN": str(self.new_bin),
                "SOVRAN_PG_STATE_FILE": str(self.state_file),
                "SOVRAN_PG_LOG_FILE": str(self.log_file),
                "SOVRAN_PG_INITDB_ARG_COUNT": "2",
                "SOVRAN_PG_INITDB_ARG_0": "--encoding=UTF8",
                "SOVRAN_PG_INITDB_ARG_1": "--locale=en_US.UTF-8",
                f"SOVRAN_PG_OLD_BIN_{source_major}": str(self.old_bin),
                "FAKE_LOG": str(self.fake_log),
                "PG_CTL_ACTIVE": str(self.root / "pg_ctl-active"),
                "INITDB_ARGS_FILE": str(self.initdb_args_file),
                "FAKE_FAIL_UPGRADE": "1" if fail_upgrade else "0",
                "FAKE_FAIL_INITDB": "1" if fail_initdb else "0",
                "PATH": str(self.fake_bin) + os.pathsep + env.get("PATH", ""),
            }
        )
        return env

    def _run(self, **kwargs):
        return subprocess.run(
            ["bash", str(_SCRIPT)],
            cwd=self.root,
            env=self._environment(**kwargs),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_auto_migration_matches_source_settings_and_marks_migrated(self):
        result = self._run()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.state_file.read_text(encoding="ascii").strip(), "MIGRATED")
        self.assertEqual(
            (self.data_root / "18" / "PG_VERSION").read_text(encoding="ascii").strip(),
            "18",
        )
        self.assertFalse((self.root / "pg_ctl-active").exists())
        self.assertEqual(list(self.data_root.glob(".sovran-pg-upgrade-18.socket.*")), [])

        args = self.initdb_args_file.read_text(encoding="utf-8")
        self.assertIn("--lc-collate=C.UTF-8", args)
        self.assertIn("--lc-ctype=C.UTF-8", args)
        self.assertIn("--locale-provider=libc", args)
        self.assertIn("--no-data-checksums", args)
        self.assertNotIn("--locale=en_US.UTF-8", args)

        invocations = self.fake_log.read_text(encoding="utf-8")
        self.assertIn("--check --copy", invocations)
        self.assertIn("--old-datadir", invocations)
        self.assertTrue(invocations.rstrip().endswith("--copy"))

    def test_failed_copy_is_marked_and_next_activation_retries_safely(self):
        first = self._run(fail_upgrade=True)
        self.assertNotEqual(first.returncode, 0)
        self.assertEqual(self.state_file.read_text(encoding="ascii").strip(), "FAILED")

        retry = self._run(fail_upgrade=False)
        self.assertEqual(retry.returncode, 0, retry.stdout + retry.stderr)
        self.assertEqual(self.state_file.read_text(encoding="ascii").strip(), "MIGRATED")
        self.assertEqual(
            (self.data_root / "18" / "PG_VERSION").read_text(encoding="ascii").strip(),
            "18",
        )

    def test_partial_initdb_target_is_removed_before_retry(self):
        first = self._run(fail_initdb=True)
        self.assertNotEqual(first.returncode, 0)
        self.assertEqual(self.state_file.read_text(encoding="ascii").strip(), "FAILED")
        target = self.data_root / "18"
        self.assertTrue((target / "partial-initdb").exists())
        self.assertFalse((target / "PG_VERSION").exists())

        retry = self._run()
        self.assertEqual(retry.returncode, 0, retry.stdout + retry.stderr)
        self.assertEqual(self.state_file.read_text(encoding="ascii").strip(), "MIGRATED")
        self.assertFalse((target / "partial-initdb").exists())

    def test_existing_target_is_not_migrated_again_without_a_state_marker(self):
        target = self.data_root / "18"
        target.mkdir()
        (target / "PG_VERSION").write_text("18\n", encoding="ascii")

        result = self._run()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.state_file.exists())
        self.assertFalse(self.fake_log.exists())

    def test_symlink_target_is_refused_without_touching_referent(self):
        target = self.data_root / "18"
        referent = self.root / "valuable-target"
        referent.mkdir()
        (referent / "keep.txt").write_text("preserve me", encoding="ascii")
        target.symlink_to(referent, target_is_directory=True)

        result = self._run()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target data directory is a symlink", result.stdout)
        self.assertEqual((referent / "keep.txt").read_text(encoding="ascii"), "preserve me")
        self.assertFalse(self.fake_log.exists())

    def test_active_source_is_refused_without_stopping_it(self):
        active_marker = self.root / "pg_ctl-active"
        active_marker.touch()

        result = self._run()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source cluster is already running", result.stdout)
        self.assertTrue(active_marker.exists())
        self.assertEqual(self.state_file.read_text(encoding="ascii").strip(), "FAILED")
        self.assertNotIn(" -m fast -w stop", self.fake_log.read_text(encoding="utf-8"))

    def test_pg14_target_does_not_receive_newer_locale_provider_option(self):
        # This exercises the script's compatibility guard; the NixOS module
        # normally retains old binaries for majors that exist in the pin.
        self.source_major = 13
        shutil.rmtree(self.data_root / "14")
        self.source_data = self.data_root / "13"
        self.source_data.mkdir()
        (self.source_data / "PG_VERSION").write_text("13\n", encoding="ascii")

        result = self._run(target_major=14, source_major=13)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        args = self.initdb_args_file.read_text(encoding="utf-8")
        self.assertNotIn("--locale-provider", args)
        self.assertIn("--lc-collate=C.UTF-8", args)


if __name__ == "__main__":
    unittest.main()
