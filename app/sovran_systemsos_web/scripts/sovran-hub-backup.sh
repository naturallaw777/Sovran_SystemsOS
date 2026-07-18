#!/usr/bin/env bash
# ── Sovran Hub External Backup Script ────────────────────────────
# Backs up Sovran_SystemsOS data to an external USB hard drive.
# Designed for the Hub web UI (no GUI dependencies).
#
# Your Sovran Pro already backs up your data automatically to its
# internal second drive (BTCEcoandBackup at /run/media/Second_Drive).
# This script creates an additional copy on an external USB drive —
# storing your data in a third location for maximum protection.
#
# Usage:
#   BACKUP_TARGET=/run/media/<user>/<drive> bash sovran-hub-backup.sh
#   (or run with no env var to auto-detect the first external USB drive)

set -euo pipefail

BACKUP_LOG="/var/log/sovran-hub-backup.log"
BACKUP_STATUS="/var/log/sovran-hub-backup.status"
MEDIA_ROOT="/run/media"
HUB_CONFIG_JSON="/var/lib/sovran-hub/config.json"
ROLE_STATE_NIX="/etc/nixos/role-state.nix"
SECOND_DRIVE_MOUNT="/run/media/Second_Drive"
SAFETY_MARGIN_BYTES=$((1024 * 1024 * 1024))

# ── Internal drive labels/paths to NEVER use as backup targets ───
INTERNAL_LABELS=("BTCEcoandBackup" "sovran_systemsos")
INTERNAL_MOUNTS=("$SECOND_DRIVE_MOUNT" "/boot/efi" "/")

FAILED_ALREADY=0
BACKUP_COMPLETE=0
LND_STOPPED=0
LND_UNITS_TO_RESTART=()

ARCHIVE_FILES=()
ARCHIVE_WARNINGS=()
PARTIAL_FILES=()
DB_DUMP_FILES=()
MANIFEST_EXCLUDES=()
LND_BACKUP_NOTES=()

# ── Logging helpers ──────────────────────────────────────────────

log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
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
  local restart_failed=0

  # Remove any partial archive files or temporary diagnostic files
  if [[ "${#PARTIAL_FILES[@]}" -gt 0 ]]; then
    local partial
    for partial in "${PARTIAL_FILES[@]}"; do
      [[ -f "$partial" ]] && rm -f "$partial" || true
    done
  fi

  if [[ "$LND_STOPPED" -eq 1 ]]; then
    log "Restarting previously active LND-related services…"
    for (( idx=${#LND_UNITS_TO_RESTART[@]}-1 ; idx>=0 ; idx-- )); do
      local unit="${LND_UNITS_TO_RESTART[$idx]}"
      if systemctl start "$unit"; then
        log "Started $unit"
      else
        log "ERROR: Failed to start $unit"
        restart_failed=1
      fi
    done
    LND_STOPPED=0
  fi

  if [[ "$restart_failed" -eq 1 ]]; then
    rc=1
    FAILED_ALREADY=1
    set_status "FAILED"
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
  fstype=$(findmnt -n -o FSTYPE -T "$target" 2>/dev/null || true)
  [[ -n "$fstype" ]] || fail "Could not determine filesystem type for '$target'."

  if [[ "$fstype" != "exfat" && "$fstype" != "fuseblk" ]]; then
    fail "Target '$target' must be exFAT (detected filesystem: $fstype)."
  fi

  if [[ "$fstype" == "fuseblk" ]]; then
    local src_dev blk_type
    src_dev=$(findmnt -n -o SOURCE -T "$target" 2>/dev/null || true)
    blk_type=""
    if [[ -n "$src_dev" ]]; then
      blk_type=$(lsblk -no FSTYPE "$src_dev" 2>/dev/null || true)
      [[ -z "$blk_type" ]] && blk_type=$(blkid -o value -s TYPE "$src_dev" 2>/dev/null || true)
    fi
    if [[ "$blk_type" != "exfat" && "$blk_type" != "fuseblk" ]]; then
      fail "Target '$target' is fuseblk but not identified as exFAT-compatible."
    fi
  fi

  local write_test
  write_test="$target/.sovran-write-test-$$"
  if ! ( : > "$write_test" && echo "ok" >> "$write_test" && rm -f "$write_test" ); then
    fail "Target '$target' is not writable."
  fi

  log "Verified backup target filesystem: $fstype"
}

has_unit() {
  systemctl cat "$1" >/dev/null 2>&1
}

is_unit_active() {
  systemctl is-active --quiet "$1"
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

# ── Initialise log file ──────────────────────────────────────────

: > "$BACKUP_LOG"
set_status "RUNNING"

log "=== Sovran_SystemsOS External Hub Backup ==="
log "Starting backup process…"

# ── Acquire exclusive run lock ────────────────────────────────────
# Prevents two simultaneous backup runs (e.g. from double-click or
# stale RUNNING status after a Hub restart).

LOCK_FILE="/var/lock/sovran-hub-backup.lock"
exec {LOCK_FD}>>"$LOCK_FILE" 2>/dev/null || \
  fail "Cannot open lock file: $LOCK_FILE. Ensure /var/lock is writable."
flock --nonblock "$LOCK_FD" 2>/dev/null || \
  fail "Another backup is already running. Wait for it to complete or check $BACKUP_STATUS."

require_cmd tar
require_cmd sha256sum
require_cmd findmnt
require_cmd lsblk
require_cmd mountpoint
require_cmd df
require_cmd du
require_cmd awk
require_cmd sort
require_cmd find
require_cmd systemctl
require_cmd hostname
require_cmd date
require_cmd python3
require_cmd runuser
require_cmd mktemp
require_cmd flock

# ── Detect system role ───────────────────────────────────────────

ROLE="$(detect_role)"
case "$ROLE" in
  desktop)              ROLE_LABEL="Desktop Only" ;;
  node)                 ROLE_LABEL="Node (Bitcoin-only)" ;;
  server_plus_desktop)  ROLE_LABEL="Server + Desktop" ;;
  *)                    ROLE_LABEL="$ROLE" ;;
