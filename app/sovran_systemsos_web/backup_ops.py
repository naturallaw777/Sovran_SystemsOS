"""Manual Backup state, drive detection, stale-lock recovery, and safe eject helpers."""

from __future__ import annotations

import fcntl
import json
import pwd
import os
import shutil
import subprocess
from typing import Callable


INTERNAL_LABELS = {"BTCEcoandBackup", "sovran_systemsos"}
INTERNAL_MOUNTS = {"/", "/boot/efi"}
INTERNAL_MOUNT_PREFIX = "/run/media/Second_Drive"
MEDIA_ROOT = "/run/media"

_FRIENDLY_PROC_NAMES: dict[str, str] = {
    "nautilus": "Files (nautilus)",
    "fish": "Terminal (fish)",
    "bash": "Terminal (bash)",
    "zsh": "Terminal (zsh)",
    "sh": "shell",
    "gnome-terminal-": "Terminal",
    "kgx": "Console",
    "ranger": "ranger",
    "gedit": "Text Editor (gedit)",
    "gnome-text-edit": "Text Editor",
    "soffice.bin": "LibreOffice",
    "loupe": "Image Viewer (Loupe)",
    "totem": "Videos (Totem)",
    "localsearch-3": "GNOME File Indexer",
    "tracker-miner-f": "GNOME File Indexer",
    "gvfsd-trash": "GNOME Trash Monitor",
    "rsync": "rsync",
}


