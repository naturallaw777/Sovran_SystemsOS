"""Regression guards for the shared PostgreSQL major-version policy."""

import os
import shlex
import subprocess
import tempfile
import textwrap
import unittest


_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class PostgreSQLMajorUpgradePolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = _read("configuration.nix")
        cls.runbook = _read("docs", "postgresql-major-upgrades.md")
        cls.readme = _read("README.md")
        cls.module = _read("modules", "postgresql-major-upgrade.nix")
        cls.modules_imports = _read("modules", "modules.nix")
        cls.nextcloud = _read("modules", "nextcloud.nix")
        cls.synapse = _read("modules", "synapse.nix")

    def test_major_package_is_explicit(self):
        self.assertIn("package = pkgs.postgresql_18;", self.config)

    def test_state_version_remains_unchanged(self):
        self.assertIn('system.stateVersion = "22.05";', self.config)

    def test_fresh_cluster_settings_and_checksum_default(self):
        self.assertIn('"--encoding=UTF8"', self.config)
        self.assertIn('"--locale=${config.i18n.defaultLocale}"', self.config)
        # --no-data-checksums is a migration-time match for old clusters,
        # not the default for a new installation.
        self.assertNotIn("--no-data-checksums", self.config)

    def test_runbook_covers_copy_check_post_upgrade_and_retention(self):
        self.assertIn("docs/postgresql-major-upgrades.md", self.readme)
        for required in (
            "--check --copy",
            "--no-data-checksums",
            "update_extensions.sql",
            "--analyze-in-stages --missing-stats-only",
            "--analyze-only",
            "SHOW data_directory",
            "delete_old_cluster.sh",
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.runbook)

    def test_automatic_upgrade_is_a_postgresql_prestart_gate(self):
        self.assertIn("./postgresql-major-upgrade.nix", self.modules_imports)
        self.assertIn("preStart = lib.mkBefore", self.module)
        self.assertIn("stopIfChanged = true;", self.module)
        self.assertIn("postgresql-major-upgrade.sh", self.module)
        self.assertIn('TimeoutStartSec = "infinity";', self.module)
        self.assertIn("builtins.baseNameOf dataDir == targetMajor", self.module)
        self.assertNotIn("systemd.services.postgresql-major-upgrade =", self.module)

    def test_database_clients_stop_with_postgres_and_wait_for_setup(self):
        self.assertIn('partOf = [ "postgresql.service" ];', self.synapse)
        self.assertIn('requires = [ "postgresql-setup.service" ];', self.synapse)
        self.assertIn('partOf = [ "postgresql.service" ];', self.nextcloud)
        self.assertIn('requires = [ "postgresql.service" "postgresql-setup.service" ];', self.nextcloud)
        self.assertIn('requires = [ "postgresql-setup.service" ];', self.nextcloud)
        self.assertIn('systemd.services.postgresql-setup = {', self.module)
        self.assertIn('partOf = [ "postgresql.service" ];', self.module)
        self.assertIn('postgresql-major-setup-trigger', self.module)
        self.assertIn('postgresql-major-trigger', self.synapse)
        self.assertIn('postgresql-major-trigger', self.nextcloud)

    def test_post_upgrade_maintenance_is_gated_and_ordered(self):
        marker = "  postUpgradeMaintenance = ''\n"
        start = self.module.index(marker) + len(marker)
        end = self.module.index("\n  '';", start)
        body = self.module[start:end].replace("''${", "${")

        with tempfile.TemporaryDirectory() as directory:
            root = os.path.abspath(directory)
            data_root = os.path.join(root, "postgresql")
            target_dir = os.path.join(data_root, "18")
            os.makedirs(target_dir)
            state_file = os.path.join(data_root, ".upgrade.state")
            update_sql = os.path.join(target_dir, "update_extensions.sql")
            call_log = os.path.join(root, "calls.log")
            fake_bin = os.path.join(root, "bin")
            os.mkdir(fake_bin)
            with open(state_file, "w", encoding="ascii") as stream:
                stream.write("MIGRATED\n")
            with open(update_sql, "w", encoding="ascii") as stream:
                stream.write("-- fake extension update\n")

            substitutions = {
                "${lib.escapeShellArg targetMajor}": shlex.quote("18"),
                "${lib.escapeShellArg dataDir}": shlex.quote(target_dir),
                "${lib.escapeShellArg stateFile}": shlex.quote(state_file),
                '${lib.escapeShellArg "${dataDir}/update_extensions.sql"}': shlex.quote(update_sql),
            }
            for old, new in substitutions.items():
                body = body.replace(old, new)
            body = textwrap.dedent(body)

            tools = {
                "psql": """case "$*" in
  *server_version_num*) printf '%s\\n' "$FAKE_SERVER_MAJOR" ;;
  *'SHOW data_directory'*) printf '%s\\n' "$FAKE_SERVER_DATA_DIR" ;;
  *) printf 'psql %s\\n' "$*" >> "$CALL_LOG" ;;
esac
""",
                "vacuumdb": """printf 'vacuumdb %s\\n' "$*" >> "$CALL_LOG"
""",
            }
            for name, content in tools.items():
                path = os.path.join(fake_bin, name)
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write("#!/usr/bin/env bash\nset -euo pipefail\n" + content)
                os.chmod(path, 0o755)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": fake_bin + os.pathsep + env.get("PATH", ""),
                    "CALL_LOG": call_log,
                    "FAKE_SERVER_MAJOR": "18",
                    "FAKE_SERVER_DATA_DIR": target_dir,
                }
            )
            completed = subprocess.run(
                ["bash", "-c", body], env=env, text=True, capture_output=True, check=False
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            with open(state_file, encoding="ascii") as stream:
                self.assertEqual(stream.read().strip(), "COMPLETE")
            with open(call_log, encoding="utf-8") as stream:
                calls = stream.read().splitlines()
            self.assertEqual(
                [line.split()[0] for line in calls], ["psql", "vacuumdb", "vacuumdb"]
            )
            self.assertIn("--analyze-in-stages --missing-stats-only", calls[1])
            self.assertIn("--analyze-only", calls[2])

            # A setup unit that runs against the previous major must leave the
            # MIGRATED marker untouched and must not apply target extension SQL.
            with open(state_file, "w", encoding="ascii") as stream:
                stream.write("MIGRATED\n")
            old_data_dir = os.path.join(data_root, "14")
            os.mkdir(old_data_dir)
            env["FAKE_SERVER_MAJOR"] = "14"
            env["FAKE_SERVER_DATA_DIR"] = old_data_dir
            os.remove(call_log)
            completed = subprocess.run(
                ["bash", "-c", body], env=env, text=True, capture_output=True, check=False
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            with open(state_file, encoding="ascii") as stream:
                self.assertEqual(stream.read().strip(), "MIGRATED")
            self.assertFalse(os.path.exists(call_log))

    def test_configuration_promises_automatic_not_manual_migration(self):
        self.assertIn("Supported major upgrades run", self.config)
        self.assertIn("automatically on service activation", self.config)
        self.assertIn("Normal automatic path", self.runbook)


if __name__ == "__main__":
    unittest.main()