esac
log "Detected role: $ROLE_LABEL"

# ── Detect target drive ──────────────────────────────────────────

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
    fail "No external USB drive detected. Please plug in an exFAT-formatted USB drive and try again."
  fi
  log "Detected external drive: $TARGET"
fi

validate_target_mount "$TARGET"

# ── Plan role-aware source scope and exclusions ─────────────────

LND_AVAILABLE=0
if [[ "$ROLE" != "desktop" ]] && [[ -d /var/lib/lnd ]] && has_unit "lnd.service"; then
  LND_AVAILABLE=1
fi

if [[ "$ROLE" == "desktop" ]]; then
  MANIFEST_EXCLUDES+=("/etc/nix-bitcoin-secrets (not applicable for Desktop Only role)")
else
  MANIFEST_EXCLUDES+=("/etc/nix-bitcoin-secrets skipped when path absent")
fi

MANIFEST_EXCLUDES+=(
  "/run/media/Second_Drive (never traversed)"
  "/run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node (excluded; internal second-drive data)"
  "/run/media/Second_Drive/BTCEcoandBackup/Electrs_Data (excluded; internal second-drive data)"
  "/var/lib/bitcoind (excluded from manual backup)"
  "/var/lib/electrs (excluded from manual backup)"
  "/var/lib/*/log and /var/lib/*/logs"
  "/var/lib/*/cache and /var/lib/*/tmp"
  "/home/*/.cache (system and application disk caches)"
  "/home/*/.local/share/Trash and /home/*/Trash (trash directories)"
  "/home/*/.mozilla/firefox/*/cache2 and */startupCache (Firefox volatile cache — profile data is kept)"
  "/home/*/.config/google-chrome/*/Cache (Chrome disk cache — profile data is kept)"
  "/home/*/.config/chromium/*/Cache (Chromium disk cache — profile data is kept)"
  "/home/*/.config/BraveSoftware/Brave-Browser/*/Cache (Brave disk cache — profile data is kept)"
  "/home/*/.local/share/baloo (KDE file indexer — rebuilt automatically)"
  "/home/*/.thumbnails (thumbnail cache — rebuilt automatically)"
  "/home/*/.xsession-errors and .xsession-errors.old (X session error logs)"
)

if [[ "$ROLE" == "desktop" || "$LND_AVAILABLE" -eq 1 ]]; then
  MANIFEST_EXCLUDES+=("/var/lib/lnd from general /var/lib archive")
fi

# ── Estimate required free space ─────────────────────────────────