class DriveEjectError(Exception):
    """Raised when an external backup drive cannot be ejected."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def is_internal_mount(mnt: str) -> bool:
    """Return True if *mnt* is a known internal system path."""
    if not mnt:
        return True
    norm = os.path.normpath(mnt)
    if norm in INTERNAL_MOUNTS or norm == MEDIA_ROOT:
        return True
    if norm == INTERNAL_MOUNT_PREFIX or norm.startswith(INTERNAL_MOUNT_PREFIX + "/"):
        return True
    return False


def is_supported_backup_fstype(path: str, fstype: str) -> bool:
    """Return whether the target filesystem type is supported for manual backup.

    Manual Backup requires ext4 for Linux metadata preservation (ACLs, xattrs,
    hard links). exFAT, FAT32, NTFS, and other filesystems are not supported.
    """
    return (fstype or "").lower() == "ext4"


def is_backup_lock_held(lock_path: str) -> bool:
    """Return True if an exclusive flock is currently held on *lock_path*."""
    if not lock_path or not os.path.exists(lock_path):
        return False
    fd = -1
    try:
        fd = os.open(lock_path, os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except BlockingIOError:
        return True
    except OSError:
        return False
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass


def recover_stale_backup_status(
    status_file: str,
    log_file: str,
    lock_path: str,
    is_unit_active_fn: Callable[[], bool] | None = None,
    launch_grace_active: bool = False,
) -> bool:
    """Reset a stale ``RUNNING`` backup status left behind by a crash or reboot.

    ``sovran-hub-backup.sh`` holds an exclusive ``flock`` on *lock_path* for its
    entire runtime and sets ``SUCCESS`` or ``FAILED`` before releasing it.  If
    the status file still reads ``RUNNING`` while neither the ``flock`` is held
    nor the detached systemd unit is active (outside the brief launch grace
    window), the backup was interrupted (e.g. power loss, reboot, or SIGKILL).

    Returns True if a stale ``RUNNING`` state was corrected to ``FAILED``.
    """
    try:
        with open(status_file, "r", encoding="utf-8") as f:
            status = f.read().strip()
    except FileNotFoundError:
        return False
    except OSError:
        return False

    if status != "RUNNING":
        return False

    if launch_grace_active:
        return False

    if is_backup_lock_held(lock_path):
        return False

    if is_unit_active_fn is not None:
        try:
            if is_unit_active_fn():
                return False
        except Exception:
            pass

    try:
        with open(status_file, "w", encoding="utf-8") as f:
            f.write("FAILED")
    except OSError:
        return False

    msg = (
        "\n[Backup was interrupted before completion (system restart or "
        "unexpected termination). Verify your USB drive is connected and run "
        "Manual Backup again.]\n"
    )
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(msg)
    except OSError:
        pass
    return True


def detect_external_drives(media_root: str = MEDIA_ROOT) -> list[dict]:
    """Scan for mounted external USB drives under *media_root*.

    GNOME/udisks automounts removable drives under
    ``/run/media/<user>/<label>``; anything mounted there that is not a
    known internal system drive (BTCEcoandBackup, sovran_systemsos,
    /run/media/Second_Drive) is a backup target.  No lsblk inspection is
    needed -- udisks has already decided the drive is removable by
    mounting it there.
    """
    drives: list[dict] = []

    if not os.path.isdir(media_root):
        return drives
    try:
        for user in os.listdir(media_root):
            user_path = os.path.join(media_root, user)
            if not os.path.isdir(user_path):
                continue
            for drive_name in os.listdir(user_path):
                drive_path = os.path.join(user_path, drive_name)
                if not os.path.isdir(drive_path):
                    continue
                if drive_name in INTERNAL_LABELS:
                    continue
                if is_internal_mount(drive_path):
                    continue
                try:
                    st = os.statvfs(drive_path)
                    total_gb = round((st.f_blocks * st.f_frsize) / (1024 ** 3), 1)
                    free_gb = round((st.f_bavail * st.f_frsize) / (1024 ** 3), 1)
                    fstype = ""
                    try:
                        fstype = subprocess.run(
                            ["findmnt", "-n", "-o", "FSTYPE", "-M", drive_path],
                            capture_output=True, text=True, timeout=5,
                        ).stdout.strip().lower()
                    except Exception:
                        fstype = ""
                    drives.append({
                        "name": drive_name,
                        "path": drive_path,
                        "free_gb": free_gb,
                        "total_gb": total_gb,
                        "fstype": fstype,
                    })
                except OSError:
                    pass
    except OSError:
        pass
    return drives


def find_mount_holders(mountpoint: str, proc_root: str = "/proc") -> list[str]:
    """Return friendly names of processes with open files or cwd under *mountpoint*.

    Inspects ``/proc/<pid>/cwd`` and ``/proc/<pid>/fd/*`` directly so no external
    ``lsof`` or ``fuser`` binary is required.
    """
    if not mountpoint or not os.path.isdir(proc_root):
        return []

    norm_mnt = os.path.normpath(mountpoint)
    prefix = norm_mnt.rstrip("/") + "/"
    self_pid = str(os.getpid())
    holders: set[str] = set()

    def _matches(target_path: str) -> bool:
        if target_path.endswith(" (deleted)"):
            target_path = target_path[:-10]
        return target_path == norm_mnt or target_path.startswith(prefix)

    try:
        entries = os.listdir(proc_root)
    except OSError:
        return []

    for entry in entries:
        if not entry.isdigit() or entry == self_pid:
            continue
        pid_dir = os.path.join(proc_root, entry)
        matched = False

        try:
            cwd = os.readlink(os.path.join(pid_dir, "cwd"))
            if _matches(cwd):
                matched = True
        except OSError:
            pass

        if not matched:
            fd_dir = os.path.join(pid_dir, "fd")
            try:
                for fd_name in os.listdir(fd_dir):
                    try:
                        link = os.readlink(os.path.join(fd_dir, fd_name))
                        if _matches(link):
                            matched = True
                            break
                    except OSError:
                        continue
            except OSError:
                pass

        if matched:
            comm = ""
            try:
                with open(os.path.join(pid_dir, "comm"), "r", encoding="utf-8", errors="replace") as f:
                    comm = f.read().strip()
            except OSError:
                comm = f"PID {entry}"
            holders.add(_FRIENDLY_PROC_NAMES.get(comm, comm or f"PID {entry}"))

    return sorted(holders)


def validate_eject_target_path(target: str, media_root: str = MEDIA_ROOT) -> str:
    """Validate and normalize *target* as a safe external mount path under *media_root*."""
    if not target or not isinstance(target, str) or "\x00" in target:
        raise DriveEjectError("Invalid drive path.", status_code=400)

    norm_media = os.path.normpath(media_root)
    norm_target = os.path.normpath(target)

    if not norm_target.startswith(norm_media.rstrip("/") + "/"):
        raise DriveEjectError(
            f"Drive path must be under {norm_media}.", status_code=400,
        )

    if is_internal_mount(norm_target):
        raise DriveEjectError(
            "Refusing to eject an internal system drive.", status_code=400,
        )

    if os.path.basename(norm_target) in INTERNAL_LABELS:
        raise DriveEjectError(
            "Refusing to eject an internal system drive.", status_code=400,
        )

    if os.path.islink(norm_target):
        raise DriveEjectError(
            "Refusing to eject a symbolic link path.", status_code=400,
        )

    return norm_target


def _desktop_username(target: str, media_root: str) -> str | None:
    """Return the desktop username who owns the mount at *target*, or None.

    The mount lives under ``/run/media/<username>/...`` and that user has
    a running graphical session if ``/run/user/<uid>/bus`` exists.  That
    is all the Hub needs to know: ``systemd-run --machine=<user>@
    --user`` enters that user's session (the user manager provides
    XDG_RUNTIME_DIR and the session bus address itself), so no session
    environment is assembled by hand here.
    """
    rel = os.path.relpath(os.path.normpath(target), os.path.normpath(media_root))
    username = rel.split(os.sep)[0]
    if not username or username.startswith("."):
        return None
    try:
        entry = pwd.getpwnam(username)
    except KeyError:
        return None
    if not os.path.exists(f"/run/user/{entry.pw_uid}/bus"):
        return None
    return username


def eject_external_drive(
    target: str,
    media_root: str = MEDIA_ROOT,
    proc_root: str = "/proc",
    run_cmd: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    sync_fn: Callable[[], None] = os.sync,
    which_fn: Callable[[str], str | None] = shutil.which,
    session_fn: Callable[[str, str], str | None] = _desktop_username,
) -> dict:
    """Flush buffers, unmount, and power off an external USB backup drive.

    Eject goes through the desktop user's GVfs session -- the same path
    Nautilus (GNOME Files) uses.  Per the gvfs udisks2 volume monitor,
    ``GMount`` eject first emits ``mount-pre-unmount`` so the trash
    monitor, indexer, and other per-user daemons release the volume
    cooperatively, then unmounts every filesystem on the drive, then
    asks udisks to power the drive off.  A root-side ``udisksctl unmount``
    skips that choreography and fails with "Volume is busy" whenever
    Files has been browsing the drive, so it is only a fallback for
    headless systems with no desktop session.

    Raises :class:`DriveEjectError` with an HTTP-ready status code if
    validation fails or a real application still holds the mount.
    """
    norm_target = validate_eject_target_path(target, media_root=media_root)

    # Check whether norm_target is currently mounted (-M matches exact mountpoint).
    findmnt_res = run_cmd(
        ["findmnt", "-J", "-o", "SOURCE,TARGET,FSTYPE,LABEL", "-M", norm_target],
        capture_output=True, text=True, timeout=10,
    )
    if findmnt_res.returncode != 0 or not (findmnt_res.stdout or "").strip():
        return {
            "ok": True,
            "status": "already_unmounted",
            "powered_off": False,
            "message": "Drive is already unmounted and safe to unplug.",
        }

    try:
        mnt_info = json.loads(findmnt_res.stdout).get("filesystems", [])[0]
    except Exception as exc:
        raise DriveEjectError(
            f"Could not inspect mount state for '{norm_target}': {exc}",
            status_code=500,
        )

    part_dev = (mnt_info.get("source") or "").strip()
    if (mnt_info.get("label") or "").strip() in INTERNAL_LABELS:
        raise DriveEjectError(
            "Refusing to eject an internal system drive.",
            status_code=400,
        )

    # Flush all pending kernel filesystem writes before unmounting.
    try:
        sync_fn()
    except Exception:
        pass

    def _busy_error() -> DriveEjectError:
        holders = find_mount_holders(norm_target, proc_root=proc_root)
        drive_display = os.path.basename(norm_target)
        if holders:
            joined = ", ".join(holders)
            return DriveEjectError(
                f"'{drive_display}' is still open in {joined}. "
                "Close any Files windows, text editors, or terminals viewing "
                "this drive, then click Safely Eject Drive again.",
                status_code=409,
            )
        return DriveEjectError(
            f"'{drive_display}' is still busy finishing disk operations. "
            "Wait a few seconds, make sure no Files window is browsing the "
            "drive, and click Safely Eject Drive again.",
            status_code=409,
        )

    # Preferred path: eject inside the desktop user's session so GVfs
    # performs its mount-pre-unmount release before udisks powers off.
    # systemd-run --machine=<user>@ --user is the systemd-supported way
    # for a root service to run a command in a user's session; the user
    # manager sets up the runtime environment.
    username = None
    try:
        username = session_fn(norm_target, media_root)
    except Exception:
        username = None
    gio = which_fn("gio")
    systemd_run = which_fn("systemd-run")
    if username and gio and systemd_run:
        eject_res = run_cmd(
            [systemd_run, f"--machine={username}@", "--user", "--wait", "--pipe",
             gio, "mount", "--eject", norm_target],
            capture_output=True, text=True, timeout=60,
        )
        if eject_res.returncode == 0:
            # Confirm the drive really left before claiming power-off:
            # gio success means GVfs/udisks accepted the eject; verify the
            # mount is actually gone.
            verify_res = run_cmd(
                ["findmnt", "-n", "-M", norm_target],
                capture_output=True, text=True, timeout=10,
            )
            if verify_res.returncode != 0:
                return {
                    "ok": True,
                    "status": "ejected",
                    "powered_off": True,
                    "message": "Drive safely unmounted and powered down. You can unplug it now.",
                }
            raise _busy_error()
        # If the user session turned out to be unavailable (stale bus,
        # user logged out between checks), fall through to the headless
        # path instead of crying busy.  A genuine busy failure goes to
        # the user with the holding applications named.
        session_err = ((eject_res.stderr or "") + " " + (eject_res.stdout or "")).lower()
        session_unavailable = any(
            marker in session_err
            for marker in (
                "user manager",
                "not running",
                "failed to connect",
                "no such file or directory",
                "transport endpoint",
            )
        )
        if not session_unavailable:
            raise _busy_error()

    # Headless fallback: no desktop session -- unmount and power off
    # directly through udisks, resolving the parent disk for power-off.
    udisksctl = which_fn("udisksctl")
    if not part_dev.startswith("/dev/") or not udisksctl:
        raise _busy_error()
    unmount_res = run_cmd(
        [udisksctl, "unmount", "--no-user-interaction", "-b", part_dev],
        capture_output=True, text=True, timeout=60,
    )
    if unmount_res.returncode != 0:
        # udisksd may not be running; fall back to a plain umount.
        err_text = ((unmount_res.stderr or "") + " " + (unmount_res.stdout or "")).lower()
        if "busy" not in err_text:
            unmount_res = run_cmd(
                ["umount", norm_target],
                capture_output=True, text=True, timeout=60,
            )
    if unmount_res.returncode != 0:
        raise _busy_error()

    powered_off = False
    try:
        pkname = run_cmd(
            ["lsblk", "-no", "PKNAME", part_dev],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
        disk_dev = f"/dev/{pkname[0].strip()}" if pkname and pkname[0].strip() else part_dev
        powered_off = run_cmd(
            [udisksctl, "power-off", "--no-user-interaction", "-b", disk_dev],
            capture_output=True, text=True, timeout=30,
        ).returncode == 0
    except Exception:
        powered_off = False

    return {
        "ok": True,
        "status": "ejected",
        "powered_off": powered_off,
        "message": (
            "Drive safely unmounted and powered down. You can unplug it now."
            if powered_off
            else "Drive safely unmounted. You can unplug it now."
        ),
    }
