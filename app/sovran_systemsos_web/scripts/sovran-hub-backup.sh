#!/usr/bin/env bash
# ── Sovran Hub External Backup Script ────────────────────────────
# Backs up Sovran_SystemsOS data to an external USB hard drive using rsync.
# Designed for the Hub web UI (no GUI dependencies).
#
# On Server + Desktop and Node systems, your Sovran Pro already backs up
# your data automatically to its internal second drive (BTCEcoandBackup at
# /run/media/Second_Drive); this script stores a copy in a third location.
# Desktop Only systems have no internal second drive, so the external copy
# is the second location.
#
# What gets mirrored depends on the system role:
#   - Node / Server + Desktop: /etc/nixos, /etc/nix-bitcoin-secrets,
#     PostgreSQL and MariaDB SQL dumps (when active), /home, and /var/lib
#     (minus raw database files, blockchain data, Flatpak runtimes, logs, caches).
#   - Desktop Only: /etc/nixos and /home. Desktop Only runs no server or
#     Bitcoin services, so there are no nix-bitcoin secrets, databases, or
#     system service data to back up.
#
# The external drive must be formatted as ext4. Files are stored as
# directly browsable files under Sovran_SystemsOS_Backup/current/.
# Later runs update the same mirror and only transfer changed or new
# files, making repeat backups fast.
#
# Bitcoin blockchain and Electrs index data are NOT included (they live on
# the internal second drive and are reconstructable).
#
# Usage:
#   BACKUP_TARGET=/run/media/<user>/<drive> bash sovran-hub-backup.sh
#   (or pass path in /run/sovran-hub-backup.target, or omit to auto-detect)

set -euo pipefail

BACKUP_LOG="${BACKUP_LOG:-/var/log/sovran-hub-backup.log}"
BACKUP_STATUS="${BACKUP_STATUS:-/var/log/sovran-hub-backup.status}"
BACKUP_LOCK="${BACKUP_LOCK:-/var/lock/sovran-hub-backup.lock}"
BACKUP_TARGET_FILE="${BACKUP_TARGET_FILE:-/run/sovran-hub-backup.target}"
MEDIA_ROOT="${MEDIA_ROOT:-/run/media}"
HUB_CONFIG_JSON="${SOVRAN_HUB_CONFIG:-/var/lib/sovran-hub/config.json}"
ROLE_STATE_NIX="${ROLE_STATE_NIX:-/etc/nixos/role-state.nix}"
SECOND_DRIVE_MOUNT="${SECOND_DRIVE_MOUNT:-/run/media/Second_Drive}"
SOURCE_ROOT="${SOURCE_ROOT:-/}"
SRC_PREFIX="${SOURCE_ROOT%/}"
SAFETY_MARGIN_BYTES="${SAFETY_MARGIN_BYTES:-$((2 * 1024 * 1024 * 1024))}"

# ── Internal drive labels/paths to NEVER use as backup targets ───
INTERNAL_LABELS=("BTCEcoandBackup" "sovran_systemsos")
INTERNAL_MOUNTS=("$SECOND_DRIVE_MOUNT" "/boot/efi" "/")

FAILED_ALREADY=0
BACKUP_COMPLETE=0
LOCK_ACQUIRED=0
RSYNC_WARNINGS=()

# Stable rsync mirror sub-path under the target drive. Not timestamped
# so later runs update the same destination and only transfer new or changed files.
BACKUP_SUBPATH="Sovran_SystemsOS_Backup/current"

# ── Logging helpers ──────────────────────────────────────────────

log() {
  local msg
  msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "$msg" | tee -a "$BACKUP_LOG"
}

set_status() {
  echo "$1" > "$BACKUP_STATUS"
}

fail() {
  FAILED_ALREADY=1
  log "ERROR: $*"
  set_status "FAILED"
  exit 1
}