ETC_NIXOS_BYTES=$(estimate_path_bytes /etc/nixos)
HOME_BYTES=$(estimate_path_bytes /home --exclude='*/.cache' --exclude='*/.local/share/Trash' --exclude='*/Trash')
SECRETS_BYTES=0
if [[ "$ROLE" != "desktop" ]]; then
  SECRETS_BYTES=$(estimate_path_bytes /etc/nix-bitcoin-secrets)
fi

VAR_LIB_BYTES=$(estimate_path_bytes /var/lib \
  --exclude='bitcoind' \
  --exclude='electrs' \
  --exclude='lnd' \
  --exclude='*/log' \
  --exclude='*/logs' \
  --exclude='*/cache' \
  --exclude='*/tmp')

LND_BYTES=0
if [[ "$LND_AVAILABLE" -eq 1 ]]; then
  LND_BYTES=$(estimate_path_bytes /var/lib/lnd)
fi

ESTIMATED_BYTES=$(( ETC_NIXOS_BYTES + HOME_BYTES + SECRETS_BYTES + VAR_LIB_BYTES + LND_BYTES ))
# Require 20% growth headroom plus an additional fixed 1 GiB safety margin.
REQUIRED_BYTES=$(( ESTIMATED_BYTES + (ESTIMATED_BYTES / 5) + SAFETY_MARGIN_BYTES ))

FREE_BYTES=$(df -B1 --output=avail "$TARGET" | tail -1 | tr -d ' ')
FREE_GB=$(( FREE_BYTES / 1024 / 1024 / 1024 ))
REQUIRED_GB=$(( REQUIRED_BYTES / 1024 / 1024 / 1024 ))

log "Estimated backup size: $(( ESTIMATED_BYTES / 1024 / 1024 / 1024 )) GB"
log "Required free space (with safety margin): ${REQUIRED_GB} GB"
log "Free space on drive: ${FREE_GB} GB"

(( FREE_BYTES >= REQUIRED_BYTES )) || \
  fail "Not enough free space on drive (${FREE_GB} GB available, ${REQUIRED_GB} GB required)."

# ── Create timestamped backup directory ─────────────────────────

TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
BACKUP_DIR="${TARGET}/Sovran_SystemsOS_Backup/${TIMESTAMP}"
DB_DUMP_DIR="$BACKUP_DIR/database-dumps"
mkdir -p "$BACKUP_DIR" "$DB_DUMP_DIR"
# Write an INCOMPLETE marker immediately; it is removed only on successful completion.
# Failed runs keep this marker so they are easily identifiable and not confused with
# complete backups during restore selection.
touch "$BACKUP_DIR/INCOMPLETE"
log "Backup destination: $BACKUP_DIR"

create_tar_archive() {
  _create_archive_impl STRICT "$@"
}

# ── Helper: classify a GNU tar (LC_ALL=C) diagnostic line ────────
# Returns 0 (true) if the message is an allowlisted transient condition
# that is safe to ignore for /home (live desktop file changes).
# Only two verified GNU tar messages qualify; all others are fatal.
_is_home_warning_allowlisted() {
  local msg="$1"
  case "$msg" in
    *"file changed as we read it"*)   return 0 ;;
    *"file removed before we read it"*) return 0 ;;
    *) return 1 ;;
  esac
}

