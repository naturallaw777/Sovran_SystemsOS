"""Regression tests for Manual Backup hardening and Safe Eject workflow."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_APP_PARENT = os.path.join(_REPO_ROOT, "app")
if _APP_PARENT not in sys.path:
    sys.path.insert(0, _APP_PARENT)

from sovran_systemsos_web import backup_ops  # noqa: E402


def _read(*rel_parts: str) -> str:
    with open(os.path.join(_REPO_ROOT, *rel_parts), "r", encoding="utf-8") as f:
        return f.read()


class TestBackupLockAndStaleRecovery(unittest.TestCase):
    """flock probing and stale RUNNING recovery must be accurate."""

    def test_lock_held_detected_and_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_file = os.path.join(tmp, "sovran-hub-backup.lock")
            self.assertFalse(backup_ops.is_backup_lock_held(lock_file))

            proc = subprocess.Popen(
                [
                    "bash",
                    "-c",
                    f'exec {{fd}}>>"{lock_file}"; flock -n "$fd"; echo READY; sleep 30',
                ],
                stdout=subprocess.PIPE,
                text=True,
            )
            try:
                line = proc.stdout.readline().strip()
                self.assertEqual(line, "READY")
                self.assertTrue(backup_ops.is_backup_lock_held(lock_file))
            finally:
                if proc.stdout is not None:
                    proc.stdout.close()
                proc.terminate()
                proc.wait(timeout=5)

            self.assertFalse(backup_ops.is_backup_lock_held(lock_file))

    def test_recover_stale_running_marks_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            status_file = os.path.join(tmp, "backup.status")
            log_file = os.path.join(tmp, "backup.log")
            lock_file = os.path.join(tmp, "backup.lock")

            with open(status_file, "w", encoding="utf-8") as f:
                f.write("RUNNING\n")
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("Stage 1 started\n")

            recovered = backup_ops.recover_stale_backup_status(
                status_file,
                log_file,
                lock_file,
                is_unit_active_fn=lambda: False,
                launch_grace_active=False,
            )
            self.assertTrue(recovered)
            with open(status_file, "r", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "FAILED")
            with open(log_file, "r", encoding="utf-8") as f:
                self.assertIn("interrupted before completion", f.read())

    def test_recover_respects_active_lock_unit_and_grace_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            status_file = os.path.join(tmp, "backup.status")
            log_file = os.path.join(tmp, "backup.log")
            lock_file = os.path.join(tmp, "backup.lock")

            with open(status_file, "w", encoding="utf-8") as f:
                f.write("RUNNING")

            # Grace window active -> must not mark FAILED
            self.assertFalse(
                backup_ops.recover_stale_backup_status(
                    status_file, log_file, lock_file,
                    is_unit_active_fn=lambda: False,
                    launch_grace_active=True,
                )
            )
            # Systemd unit active -> must not mark FAILED
            self.assertFalse(
                backup_ops.recover_stale_backup_status(
                    status_file, log_file, lock_file,
                    is_unit_active_fn=lambda: True,
                    launch_grace_active=False,
                )
            )
            with open(status_file, "r", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "RUNNING")

    def test_recover_ignores_terminal_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            status_file = os.path.join(tmp, "backup.status")
            log_file = os.path.join(tmp, "backup.log")
            lock_file = os.path.join(tmp, "backup.lock")

            for terminal in ("SUCCESS", "FAILED"):
                with open(status_file, "w", encoding="utf-8") as f:
                    f.write(terminal)
                self.assertFalse(
                    backup_ops.recover_stale_backup_status(
                        status_file, log_file, lock_file,
                    )
                )


class TestMountHolderDetection(unittest.TestCase):
    """/proc inspection must surface friendly names of processes holding a USB mount."""

    def test_finds_cwd_and_open_fd_with_spaces_in_mount_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            mnt = os.path.join(tmp, "run", "media", "free", "S_S Backup")
            sub = os.path.join(mnt, "Sovran_SystemsOS_Backup", "current")
            other = os.path.join(tmp, "home", "free")
            os.makedirs(sub)
            os.makedirs(other)
            target_file = os.path.join(sub, "manifest.txt")
            with open(target_file, "w", encoding="utf-8") as f:
                f.write("ok")

            proc_root = os.path.join(tmp, "proc")
            # PID 1001: nautilus with cwd inside the backup drive
            pid1 = os.path.join(proc_root, "1001")
            os.makedirs(os.path.join(pid1, "fd"))
            os.symlink(sub, os.path.join(pid1, "cwd"))
            with open(os.path.join(pid1, "comm"), "w", encoding="utf-8") as f:
                f.write("nautilus\n")

            # PID 1002: fish shell with an open fd to a file on the drive
            pid2 = os.path.join(proc_root, "1002")
            os.makedirs(os.path.join(pid2, "fd"))
            os.symlink(other, os.path.join(pid2, "cwd"))
            os.symlink(target_file, os.path.join(pid2, "fd", "3"))
            with open(os.path.join(pid2, "comm"), "w", encoding="utf-8") as f:
                f.write("fish\n")

            # PID 1003: unrelated process
            pid3 = os.path.join(proc_root, "1003")
            os.makedirs(os.path.join(pid3, "fd"))
            os.symlink(other, os.path.join(pid3, "cwd"))
            with open(os.path.join(pid3, "comm"), "w", encoding="utf-8") as f:
                f.write("systemd\n")

            holders = backup_ops.find_mount_holders(mnt, proc_root=proc_root)
            self.assertEqual(holders, ["Files (nautilus)", "Terminal (fish)"])


class TestSafeDriveEject(unittest.TestCase):
    """eject_external_drive must enforce safety guards and report busy holders clearly."""

    def test_rejects_internal_and_outside_paths(self):
        for bad in (
            "",
            "/",
            "/boot/efi",
            "/etc/nixos",
            "/run/media",
            "/run/media/Second_Drive",
            "/run/media/Second_Drive/sub",
            "/run/media/free/BTCEcoandBackup",
            "/run/media/free/sovran_systemsos",
        ):
            with self.assertRaises(backup_ops.DriveEjectError) as ctx:
                backup_ops.validate_eject_target_path(bad)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_already_unmounted_is_idempotent_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_root = os.path.join(tmp, "media")
            target = os.path.join(media_root, "free", "S_S Backup")
            os.makedirs(target)

            def fake_run(cmd, **_kwargs):
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

            res = backup_ops.eject_external_drive(
                target, media_root=media_root, run_cmd=fake_run, sync_fn=lambda: None,
            )
            self.assertTrue(res["ok"])
            self.assertEqual(res["status"], "already_unmounted")

    def test_eject_runs_sync_unmount_and_power_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_root = os.path.join(tmp, "media")
            target = os.path.join(media_root, "free", "S_S Backup")
            os.makedirs(target)

            calls: list[list[str]] = []
            synced = {"count": 0}

            def fake_sync():
                synced["count"] += 1

            def fake_run(cmd, **_kwargs):
                calls.append(list(cmd))
                if cmd[0] == "findmnt":
                    payload = {
                        "filesystems": [{
                            "source": "/dev/sdb1",
                            "target": target,
                            "fstype": "ext4",
                            "label": "S_S Backup",
                        }]
                    }
                    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
                if cmd[0] == "lsblk":
                    payload = {
                        "blockdevices": [{
                            "name": "sdb1",
                            "label": "S_S Backup",
                            "hotplug": "1",
                            "rm": "0",
                            "pkname": "sdb",
                        }]
                    }
                    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            res = backup_ops.eject_external_drive(
                target,
                media_root=media_root,
                run_cmd=fake_run,
                sync_fn=fake_sync,
                which_fn=lambda name: "/run/current-system/sw/bin/udisksctl" if name == "udisksctl" else None,
            )
            self.assertEqual(synced["count"], 1)
            self.assertEqual(res["status"], "ejected")
            self.assertTrue(res["powered_off"])
            self.assertIn(
                ["/run/current-system/sw/bin/udisksctl", "unmount", "--no-user-interaction", "-b", "/dev/sdb1"],
                calls,
            )
            self.assertIn(
                ["/run/current-system/sw/bin/udisksctl", "power-off", "--no-user-interaction", "-b", "/dev/sdb"],
                calls,
            )

    def test_busy_unmount_surfaces_409_with_holder_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_root = os.path.join(tmp, "media")
            target = os.path.join(media_root, "free", "S_S Backup")
            os.makedirs(target)

            proc_root = os.path.join(tmp, "proc")
            pid_dir = os.path.join(proc_root, "2222")
            os.makedirs(os.path.join(pid_dir, "fd"))
            os.symlink(target, os.path.join(pid_dir, "cwd"))
            with open(os.path.join(pid_dir, "comm"), "w", encoding="utf-8") as f:
                f.write("nautilus\n")

            def fake_run(cmd, **_kwargs):
                if cmd[0] == "findmnt":
                    return subprocess.CompletedProcess(
                        cmd, 0,
                        stdout=json.dumps({"filesystems": [{"source": "/dev/sdb1", "target": target, "fstype": "ext4"}]}),
                        stderr="",
                    )
                if cmd[0] == "lsblk":
                    return subprocess.CompletedProcess(
                        cmd, 0,
                        stdout=json.dumps({"blockdevices": [{"name": "sdb1", "hotplug": "1", "rm": "0", "pkname": "sdb"}]}),
                        stderr="",
                    )
                return subprocess.CompletedProcess(
                    cmd, 1, stdout="", stderr="Error unmounting /dev/sdb1: target is busy (udisks-error-quark, 14)",
                )

            with self.assertRaises(backup_ops.DriveEjectError) as ctx:
                backup_ops.eject_external_drive(
                    target,
                    media_root=media_root,
                    proc_root=proc_root,
                    run_cmd=fake_run,
                    sync_fn=lambda: None,
                    which_fn=lambda name: "/usr/bin/udisksctl",
                )
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("Files (nautilus)", ctx.exception.message)

    def test_refuses_non_removable_device_reported_by_lsblk(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_root = os.path.join(tmp, "media")
            target = os.path.join(media_root, "free", "FakeInternal")
            os.makedirs(target)

            def fake_run(cmd, **_kwargs):
                if cmd[0] == "findmnt":
                    return subprocess.CompletedProcess(
                        cmd, 0,
                        stdout=json.dumps({"filesystems": [{"source": "/dev/nvme0n1p2", "target": target, "fstype": "ext4"}]}),
                        stderr="",
                    )
                if cmd[0] == "lsblk":
                    return subprocess.CompletedProcess(
                        cmd, 0,
                        stdout=json.dumps({"blockdevices": [{"name": "nvme0n1p2", "hotplug": "0", "rm": "0", "pkname": "nvme0n1"}]}),
                        stderr="",
                    )
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with self.assertRaises(backup_ops.DriveEjectError) as ctx:
                backup_ops.eject_external_drive(
                    target, media_root=media_root, run_cmd=fake_run, sync_fn=lambda: None,
                )
            self.assertEqual(ctx.exception.status_code, 400)


class TestBackupScriptEndToEnd(unittest.TestCase):
    """Execute sovran-hub-backup.sh in an isolated sandbox to verify runtime behavior."""

    SCRIPT_PATH = os.path.join(
        _REPO_ROOT, "app", "sovran_systemsos_web", "scripts", "sovran-hub-backup.sh"
    )

    def _write_exe(self, directory: str, name: str, body: str) -> str:
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env bash\nset -euo pipefail\n" + textwrap.dedent(body).lstrip())
        os.chmod(path, 0o755)
        return path

    def _setup_sandbox(self, tmp: str, avail_bytes: int = 50 * 1024 ** 3, var_lib_vanished: bool = False):
        bin_dir = os.path.join(tmp, "bin")
        os.makedirs(bin_dir)

        media_root = os.path.join(tmp, "run", "media")
        target_mount = os.path.join(media_root, "free", "S_S Backup")
        os.makedirs(target_mount)

        src_root = os.path.join(tmp, "src_root")
        for sub in ("etc/nixos", "etc/nix-bitcoin-secrets", "home/free", "var/lib/nextcloud", "var/lib/mysql"):
            os.makedirs(os.path.join(src_root, sub), exist_ok=True)
        with open(os.path.join(src_root, "etc/nixos/configuration.nix"), "w", encoding="utf-8") as f:
            f.write("{ }\n")
        with open(os.path.join(src_root, "home/free/notes.txt"), "w", encoding="utf-8") as f:
            f.write("hello sovran\n")

        rsync_calls_log = os.path.join(tmp, "rsync_calls.log")
        sync_marker = os.path.join(tmp, "sync_status_at_call.txt")
        status_file = os.path.join(tmp, "backup.status")
        log_file = os.path.join(tmp, "backup.log")
        lock_file = os.path.join(tmp, "backup.lock")
        target_file = os.path.join(tmp, "backup.target")
        cfg_json = os.path.join(tmp, "config.json")
        with open(cfg_json, "w", encoding="utf-8") as f:
            json.dump({"role": "server_plus_desktop"}, f)

        self._write_exe(bin_dir, "mountpoint", f"""
            if [[ "${{1:-}}" == "-q" ]]; then shift; fi
            [[ "${{1:-}}" == "{target_mount}" ]]
        """)
        self._write_exe(bin_dir, "findmnt", """
            echo "ext4"
        """)
        self._write_exe(bin_dir, "lsblk", f"""
            cat <<'EOF'
            {{"blockdevices":[{{"name":"sdb1","type":"part","hotplug":"1","rm":"0","label":"S_S Backup","mountpoint":"{target_mount}"}}]}}
            EOF
        """)
        self._write_exe(bin_dir, "df", f"""
            echo "Avail"
            echo "{avail_bytes}"
        """)
        self._write_exe(bin_dir, "systemctl", """
            if [[ "${1:-}" == "is-active" ]]; then
              unit="${@: -1}"
              if [[ "$unit" == "postgresql.service" || "$unit" == "mysql.service" ]]; then
                exit 0
              fi
            fi
            exit 1
        """)
        self._write_exe(bin_dir, "psql", """
            echo "4096"
        """)
        self._write_exe(bin_dir, "pg_dumpall", """
            echo "-- PostgreSQL logical dump"
        """)
        self._write_exe(bin_dir, "mariadb-dump", """
            echo "-- MariaDB logical dump"
        """)
        vanished_rc = "24" if var_lib_vanished else "0"
        self._write_exe(bin_dir, "rsync", f"""
            printf '%s\\n' "$*" >> "{rsync_calls_log}"
            src="${{@: -2:1}}"
            dst="${{@: -1}}"
            mkdir -p "$dst"
            cp -a "${{src%/}}/." "$dst/" 2>/dev/null || true
            if [[ "$src" == *"/var/lib/" && "{vanished_rc}" == "24" ]]; then
              echo "file has vanished: /var/lib/nextcloud/tmp.part" >&2
              exit 24
            fi
            exit 0
        """)
        self._write_exe(bin_dir, "sync", f"""
            cat "{status_file}" > "{sync_marker}"
        """)

        env = os.environ.copy()
        env.update({
            "PATH": f"{bin_dir}:{env.get('PATH', '')}",
            "BACKUP_LOG": log_file,
            "BACKUP_STATUS": status_file,
            "BACKUP_LOCK": lock_file,
            "BACKUP_TARGET_FILE": target_file,
            "MEDIA_ROOT": media_root,
            "SOVRAN_HUB_CONFIG": cfg_json,
            "SOURCE_ROOT": src_root,
            "SAFETY_MARGIN_BYTES": str(1024 * 1024),
        })
        env.pop("BACKUP_TARGET", None)
        return {
            "env": env,
            "target_mount": target_mount,
            "target_file": target_file,
            "status_file": status_file,
            "log_file": log_file,
            "lock_file": lock_file,
            "rsync_calls_log": rsync_calls_log,
            "sync_marker": sync_marker,
            "bin_dir": bin_dir,
        }

    def test_full_backup_dumps_dbs_tolerates_var_lib_exit24_and_flushes_before_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._setup_sandbox(tmp, var_lib_vanished=True)
            with open(ctx["target_file"], "w", encoding="utf-8") as f:
                f.write(ctx["target_mount"] + "\n")

            res = subprocess.run(
                ["bash", self.SCRIPT_PATH],
                env=ctx["env"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(res.returncode, 0, msg=res.stdout + "\n" + res.stderr)

            backup_root = os.path.join(ctx["target_mount"], "Sovran_SystemsOS_Backup")
            backup_dir = os.path.join(backup_root, "current")

            # Indexer exclusion markers created
            self.assertTrue(os.path.isfile(os.path.join(backup_root, ".trackerignore")))
            self.assertTrue(os.path.isfile(os.path.join(backup_root, ".nomedia")))

            # Completion markers & status
            self.assertFalse(os.path.exists(os.path.join(backup_dir, "INCOMPLETE")))
            self.assertTrue(os.path.isfile(os.path.join(backup_dir, "BACKUP_COMPLETE")))
            with open(ctx["status_file"], "r", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "SUCCESS")

            # sync ran BEFORE status switched from RUNNING to SUCCESS
            with open(ctx["sync_marker"], "r", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "RUNNING")

            # SQL dumps created with strict permissions
            pg_dump = os.path.join(backup_dir, "databases", "postgresql-all.sql")
            my_dump = os.path.join(backup_dir, "databases", "mariadb-all.sql")
            self.assertTrue(os.path.isfile(pg_dump))
            self.assertTrue(os.path.isfile(my_dump))
            self.assertEqual(stat.S_IMODE(os.stat(pg_dump).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(my_dump).st_mode), 0o600)

            # rsync invoked with --delete-delay and new /var/lib exclusions
            with open(ctx["rsync_calls_log"], "r", encoding="utf-8") as f:
                rsync_calls = f.read()
            self.assertIn("--delete-delay", rsync_calls)
            self.assertIn("--exclude=flatpak/", rsync_calls)
            self.assertIn("--exclude=udisks2/", rsync_calls)
            self.assertIn("--exclude=systemd/coredump/", rsync_calls)

            # Manifest records vanished warning and avoids 'sudo'
            with open(os.path.join(backup_dir, "BACKUP_MANIFEST.txt"), "r", encoding="utf-8") as f:
                manifest = f.read()
            self.assertNotIn("sudo ", manifest)
            self.assertIn("/var/lib: some transient files vanished", manifest)

    def test_incremental_repeat_backup_subtracts_existing_mirror_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Simulate only 15 GiB free on the USB drive while source + existing
            # mirror are each 100 GiB (net new = 0 bytes).
            ctx = self._setup_sandbox(tmp, avail_bytes=15 * 1024 ** 3)
            with open(ctx["target_file"], "w", encoding="utf-8") as f:
                f.write(ctx["target_mount"] + "\n")

            backup_dir = os.path.join(ctx["target_mount"], "Sovran_SystemsOS_Backup", "current")
            os.makedirs(backup_dir, exist_ok=True)

            # Shim du so both source /home and existing $BACKUP_DIR report 100 GiB
            hundred_gib = 100 * 1024 ** 3
            self._write_exe(ctx["bin_dir"], "du", f"""
                target="${{@: -1}}"
                if [[ "$target" == *"/home" || "$target" == *"/Sovran_SystemsOS_Backup/current" ]]; then
                  echo "{hundred_gib}\t$target"
                else
                  echo "4096\t$target"
                fi
            """)

            res = subprocess.run(
                ["bash", self.SCRIPT_PATH],
                env=ctx["env"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(res.returncode, 0, msg=res.stdout + "\n" + res.stderr)
            with open(ctx["status_file"], "r", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "SUCCESS")

    def test_duplicate_launch_does_not_clobber_running_status_or_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._setup_sandbox(tmp)
            with open(ctx["status_file"], "w", encoding="utf-8") as f:
                f.write("RUNNING\n")
            with open(ctx["log_file"], "w", encoding="utf-8") as f:
                f.write("ACTIVE_RUN_LOG_LINE\n")

            holder = subprocess.Popen(
                [
                    "bash",
                    "-c",
                    f'exec {{fd}}>>"{ctx["lock_file"]}"; flock -n "$fd"; echo HELD; sleep 30',
                ],
                stdout=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertEqual(holder.stdout.readline().strip(), "HELD")
                dup = subprocess.run(
                    ["bash", self.SCRIPT_PATH],
                    env=ctx["env"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(dup.returncode, 0)
                with open(ctx["status_file"], "r", encoding="utf-8") as f:
                    self.assertEqual(f.read().strip(), "RUNNING")
                with open(ctx["log_file"], "r", encoding="utf-8") as f:
                    self.assertEqual(f.read(), "ACTIVE_RUN_LOG_LINE\n")
            finally:
                if holder.stdout is not None:
                    holder.stdout.close()
                holder.terminate()
                holder.wait(timeout=5)


class TestHubWiringAndFrontendInvariants(unittest.TestCase):
    """Verify NixOS unit, FastAPI endpoints, and frontend JS invariants."""

    def test_backup_script_bash_syntax(self):
        script = os.path.join(
            _REPO_ROOT, "app", "sovran_systemsos_web", "scripts", "sovran-hub-backup.sh"
        )
        res = subprocess.run(["bash", "-n", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(res.returncode, 0, msg=res.stderr)

    def test_sovran_hub_nix_defines_detached_backup_service_and_udisks(self):
        hub_nix = _read("modules", "core", "sovran-hub.nix")
        self.assertIn("systemd.services.sovran-hub-backup", hub_nix)
        self.assertIn("config.services.udisks2.package", hub_nix)
        self.assertIn("config.services.postgresql.enable", hub_nix)
        start = hub_nix.index("systemd.services.sovran-hub-backup")
        end = hub_nix.index("systemd.services.sovran-hub-update", start)
        block = hub_nix[start:end]
        self.assertIn("restartIfChanged = false;", block)
        self.assertIn("stopIfChanged    = false;", block)
        self.assertIn("sovran-hub-reboot.service", block)

    def test_server_wires_eject_endpoint_recovery_and_reboot_guard(self):
        server = _read("app", "sovran_systemsos_web", "server.py")
        self.assertIn('@app.post("/api/backup/eject")', server)
        self.assertIn("async def api_backup_eject", server)
        self.assertIn("_recover_stale_backup_status", server)

        reboot_start = server.index("async def api_reboot")
        reboot_end = server.index("@app.", reboot_start)
        reboot_block = server[reboot_start:reboot_end]
        self.assertIn("_is_backup_genuinely_running", reboot_block)
        self.assertIn("UPDATE_UNIT", reboot_block)
        self.assertIn("REBUILD_UNIT", reboot_block)

    def test_support_js_guards_shared_modal_and_wires_safe_eject(self):
        support_js = _read("app", "sovran_systemsos_web", "static", "js", "support.js")
        self.assertIn("function isBackupModalActive()", support_js)
        self.assertIn("async function ejectBackupDrive()", support_js)
        self.assertIn('"/api/backup/eject"', support_js)
        self.assertIn("btn-eject-backup-drive", support_js)
        self.assertIn("function updateDriveSelectionState()", support_js)

        poll_start = support_js.index("async function pollBackupStatus()")
        poll_end = support_js.index("async function ejectBackupDrive()", poll_start)
        poll_block = support_js[poll_start:poll_end]
        self.assertIn("if (isBackupModalActive())", poll_block)

    def test_events_js_blocks_restart_dialog_during_backup(self):
        events_js = _read("app", "sovran_systemsos_web", "static", "js", "events.js")
        start = events_js.index("function openRestartConfirmDialog()")
        end = events_js.index("function closeRestartConfirmDialog()", start)
        block = events_js[start:end]
        self.assertIn("_backupPollTimer", block)
        self.assertIn("/api/backup/status", block)


if __name__ == "__main__":
    unittest.main()