cleanup() {
  local rc=$?

  # If we exited before acquiring the exclusive run lock (e.g. another
  # backup is already running), never clobber the active run's log, status,
  # or completion markers.
  if [[ "$LOCK_ACQUIRED" -ne 1 ]]; then
    if [[ -n "${LOCK_FD:-}" ]]; then
      exec {LOCK_FD}>&- 2>/dev/null || true
    fi
    return
  fi

  # Release the concurrency lock file descriptor if it was opened
  if [[ -n "${LOCK_FD:-}" ]]; then
    exec {LOCK_FD}>&- 2>/dev/null || true
  fi

  if [[ "$BACKUP_COMPLETE" -eq 1 && "$rc" -eq 0 ]]; then
    return
  fi

  if [[ "$FAILED_ALREADY" -eq 0 ]]; then
    log "ERROR: Backup terminated unexpectedly (exit code $rc)."
    set_status "FAILED"
  fi

  # Mark the backup directory as incomplete so failed runs are identifiable
  if [[ -n "${BACKUP_DIR:-}" && -d "${BACKUP_DIR:-}" && ! -f "${BACKUP_DIR:-}/BACKUP_COMPLETE" ]]; then
    touch "${BACKUP_DIR}/INCOMPLETE" 2>/dev/null || true
  fi
}

trap cleanup EXIT
trap 'exit 1' INT TERM

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: $cmd"
}

# ── Check whether a mount point is an internal drive ────────────

is_internal() {
  local mnt="$1"
  for internal in "${INTERNAL_MOUNTS[@]}"; do
    if [[ "$mnt" == "$internal" || "$mnt" == "${internal}/"* ]]; then
      return 0
    fi
  done
  return 1
}

# ── Use lsblk to find the first genuine external USB drive ───────