# ── Internal archive builder ──────────────────────────────────────
# mode: STRICT — any tar error fails.
#       HOME   — tar exit 1 is accepted when every diagnostic is an
#                allowlisted transient condition (live file changes).
_create_archive_impl() {
  local mode="$1"; shift
  local archive_name="$1"; shift
  local archive_path="$BACKUP_DIR/$archive_name"
  local partial_path="${archive_path}.partial"
  local diag_tmp
  diag_tmp="$(mktemp /tmp/sovran-tar-diag.XXXXXX)"
  PARTIAL_FILES+=("$partial_path" "$diag_tmp")

  log "Creating $archive_name …"

  local tar_rc=0
  LC_ALL=C tar \
    --create \
    --file "$partial_path" \
    --numeric-owner \
    --acls \
    --xattrs \
    --sparse \
    --one-file-system \
    "$@" 2>"$diag_tmp" || tar_rc=$?

  # Log every tar diagnostic to the backup log so it appears in the Hub UI
  local has_fatal_diag=0
  if [[ -s "$diag_tmp" ]]; then
    while IFS= read -r diag_line; do
      [[ -n "$diag_line" ]] || continue
      log "tar: $diag_line"
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
    log "NOTE: $archive_name completed with nonfatal warnings (live files changed" \
        "during backup — this is normal on an active desktop and does not affect" \
        "the safety of your backup)."
    ARCHIVE_WARNINGS+=("$archive_name: nonfatal warnings — live files changed during backup (normal on an active desktop)")
  fi

  if [[ "$accept" -eq 0 ]]; then
    rm -f "$partial_path" "$diag_tmp"
    if [[ "$tar_rc" -gt 1 ]]; then
      fail "tar exited with fatal code $tar_rc while creating $archive_name."
    elif [[ "$mode" == "HOME" ]]; then
      fail "tar exited with code $tar_rc and unrecognized diagnostics while creating $archive_name."
    else
      fail "tar exited with code $tar_rc while creating $archive_name."
    fi
  fi

  # Verify the partial archive is non-empty and readable (spot-check first entry)
  if [[ ! -s "$partial_path" ]]; then
    rm -f "$partial_path" "$diag_tmp"
    fail "Archive $archive_name is empty after creation."
  fi

  local spot_entry
  spot_entry="$(LC_ALL=C tar --list --file "$partial_path" 2>/dev/null | head -1 || true)"
  if [[ -z "$spot_entry" ]]; then
    rm -f "$partial_path" "$diag_tmp"
    fail "Archive $archive_name failed readability check."
  fi

  # Atomic publish: rename partial to final path only after acceptance
  mv "$partial_path" "$archive_path"
  rm -f "$diag_tmp"
  ARCHIVE_FILES+=("$archive_name")
  log "Created archive: $archive_name"
}

# ── Home archive: tolerates allowlisted live-file warnings ───────
create_home_tar_archive() {
  _create_archive_impl HOME "$@"
}

export_postgresql_dumps() {
  if ! command -v pg_dump >/dev/null 2>&1 || ! has_unit "postgresql.service"; then
    log "PostgreSQL tools/service not available — skipping PostgreSQL exports."
    return
  fi

  if ! is_unit_active "postgresql.service"; then
    log "PostgreSQL service is not active — skipping PostgreSQL exports."
    return
  fi

  log "Exporting PostgreSQL globals and databases…"
  local globals_file="$DB_DUMP_DIR/postgresql_globals.sql"
  runuser -u postgres -- pg_dumpall --globals-only > "$globals_file" || \
    fail "Failed to export PostgreSQL globals."
  DB_DUMP_FILES+=("database-dumps/postgresql_globals.sql")

  local dbs
  dbs=$(runuser -u postgres -- psql -Atqc "SELECT datname FROM pg_database WHERE datistemplate = false AND datallowconn AND datname <> 'postgres';" 2>/dev/null || true)

  if [[ -z "$dbs" ]]; then
    log "No non-template PostgreSQL application databases found."
    return
  fi

  while IFS= read -r db; do
    [[ -n "$db" ]] || continue
    local safe_db
    safe_db="$(echo "$db" | tr -c '[:alnum:]_.-' '_')"
    local out_file="$DB_DUMP_DIR/postgresql_${safe_db}.dump"
    runuser -u postgres -- pg_dump --format=custom --file "$out_file" "$db" || \
      fail "Failed to export PostgreSQL database '$db'."
    DB_DUMP_FILES+=("database-dumps/postgresql_${safe_db}.dump")
  done <<< "$dbs"
}

export_mariadb_dumps() {
  local dump_cmd=""
  local query_cmd=""
  local mariadb_unit=""

  if command -v mariadb-dump >/dev/null 2>&1; then
    dump_cmd="mariadb-dump"
  elif command -v mysqldump >/dev/null 2>&1; then
    dump_cmd="mysqldump"
  fi

  if command -v mariadb >/dev/null 2>&1; then
    query_cmd="mariadb"
  elif command -v mysql >/dev/null 2>&1; then
    query_cmd="mysql"
  fi

  if [[ -z "$dump_cmd" || -z "$query_cmd" ]]; then
    log "MariaDB dump/query tools not available — skipping MariaDB exports."
    return
  fi

  if has_unit "mariadb.service" && is_unit_active "mariadb.service"; then
    mariadb_unit="mariadb.service"
  elif has_unit "mysql.service" && is_unit_active "mysql.service"; then
    mariadb_unit="mysql.service"
  else
    log "MariaDB service is not active — skipping MariaDB exports."
    return
  fi

  log "Exporting MariaDB databases from ${mariadb_unit}…"

  local dbs
  dbs=$($query_cmd -N -e "SHOW DATABASES" 2>/dev/null || true)
  if [[ -z "$dbs" ]]; then
    log "No MariaDB databases found."
    return
  fi

  while IFS= read -r db; do
    [[ -n "$db" ]] || continue
    case "$db" in
      information_schema|performance_schema|mysql|sys) continue ;;
    esac

    local safe_db out_file
    safe_db="$(echo "$db" | tr -c '[:alnum:]_.-' '_')"
    out_file="$DB_DUMP_DIR/mariadb_${safe_db}.sql"

    $dump_cmd --single-transaction --quick --routines --events --triggers "$db" > "$out_file" || \
      fail "Failed to export MariaDB database '$db'."

    DB_DUMP_FILES+=("database-dumps/mariadb_${safe_db}.sql")
  done <<< "$dbs"
}

export_lnd_scb_if_possible() {
  [[ "$LND_AVAILABLE" -eq 1 ]] || return

  local scb_file="$BACKUP_DIR/lnd-static-channel-backup.scb"
  local attempts=(
    "lncli exportchanbackup --all --output_file $scb_file"
    "lncli -n mainnet exportchanbackup --all --output_file $scb_file"
    "runuser -u lnd -- lncli exportchanbackup --all --output_file $scb_file"
    "runuser -u lnd -- lncli -n mainnet exportchanbackup --all --output_file $scb_file"
  )

  if ! command -v lncli >/dev/null 2>&1; then
    log "lncli not available — skipping Static Channel Backup export."
    LND_BACKUP_NOTES+=("Static Channel Backup skipped (lncli unavailable)")
    return
  fi

  if ! is_unit_active "lnd.service"; then
    log "LND service is not active — skipping Static Channel Backup export."
    LND_BACKUP_NOTES+=("Static Channel Backup skipped (lnd.service inactive)")
    return
  fi

  log "Exporting LND Static Channel Backup…"
  local attempt
  for attempt in "${attempts[@]}"; do
    if eval "$attempt" >/dev/null 2>&1; then
      DB_DUMP_FILES+=("lnd-static-channel-backup.scb")
      LND_BACKUP_NOTES+=("Static Channel Backup exported via lncli")
      log "LND Static Channel Backup exported."
      return
    fi
  done

  log "WARNING: Unable to export LND Static Channel Backup with available lncli invocations."
  LND_BACKUP_NOTES+=("Static Channel Backup export failed (no compatible lncli invocation succeeded)")
}

capture_active_lnd_dependents() {
  [[ "$LND_AVAILABLE" -eq 1 ]] || return

  LND_UNITS_TO_RESTART=()
  local raw_units=""
  raw_units=$(systemctl show lnd.service -p RequiredBy -p WantedBy --value 2>/dev/null | tr ' ' '\n' | grep '\.service$' | sort -u || true)

  while IFS= read -r unit; do
    [[ -n "$unit" ]] || continue
    if is_unit_active "$unit"; then
      LND_UNITS_TO_RESTART+=("$unit")
    fi
  done <<< "$raw_units"

  if is_unit_active "lnd.service"; then
    LND_UNITS_TO_RESTART+=("lnd.service")
  fi
}

stop_lnd_stack_if_needed() {
  [[ "$LND_AVAILABLE" -eq 1 ]] || return

  capture_active_lnd_dependents

  if [[ "${#LND_UNITS_TO_RESTART[@]}" -eq 0 ]]; then
    log "No active LND-related services needed stopping."
    return
  fi

  log "Stopping active services that depend on LND for clean /var/lib/lnd archive…"

  local unit
  for unit in "${LND_UNITS_TO_RESTART[@]}"; do
    if [[ "$unit" == "lnd.service" ]]; then
      continue
    fi
    systemctl stop "$unit" || fail "Failed to stop dependent service: $unit"
    log "Stopped $unit"
  done

  if printf '%s\n' "${LND_UNITS_TO_RESTART[@]}" | grep -qx 'lnd.service'; then
    systemctl stop lnd.service || fail "Failed to stop lnd.service"
    log "Stopped lnd.service"
  fi

  LND_STOPPED=1
}