find_external_drive() {
  local target=""

  while IFS=$'\t' read -r dev_type hotplug removable label mountpoint; do
    [[ "$dev_type" == "part" || "$dev_type" == "disk" ]] || continue
    [[ "$hotplug" == "1" || "$removable" == "1" ]] || continue
    [[ -n "$mountpoint" ]] || continue

    local skip=0
    for lbl in "${INTERNAL_LABELS[@]}"; do
      [[ "$label" == "$lbl" ]] && skip=1 && break
    done
    [[ "$skip" -eq 1 ]] && continue

    is_internal "$mountpoint" && continue

    if mountpoint -q "$mountpoint" 2>/dev/null; then
      target="$mountpoint"
      break
    fi
  done < <(lsblk -J -o NAME,LABEL,MOUNTPOINT,HOTPLUG,RM,TYPE 2>/dev/null | \
    python3 -c "
import sys, json

def flatten(devs):
    for d in devs:
        yield d
        for c in d.get('children', []):
            yield from flatten([c])

data = json.load(sys.stdin)
for d in flatten(data.get('blockdevices', [])):
    print('\\t'.join([
        d.get('type') or '',
        str(d.get('hotplug') or '0'),
        str(d.get('rm') or '0'),
        d.get('label') or '',
        d.get('mountpoint') or '',
    ]))
" 2>/dev/null || true)

  if [[ -z "$target" && -d "$MEDIA_ROOT" ]]; then
    while IFS= read -r -d '' mnt; do
      is_internal "$mnt" && continue
      if mountpoint -q "$mnt" 2>/dev/null; then
        target="$mnt"
        break
      fi
    done < <(find "$MEDIA_ROOT" -mindepth 2 -maxdepth 2 -type d -print0 2>/dev/null)
  fi

  echo "$target"
}

# ── Detect the configured system role ───────────────────────────

detect_role() {
  local role="server_plus_desktop"

  if [[ -f "$HUB_CONFIG_JSON" ]] && command -v python3 &>/dev/null; then
    local r
    r=$(python3 -c \
      "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('role',''))" \
      "$HUB_CONFIG_JSON" 2>/dev/null || true)
    if [[ -n "$r" ]]; then
      echo "$r"
      return
    fi
  fi

  if [[ -f "$ROLE_STATE_NIX" ]]; then
    if grep -q 'roles\.desktop = lib\.mkDefault true' "$ROLE_STATE_NIX" 2>/dev/null; then
      role="desktop"
    elif grep -q 'roles\.node = lib\.mkDefault true' "$ROLE_STATE_NIX" 2>/dev/null; then
      role="node"
    fi
  fi

  echo "$role"
}

validate_target_mount() {
  local target="$1"
  [[ "$target" == "${MEDIA_ROOT}/"* ]] || fail "Target '$target' must be mounted under $MEDIA_ROOT."
  [[ -d "$target" ]] || fail "Target path '$target' does not exist."
  mountpoint -q "$target" || fail "Target path '$target' is not a mount point."

  local fstype=""
  fstype=$(findmnt -n -o FSTYPE -M "$target" 2>/dev/null || findmnt -n -o FSTYPE -T "$target" 2>/dev/null || true)
  [[ -n "$fstype" ]] || fail "Could not determine filesystem type for '$target'."

  if [[ "$fstype" != "ext4" ]]; then
    fail "Target '$target' must be formatted as ext4 (detected filesystem: $fstype). Manual Backup requires an ext4-formatted external drive for Linux metadata preservation. exFAT, FAT32, and NTFS are not supported."
  fi

  local write_test
  write_test="$target/.sovran-write-test-$$"
  if ! ( : > "$write_test" && echo "ok" >> "$write_test" && rm -f "$write_test" ); then
    fail "Target '$target' is not writable."
  fi

  log "Verified backup target filesystem: $fstype"
}

estimate_path_bytes() {
  local path="$1"
  shift || true
  [[ -e "$path" ]] || {
    echo 0
    return
  }

  local size
  size=$(du -s -B1 -x "$@" "$path" 2>/dev/null | awk '{print $1}' || true)
  [[ -n "$size" ]] || size=0
  echo "$size"
}

estimate_db_bytes() {
  local total=0

  if command -v psql >/dev/null 2>&1 && \
     command -v systemctl >/dev/null 2>&1 && \
     systemctl is-active --quiet postgresql.service 2>/dev/null; then
    local pg_bytes
    pg_bytes=$(psql -AtU postgres -c "SELECT COALESCE(SUM(pg_database_size(oid)), 0) FROM pg_database;" 2>/dev/null | tr -d '[:space:]' || true)
    if [[ "$pg_bytes" =~ ^[0-9]+$ ]]; then
      total=$(( total + pg_bytes ))
    fi
  fi

  if [[ -d "${SRC_PREFIX}/var/lib/mysql" ]] && \
     command -v systemctl >/dev/null 2>&1 && \
     systemctl is-active --quiet mysql.service 2>/dev/null; then
    local my_bytes
    my_bytes=$(estimate_path_bytes "${SRC_PREFIX}/var/lib/mysql")
    total=$(( total + my_bytes ))
  fi

  echo "$total"
}

dump_databases() {
  local db_dir="$BACKUP_DIR/databases"

  mountpoint -q "$TARGET" 2>/dev/null || \
    fail "Databases stage: external drive '$TARGET' is no longer mounted. Refusing to write."

  mkdir -p -- "$db_dir" || fail "Failed to create database dump directory '$db_dir'."
  chmod 700 "$db_dir"

  # ── PostgreSQL (Nextcloud, Matrix Synapse, BTCPay Server) ─────────
  if command -v pg_dumpall >/dev/null 2>&1 && \
     command -v systemctl >/dev/null 2>&1 && \
     systemctl is-active --quiet postgresql.service 2>/dev/null; then
    log "Dumping PostgreSQL databases…"
    local pg_tmp="$db_dir/postgresql-all.sql.tmp"
    local pg_out="$db_dir/postgresql-all.sql"
    rm -f "$pg_tmp"
    if ( umask 077 && pg_dumpall --clean --if-exists -U postgres > "$pg_tmp" ) && \
       mv -f "$pg_tmp" "$pg_out"; then
      chmod 600 "$pg_out"
      log "PostgreSQL dump saved to databases/postgresql-all.sql"
    else
      rm -f "$pg_tmp"
      fail "PostgreSQL database dump failed."
    fi
  else
    log "(PostgreSQL service not active or pg_dumpall unavailable — skipping)"
  fi

  # ── MariaDB / MySQL (WordPress) ──────────────────────────────────
  local mysql_dump_bin=""
  if command -v mariadb-dump >/dev/null 2>&1; then
    mysql_dump_bin="mariadb-dump"
  elif command -v mysqldump >/dev/null 2>&1; then
    mysql_dump_bin="mysqldump"
  fi

  if [[ -n "$mysql_dump_bin" ]] && \
     command -v systemctl >/dev/null 2>&1 && \
     systemctl is-active --quiet mysql.service 2>/dev/null; then
    log "Dumping MariaDB databases…"
    local my_tmp="$db_dir/mariadb-all.sql.tmp"
    local my_out="$db_dir/mariadb-all.sql"
    rm -f "$my_tmp"
    if ( umask 077 && "$mysql_dump_bin" -u root --all-databases --single-transaction --quick > "$my_tmp" ) && \
       mv -f "$my_tmp" "$my_out"; then
      chmod 600 "$my_out"
      log "MariaDB dump saved to databases/mariadb-all.sql"
    else
      rm -f "$my_tmp"
      fail "MariaDB database dump failed."
    fi
  else
    log "(MariaDB service not active or mariadb-dump unavailable — skipping)"
  fi
}

# ── Sync one source tree to its backup destination ───────────────
# Usage: sync_tree <label> <allow_vanished> <source> <destination> [rsync options...]
#
# allow_vanished: "yes" means rsync exit 24 (vanished files) is nonfatal.
# Used for /home and /var/lib — transient files may disappear while the
# desktop and hosted services are active. All other nonzero exit codes remain fatal.
#
# Before every rsync call this helper:
#   1. Re-verifies $TARGET is still a mount point (fails if drive disconnected).
#   2. Verifies the destination path remains beneath $BACKUP_DIR and $BACKUP_DIR
#      remains beneath $TARGET (safe-path check).
#   3. Creates the full destination directory hierarchy with mkdir -p so that
#      rsync never fails trying to create a directory whose parent is absent.
sync_tree() {
  local label="$1"
  local allow_vanished="$2"
  local source="$3"
  local destination="$4"
  shift 4
  # Remaining "$@" are rsync options (--exclude, etc.)

  # ── Re-verify the external drive is still mounted ────────────────
  mountpoint -q "$TARGET" 2>/dev/null || \
    fail "Stage $label: external drive '$TARGET' is no longer mounted. Refusing to write."

  # ── Verify path safety ────────────────────────────────────────────
  # BACKUP_DIR must remain beneath TARGET.
  case "$BACKUP_DIR" in
    "$TARGET"/*) ;;
    *) fail "Stage $label: BACKUP_DIR '$BACKUP_DIR' is outside TARGET '$TARGET'." ;;
  esac
  # Destination must remain beneath BACKUP_DIR.
  case "$destination" in
    "$BACKUP_DIR"/*|"$BACKUP_DIR") ;;
    *) fail "Stage $label: destination '$destination' is outside BACKUP_DIR '$BACKUP_DIR'. Refusing to write." ;;
  esac

  # ── Create complete destination directory hierarchy ───────────────
  mkdir -p -- "$destination" || \
    fail "Stage $label: failed to create destination directory '$destination' (source: '$source')."

  local rsync_err_tmp
  rsync_err_tmp="$(mktemp /tmp/sovran-rsync-err.XXXXXX)"

  local rc=0
  rsync \
    --archive \
    --acls \
    --xattrs \
    --hard-links \
    --numeric-ids \
    --one-file-system \
    --delete-delay \
    --partial \
    "$@" "$source" "$destination" 2>"$rsync_err_tmp" || rc=$?

  if [[ -s "$rsync_err_tmp" ]]; then
    while IFS= read -r rline; do
      log "rsync: $rline"
    done < "$rsync_err_tmp"
  fi
  rm -f "$rsync_err_tmp"

  if [[ "$rc" -eq 0 ]]; then
    return 0
  elif [[ "$allow_vanished" == "yes" && "$rc" -eq 24 ]]; then
    log "NOTE: $label — some transient files vanished during sync (normal on an active system). Your important data is backed up."
    RSYNC_WARNINGS+=("$label: some transient files vanished during sync (rsync exit 24 — normal on active system)")
    return 0
  else
    fail "rsync failed for $label (exit code $rc). See the rsync errors above."
  fi
}

# ── Acquire exclusive run lock BEFORE touching status or log ─────
# Prevents a second invocation from truncating the active run's log
# or overwriting its RUNNING status with FAILED.

mkdir -p "$(dirname "$BACKUP_LOCK")" 2>/dev/null || true
if ! exec {LOCK_FD}>>"$BACKUP_LOCK" 2>/dev/null; then
  echo "ERROR: Cannot open lock file: $BACKUP_LOCK." >&2
  exit 1
fi
if ! flock --nonblock "$LOCK_FD" 2>/dev/null; then
  echo "Another backup is already running (lock held on $BACKUP_LOCK)." >&2
  exit 0
fi
LOCK_ACQUIRED=1

# ── Initialise log and status now that we own the lock ───────────

mkdir -p "$(dirname "$BACKUP_LOG")" "$(dirname "$BACKUP_STATUS")" 2>/dev/null || true
: > "$BACKUP_LOG"
set_status "RUNNING"

log "=== Sovran_SystemsOS External Hub Backup ==="
log "Starting backup process…"

require_cmd rsync
require_cmd findmnt
require_cmd lsblk
require_cmd mountpoint
require_cmd df
require_cmd du
require_cmd awk
require_cmd find
require_cmd hostname
require_cmd date
require_cmd python3
require_cmd flock
require_cmd sync

# ── Detect system role ───────────────────────────────────────────

ROLE="$(detect_role)"
case "$ROLE" in
  desktop)              ROLE_LABEL="Desktop Only" ;;
  node)                 ROLE_LABEL="Node (Bitcoin-only)" ;;
  server_plus_desktop)  ROLE_LABEL="Server + Desktop" ;;
  *)                    ROLE_LABEL="$ROLE" ;;
esac
log "Detected role: $ROLE_LABEL"

# Backup scope depends on the role. Desktop Only systems run no server or
# Bitcoin services, so only the NixOS configuration and home directory are
# mirrored (2 stages). Node and Server + Desktop systems also mirror
# nix-bitcoin secrets, database dumps, and /var/lib service data (5 stages).
if [[ "$ROLE" == "desktop" ]]; then
  TOTAL_STAGES=2
  HOME_STAGE_NUM=2
  log "Desktop Only role: backing up the NixOS configuration (/etc/nixos) and home directory (/home) only."
else
  TOTAL_STAGES=5
  HOME_STAGE_NUM=4
fi

# ── Detect target drive ──────────────────────────────────────────

if [[ -z "${BACKUP_TARGET:-}" && -f "$BACKUP_TARGET_FILE" ]]; then
  BACKUP_TARGET="$(tr -d '\r\n' < "$BACKUP_TARGET_FILE" 2>/dev/null || true)"
fi

if [[ -n "${BACKUP_TARGET:-}" ]]; then
  TARGET="$BACKUP_TARGET"
  if is_internal "$TARGET"; then
    fail "Target '$TARGET' is an internal system drive and cannot be used for external backup."
  fi
  log "Using specified backup target: $TARGET"
else
  log "Auto-detecting external USB drives…"
  TARGET="$(find_external_drive)"
  if [[ -z "$TARGET" ]]; then
    fail "No external USB drive detected. Please plug in an ext4-formatted USB drive and try again."
  fi
  log "Detected external drive: $TARGET"
fi

validate_target_mount "$TARGET"

# ── Set up stable backup destination ────────────────────────────
# Subsequent runs update the same mirror, transferring only new or changed files.

BACKUP_ROOT_DIR="${TARGET}/Sovran_SystemsOS_Backup"
BACKUP_DIR="${TARGET}/${BACKUP_SUBPATH}"
mkdir -p -- "$BACKUP_DIR"

# Prevent GNOME LocalSearch (Tracker) and media scanners from indexing the
# backup mirror and holding open file descriptors when the user ejects the drive.
touch "$BACKUP_ROOT_DIR/.trackerignore" "$BACKUP_ROOT_DIR/.nomedia" 2>/dev/null || true

# Remove any stale BACKUP_COMPLETE left by a previous successful run.
# The new run will re-earn it only after all stages succeed.
rm -f "$BACKUP_DIR/BACKUP_COMPLETE"

# Write an INCOMPLETE marker immediately; replaced by BACKUP_COMPLETE only
# after all rsync stages, manifest write, and disk sync succeed.
touch "$BACKUP_DIR/INCOMPLETE"
log "Backup destination: $BACKUP_DIR"

# ── Estimate required free space ─────────────────────────────────
# Subtract space already occupied by an existing backup mirror on this drive
# so incremental repeat runs do not falsely fail when the drive is >50% full.

SRC_ETC_NIXOS="${SRC_PREFIX}/etc/nixos"
SRC_SECRETS="${SRC_PREFIX}/etc/nix-bitcoin-secrets"
SRC_HOME="${SRC_PREFIX}/home"
SRC_VAR_LIB="${SRC_PREFIX}/var/lib"

ETC_NIXOS_BYTES=$(estimate_path_bytes "$SRC_ETC_NIXOS")
HOME_BYTES=$(estimate_path_bytes "$SRC_HOME" --exclude='*/.cache' --exclude='*/.local/share/Trash' --exclude='*/Trash')

SECRETS_BYTES=0
VAR_LIB_BYTES=0
DB_BYTES=0
if [[ "$ROLE" != "desktop" ]]; then
  SECRETS_BYTES=$(estimate_path_bytes "$SRC_SECRETS")
  DB_BYTES=$(estimate_db_bytes)
  VAR_LIB_BYTES=$(estimate_path_bytes "$SRC_VAR_LIB" \
    --exclude='postgresql' \
    --exclude='mysql' \
    --exclude='mariadb' \
    --exclude='bitcoind' \
    --exclude='electrs' \
    --exclude='flatpak' \
    --exclude='udisks2' \
    --exclude='systemd/coredump' \
    --exclude='*/log' \
    --exclude='*/logs' \
    --exclude='*/cache' \
    --exclude='*/tmp')
fi

ESTIMATED_BYTES=$(( ETC_NIXOS_BYTES + HOME_BYTES + SECRETS_BYTES + DB_BYTES + VAR_LIB_BYTES ))

EXISTING_BACKUP_BYTES=0
if [[ -d "$BACKUP_DIR" ]]; then
  EXISTING_BACKUP_BYTES=$(estimate_path_bytes "$BACKUP_DIR")
fi

if (( ESTIMATED_BYTES > EXISTING_BACKUP_BYTES )); then
  NET_NEW_BYTES=$(( ESTIMATED_BYTES - EXISTING_BACKUP_BYTES ))
else
  NET_NEW_BYTES=0
fi

# Require 20% headroom on net new data plus a fixed safety margin for
# rsync temporary files and database dumps.
REQUIRED_BYTES=$(( NET_NEW_BYTES + (NET_NEW_BYTES / 5) + SAFETY_MARGIN_BYTES ))

FREE_BYTES=$(df -B1 --output=avail "$TARGET" | tail -1 | tr -d ' ')
FREE_GB=$(( FREE_BYTES / 1024 / 1024 / 1024 ))
REQUIRED_GB=$(( REQUIRED_BYTES / 1024 / 1024 / 1024 ))

log "Estimated total backup size: $(( ESTIMATED_BYTES / 1024 / 1024 / 1024 )) GB (existing mirror on drive: $(( EXISTING_BACKUP_BYTES / 1024 / 1024 / 1024 )) GB)"
log "Required additional free space (with safety margin): ${REQUIRED_GB} GB"
log "Free space on drive: ${FREE_GB} GB"

(( FREE_BYTES >= REQUIRED_BYTES )) || \
  fail "Not enough free space on drive (${FREE_GB} GB available, ${REQUIRED_GB} GB required)."

# ── Stage 1: NixOS configuration ────────────────────────────────

log ""
log "── Stage 1/${TOTAL_STAGES}: NixOS configuration (/etc/nixos) ──────────────"
if [[ -d "$SRC_ETC_NIXOS" ]]; then
  sync_tree "/etc/nixos" no "$SRC_ETC_NIXOS/" "$BACKUP_DIR/etc/nixos/"
  log "Stage 1 complete."
else
  log "WARNING: /etc/nixos not found — skipping."
fi

# ── Stage 2: Secrets ────────────────────────────────────────────
# Only applies to the Node and Server + Desktop roles.

if [[ "$ROLE" != "desktop" ]]; then
  log ""
  log "── Stage 2/${TOTAL_STAGES}: Secrets (/etc/nix-bitcoin-secrets) ───────────"
  if [[ -e "$SRC_SECRETS" ]]; then
    sync_tree "/etc/nix-bitcoin-secrets" no "$SRC_SECRETS/" "$BACKUP_DIR/etc/nix-bitcoin-secrets/"
  else
    log "(not found: /etc/nix-bitcoin-secrets — skipping)"
  fi
  log "Stage 2 complete."
fi

# ── Stage 3: Application databases ──────────────────────────────
# Consistent SQL dumps for PostgreSQL (Nextcloud, Matrix Synapse, BTCPay)
# and MariaDB (WordPress) on Node and Server + Desktop roles.

if [[ "$ROLE" != "desktop" ]]; then
  log ""
  log "── Stage 3/${TOTAL_STAGES}: Application databases (SQL dumps) ───────────"
  dump_databases
  log "Stage 3 complete."
fi

# ── Home directory ──────────────────────────────────────────────
# Stage 2/2 on Desktop Only, stage 4/5 on Node and Server + Desktop.
# Rsync exit code 24 (vanished source files) is treated as nonfatal here
# because the desktop may be active.

log ""
log "── Stage ${HOME_STAGE_NUM}/${TOTAL_STAGES}: Home directory (/home) ───────────────────────"
if [[ -d "$SRC_HOME" ]]; then
  sync_tree "/home" yes "$SRC_HOME/" "$BACKUP_DIR/home/" \
    --exclude='.cache/' \
    --exclude='.local/share/Trash/' \
    --exclude='Trash/' \
    --exclude='.mozilla/firefox/*/cache2/' \
    --exclude='.mozilla/firefox/*/startupCache/' \
    --exclude='.mozilla/firefox/*/thumbnails/' \
    --exclude='.config/google-chrome/*/Cache/' \
    --exclude='.config/google-chrome/*/Code Cache/' \
    --exclude='.config/chromium/*/Cache/' \
    --exclude='.config/chromium/*/Code Cache/' \
    --exclude='.config/BraveSoftware/Brave-Browser/*/Cache/' \
    --exclude='.config/BraveSoftware/Brave-Browser/*/Code Cache/' \
    --exclude='.config/BraveSoftware/Brave-Origin/*/Cache/' \
    --exclude='.config/BraveSoftware/Brave-Origin/*/Code Cache/' \
    --exclude='.local/share/baloo/' \
    --exclude='.thumbnails/' \
    --exclude='.xsession-errors' \
    --exclude='.xsession-errors.old'
  log "Stage ${HOME_STAGE_NUM} complete."
else
  log "WARNING: /home not found — skipping."
fi

# ── Stage 5: System data ────────────────────────────────────────
# Only applies to the Node and Server + Desktop roles.
# Raw PostgreSQL/MariaDB directories are excluded (backed up cleanly as SQL
# dumps in Stage 3). Bitcoin/Electrs data live on the internal second drive.
# Flatpak runtimes, udisks state, and coredumps are excluded as reconstructable.
# allow_vanished is "yes" so active services rotating transient temp files
# (Nextcloud cron, Redis RDB, Tor consensus, systemd timers) do not abort Stage 5.

if [[ "$ROLE" != "desktop" ]]; then
  log ""
  log "── Stage 5/${TOTAL_STAGES}: System data (/var/lib) ───────────────────────"
  if [[ -d "$SRC_VAR_LIB" ]]; then
    sync_tree "/var/lib" yes "$SRC_VAR_LIB/" "$BACKUP_DIR/var/lib/" \
      --exclude='postgresql/' \
      --exclude='mysql/' \
      --exclude='mariadb/' \
      --exclude='bitcoind/' \
      --exclude='electrs/' \
      --exclude='flatpak/' \
      --exclude='udisks2/' \
      --exclude='systemd/coredump/' \
      --exclude='*/log/' \
      --exclude='*/logs/' \
      --exclude='*/cache/' \
      --exclude='*/tmp/'
    log "Stage 5 complete."
  else
    log "WARNING: /var/lib not found — skipping."
  fi
fi

# ── Generate manifest ────────────────────────────────────────────

log ""
log "Generating BACKUP_MANIFEST.txt …"
MANIFEST_FILE="$BACKUP_DIR/BACKUP_MANIFEST.txt"

{
  echo "Sovran_SystemsOS Backup Manifest"
  echo "Updated:   $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "Hostname:  $(hostname)"
  echo "Role:      $ROLE_LABEL"
  echo "Target:    $TARGET"
  echo ""
  echo "Backup type: Live rsync mirror (directly browsable files)"
  echo "Location:    ${BACKUP_DIR}"
  echo ""
  echo "Source paths mirrored:"
  echo "- /etc/nixos  →  current/etc/nixos/"
  if [[ "$ROLE" != "desktop" ]]; then
    echo "- /etc/nix-bitcoin-secrets (when present)  →  current/etc/nix-bitcoin-secrets/"
    echo "- PostgreSQL / MariaDB SQL dumps (when active)  →  current/databases/"
  fi
  echo "- /home  →  current/home/"
  if [[ "$ROLE" != "desktop" ]]; then
    echo "- /var/lib  →  current/var/lib/"
  fi
  echo ""
  echo "Exclusions:"
  if [[ "$ROLE" != "desktop" ]]; then
    echo "- /var/lib/postgresql, /var/lib/mysql, /var/lib/mariadb (raw DB files excluded; logical SQL dumps stored in current/databases/)"
    echo "- /var/lib/bitcoind (Bitcoin blockchain — excluded; lives on internal second drive)"
    echo "- /var/lib/electrs (Electrs index — excluded; lives on internal second drive)"
    echo "- /var/lib/flatpak, /var/lib/udisks2, /var/lib/systemd/coredump (reconstructable runtime state)"
    echo "- /run/media/Second_Drive (internal second drive — never traversed)"
    echo "- /var/lib/*/log, /var/lib/*/logs, /var/lib/*/cache, /var/lib/*/tmp"
  fi
  echo "- Browser disk caches, thumbnail caches, trash directories, X session error logs"
  echo ""
  echo "Important limitations:"
  if [[ "$ROLE" != "desktop" ]]; then
    echo "- Bitcoin blockchain data and Electrs indexes are NOT included; they are"
    echo "  reconstructable or stored on the internal second drive."
  fi
  echo "- File trees are mirrored from a live system; files actively written mid-copy"
  echo "  may reflect an in-flight state."
  echo ""
  echo "Restore guidance (run from a root shell via 'su -' or from the Sovran Live ISO):"
  echo "- Files are directly browsable on the backup drive under: ${BACKUP_DIR}"
  echo "- To restore directories:"
  echo "    rsync -aAXH --numeric-ids current/etc/nixos/ /etc/nixos/"
  echo "    rsync -aAXH --numeric-ids current/home/ /home/"
  if [[ "$ROLE" != "desktop" ]]; then
    echo "    rsync -aAXH --numeric-ids current/var/lib/ /var/lib/"
    echo "- To restore SQL dumps (when present):"
    echo "    psql -U postgres -f current/databases/postgresql-all.sql"
    echo "    mysql -u root < current/databases/mariadb-all.sql"
  fi
  echo "- To copy individual files:"
  echo "    cp -a current/home/free/ /home/free/"
  echo "- When restoring /etc/nixos to replacement hardware, regenerate"
  echo "  hardware-configuration.nix for the new hardware before rebuilding."
  echo ""
  echo "Nonfatal warnings:"
  if [[ "${#RSYNC_WARNINGS[@]}" -eq 0 ]]; then
    echo "- none"
  else
    for warning in "${RSYNC_WARNINGS[@]}"; do
      echo "- $warning"
    done
  fi
  if [[ "$ROLE" != "desktop" ]]; then
    echo ""
    echo "Note: Bitcoin blockchain and Electrs index data are intentionally excluded"
    echo "from manual external backup because they already live on the internal second drive"
    echo "(/run/media/Second_Drive) and are reconstructable/internal-backup data."
  fi
} > "$MANIFEST_FILE"

log "Manifest written to $MANIFEST_FILE"

# ── Finalise markers & flush USB writeback BEFORE reporting SUCCESS ──

rm -f "$BACKUP_DIR/INCOMPLETE"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$BACKUP_DIR/BACKUP_COMPLETE"

log "Flushing pending disk writes to USB drive…"
sync -f "$BACKUP_DIR/BACKUP_COMPLETE" 2>/dev/null || sync
log "All disk buffers flushed."

log ""
if [[ "${#RSYNC_WARNINGS[@]}" -gt 0 ]]; then
  log "Backup completed with nonfatal warnings:"
  for warning in "${RSYNC_WARNINGS[@]}"; do
    log "  WARNING: $warning"
  done
  log "Your important data is backed up. The warnings above indicate transient"
  log "files that vanished during backup, which is normal on an active system."
  log ""
fi
if [[ "$ROLE" == "desktop" ]]; then
  log "All Finished! Your data is now backed up to a second, external location."
else
  log "All Finished! Your data is now backed up to a third location."
fi
log "Files are directly browsable on the drive under: ${BACKUP_DIR}"
log "Click 'Safely Eject Drive' in the Hub before unplugging your USB drive."

BACKUP_COMPLETE=1
set_status "SUCCESS"