# ── Stage 1/5: NixOS configuration ──────────────────────────────

log ""
log "── Stage 1/5: NixOS configuration (/etc/nixos) ──────────────"
if [[ -d /etc/nixos ]]; then
  create_tar_archive "etc-nixos.tar" -C / etc/nixos
  log "Stage 1 complete."
else
  log "WARNING: /etc/nixos not found — skipping."
fi

# ── Stage 2/5: Secrets ──────────────────────────────────────────

log ""
log "── Stage 2/5: Secrets (/etc/nix-bitcoin-secrets) ───────────"
if [[ "$ROLE" == "desktop" ]]; then
  log "Skipping /etc/nix-bitcoin-secrets — not applicable for Desktop Only role."
elif [[ -e /etc/nix-bitcoin-secrets ]]; then
  create_tar_archive "etc-nix-bitcoin-secrets.tar" -C / etc/nix-bitcoin-secrets
else
  log "(not found: /etc/nix-bitcoin-secrets — skipping)"
fi
log "Stage 2 complete."

# ── Stage 3/5: Home directory ───────────────────────────────────

log ""
log "── Stage 3/5: Home directory (/home) ───────────────────────"
if [[ -d /home ]]; then
  create_home_tar_archive "home.tar" \
    -C / \
    --exclude='home/*/.cache' \
    --exclude='home/*/.local/share/Trash' \
    --exclude='home/*/Trash' \
    --exclude='home/*/.mozilla/firefox/*/cache2' \
    --exclude='home/*/.mozilla/firefox/*/startupCache' \
    --exclude='home/*/.mozilla/firefox/*/thumbnails' \
    --exclude='home/*/.config/google-chrome/*/Cache' \
    --exclude='home/*/.config/google-chrome/*/Code Cache' \
    --exclude='home/*/.config/chromium/*/Cache' \
    --exclude='home/*/.config/chromium/*/Code Cache' \
    --exclude='home/*/.config/BraveSoftware/Brave-Browser/*/Cache' \
    --exclude='home/*/.config/BraveSoftware/Brave-Browser/*/Code Cache' \
    --exclude='home/*/.local/share/baloo' \
    --exclude='home/*/.thumbnails' \
    --exclude='home/*/.xsession-errors' \
    --exclude='home/*/.xsession-errors.old' \
    home
  log "Stage 3 complete."
else
  log "WARNING: /home not found — skipping."
fi

# ── Stage 4/5: Database exports + LND artifacts ────────────────

log ""
log "── Stage 4/5: Database and LND consistency exports ─────────"
export_postgresql_dumps
export_mariadb_dumps
export_lnd_scb_if_possible

if [[ "$LND_AVAILABLE" -eq 1 ]]; then
  stop_lnd_stack_if_needed
  create_tar_archive "var-lib-lnd-clean.tar" -C / var/lib/lnd
  LND_BACKUP_NOTES+=("Created clean raw /var/lib/lnd archive after controlled service stop")
fi

log "Stage 4 complete."

# ── Stage 5/5: System data ──────────────────────────────────────

log ""
log "── Stage 5/5: System data (/var/lib) ───────────────────────"
if [[ -d /var/lib ]]; then
  VAR_LIB_EXCLUDES=(
    --exclude='var/lib/bitcoind'
    --exclude='var/lib/electrs'
    --exclude='var/lib/*/log'
    --exclude='var/lib/*/logs'
    --exclude='var/lib/*/cache'
    --exclude='var/lib/*/tmp'
  )

  if [[ "$ROLE" == "desktop" || "$LND_AVAILABLE" -eq 1 ]]; then
    VAR_LIB_EXCLUDES+=(--exclude='var/lib/lnd')
  fi

  create_tar_archive "var-lib.tar" -C / "${VAR_LIB_EXCLUDES[@]}" var/lib
  log "Stage 5 complete."
else
  log "WARNING: /var/lib not found — skipping."
fi

# ── Generate manifest ────────────────────────────────────────────

log ""
log "Generating BACKUP_MANIFEST.txt …"
MANIFEST_FILE="$BACKUP_DIR/BACKUP_MANIFEST.txt"
CHECKSUM_FILE="$BACKUP_DIR/SHA256SUMS.txt"

{
  echo "Sovran_SystemsOS Backup Manifest"
  echo "Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "Timestamp: $TIMESTAMP"
  echo "Hostname:  $(hostname)"
  echo "Role:      $ROLE_LABEL"
  echo "Target:    $TARGET"
  echo ""
  echo "Source paths included:"
  echo "- /etc/nixos"
  echo "- /home"
  if [[ "$ROLE" != "desktop" ]]; then
    echo "- /etc/nix-bitcoin-secrets (when present)"
  fi
  echo "- /var/lib"
  echo ""
  echo "Exclusions:"
  for ex in "${MANIFEST_EXCLUDES[@]}"; do
    echo "- $ex"
  done
  echo ""
  echo "Archives:"
  for archive in "${ARCHIVE_FILES[@]}"; do
    echo "- $archive"
  done
  echo ""
  echo "Database and LND exports:"
  if [[ "${#DB_DUMP_FILES[@]}" -eq 0 && "${#LND_BACKUP_NOTES[@]}" -eq 0 ]]; then
    echo "- none"
  else
    for dump in "${DB_DUMP_FILES[@]}"; do
      echo "- $dump"
    done
    for note in "${LND_BACKUP_NOTES[@]}"; do
      echo "- $note"
    done
  fi
  echo ""
  echo "Restore guidance:"
  echo "- Verify artifacts: cd <backup_dir> && sha256sum -c SHA256SUMS.txt"
  echo "- Extract a tar archive: sudo tar --acls --xattrs --numeric-owner -xpf <archive>.tar -C /"
  echo "- PostgreSQL globals: sudo -u postgres psql -f database-dumps/postgresql_globals.sql"
  echo "- PostgreSQL DB dump: sudo -u postgres pg_restore --create --clean --if-exists -d postgres database-dumps/postgresql_<db>.dump"
  echo "- MariaDB DB dump: mariadb <db_name> < database-dumps/mariadb_<db>.sql"
  echo "- LND SCB: keep lnd-static-channel-backup.scb with wallet seed for channel recovery procedures"
  echo "- Note: when restoring /var/lib, exclude raw DB directories (var/lib/postgresql, var/lib/mysql)"
  echo "  and restore from native dumps instead for PostgreSQL and MariaDB"
  echo ""
  echo "Nonfatal warnings:"
  if [[ "${#ARCHIVE_WARNINGS[@]}" -eq 0 ]]; then
    echo "- none"
  else
    for warning in "${ARCHIVE_WARNINGS[@]}"; do
      echo "- $warning"
    done
  fi
  echo ""
  echo "Important note: Bitcoin blockchain and Electrs index data are intentionally excluded"
  echo "from manual external backup because they already live on the internal second drive"
  echo "(/run/media/Second_Drive) and are reconstructable/internal-backup data."
  echo ""
  echo "Artifact listing:"
  find "$BACKUP_DIR" -mindepth 1 -maxdepth 2 -type f ! -name 'INCOMPLETE' | sort
} > "$MANIFEST_FILE"

# ── Generate checksums for all backup artifacts ─────────────────

log "Generating SHA-256 checksums …"
(
  cd "$BACKUP_DIR"
  while IFS= read -r -d '' file; do
    sha256sum "$file"
  done < <(find . -mindepth 1 -maxdepth 2 -type f ! -name 'SHA256SUMS.txt' ! -name 'INCOMPLETE' -print0 | sort -z)
) > "$CHECKSUM_FILE"

log "Manifest written to $MANIFEST_FILE"
log "Checksums written to $CHECKSUM_FILE"

# ── Done ─────────────────────────────────────────────────────────

log ""
if [[ "${#ARCHIVE_WARNINGS[@]}" -gt 0 ]]; then
  log "Backup completed with nonfatal warnings:"
  for warning in "${ARCHIVE_WARNINGS[@]}"; do
    log "  WARNING: $warning"
  done
  log "Your important data is backed up. The warnings above indicate files that changed"
  log "during backup, which is normal on an active desktop and does not affect your backup."
  log ""
fi
log "All Finished! Your data is now backed up to a third location."
log "Please eject the drive safely before removing it from your Sovran Pro."

# Remove incomplete marker and write completion marker only after all work succeeds
rm -f "$BACKUP_DIR/INCOMPLETE"
echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$BACKUP_DIR/BACKUP_COMPLETE"

BACKUP_COMPLETE=1
set_status "SUCCESS"
