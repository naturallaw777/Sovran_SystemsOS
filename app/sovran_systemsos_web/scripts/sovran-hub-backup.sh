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
MIN_FREE_GB=10
HUB_CONFIG_JSON="/var/lib/sovran-hub/config.json"
ROLE_STATE_NIX="/etc/nixos/role-state.nix"

# ── Internal drive labels/paths to NEVER use as backup targets ───
INTERNAL_LABELS=("BTCEcoandBackup" "sovran_systemsos")
INTERNAL_MOUNTS=("/run/media/Second_Drive" "/boot/efi" "/")

# ── Logging helpers ──────────────────────────────────────────────

log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  echo "$msg" | tee -a "$BACKUP_LOG"
}

set_status() {
  echo "$1" > "$BACKUP_STATUS"
}

fail() {
  log "ERROR: $*"
  set_status "FAILED"
  exit 1
}

# ── Check whether a mount point is an internal drive ────────────

is_internal() {
  local mnt="$1"
  # Reject known internal mount points and their subdirectories
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
  # lsblk JSON output: NAME,LABEL,MOUNTPOINT,HOTPLUG,RM,TYPE
  if command -v lsblk &>/dev/null; then
    while IFS=$'\t' read -r dev_type hotplug removable label mountpoint; do
      # Must be a partition or disk, and be removable/hotplug
      [[ "$dev_type" == "part" || "$dev_type" == "disk" ]] || continue
      [[ "$hotplug" == "1" || "$removable" == "1" ]] || continue
      [[ -n "$mountpoint" ]] || continue

      # Filter out internal labels
      local skip=0
      for lbl in "${INTERNAL_LABELS[@]}"; do
        [[ "$label" == "$lbl" ]] && skip=1 && break
      done
      [[ "$skip" -eq 1 ]] && continue

      # Filter out internal mount points
      is_internal "$mountpoint" && continue

      if mountpoint -q "$mountpoint" 2>/dev/null; then
        target="$mountpoint"
        break
      fi
    done < <(lsblk -J -o NAME,LABEL,MOUNTPOINT,HOTPLUG,RM,TYPE 2>/dev/null | \
      python3 -c "
import sys, json
data = json.load(sys.stdin)
def flatten(devs):
    for d in devs:
        yield d
        for c in d.get('children', []):
            yield from flatten([c])
for d in flatten(data.get('blockdevices', [])):
    print('\t'.join([
        d.get('type') or '',
        str(d.get('hotplug') or '0'),
        str(d.get('rm') or '0'),
        d.get('label') or '',
        d.get('mountpoint') or '',
    ]))
" 2>/dev/null || true)
  fi

  # Fallback: walk /run/media/ if lsblk produced nothing
  if [[ -z "$target" && -d "$MEDIA_ROOT" ]]; then
    while IFS= read -r -d '' mnt; do
      is_internal "$mnt" && continue
      # Check label via lsblk on the device backing this mount
      local dev
      dev=$(findmnt -n -o SOURCE "$mnt" 2>/dev/null || true)
      if [[ -n "$dev" ]]; then
        local lbl
        lbl=$(lsblk -n -o LABEL "$dev" 2>/dev/null || true)
        local skip=0
        for internal_lbl in "${INTERNAL_LABELS[@]}"; do
          [[ "$lbl" == "$internal_lbl" ]] && skip=1 && break
        done
        [[ "$skip" -eq 1 ]] && continue
      fi
      if mountpoint -q "$mnt" 2>/dev/null; then
        target="$mnt"
        break
      fi
    done < <(find "$MEDIA_ROOT" -mindepth 2 -maxdepth 2 -type d -print0 2>/dev/null)
  fi

  echo "$target"
}

# ── Detect the configured system role ───────────────────────────
#
# Priority:
#   1. Hub config JSON  (/var/lib/sovran-hub/config.json)  — "role" key
#   2. role-state.nix   (/etc/nixos/role-state.nix)        — grep for true flag
#   3. Default: server_plus_desktop

detect_role() {
  local role="server_plus_desktop"

  # 1. Try the Hub config JSON
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

  # 2. Fall back to parsing role-state.nix
  if [[ -f "$ROLE_STATE_NIX" ]]; then
    if grep -q 'roles\.desktop = lib\.mkDefault true' "$ROLE_STATE_NIX" 2>/dev/null; then
      role="desktop"
    elif grep -q 'roles\.node = lib\.mkDefault true' "$ROLE_STATE_NIX" 2>/dev/null; then
      role="node"
    fi
  fi

  echo "$role"
}

# ── Initialise log file ──────────────────────────────────────────

: > "$BACKUP_LOG"
set_status "RUNNING"

log "=== Sovran_SystemsOS External Hub Backup ==="
log "Starting backup process…"

# ── Detect system role ───────────────────────────────────────────

ROLE="$(detect_role)"
case "$ROLE" in
  desktop)            ROLE_LABEL="Desktop Only" ;;
  node)               ROLE_LABEL="Node (Bitcoin-only)" ;;
  server_plus_desktop) ROLE_LABEL="Server + Desktop" ;;
  *)                  ROLE_LABEL="$ROLE" ;;
esac
log "Detected role: $ROLE_LABEL"

# ── Detect target drive ──────────────────────────────────────────

if [[ -n "${BACKUP_TARGET:-}" ]]; then
  TARGET="$BACKUP_TARGET"
  # Safety: never allow internal drives even if explicitly passed
  if is_internal "$TARGET"; then
    fail "Target '$TARGET' is an internal system drive and cannot be used for external backup."
  fi
  log "Using specified backup target: $TARGET"
else
  log "Auto-detecting external USB drives…"
  TARGET="$(find_external_drive)"
  if [[ -z "$TARGET" ]]; then
    fail "No external USB drive detected. " \
         "Please plug in an exFAT-formatted USB drive (≥500 GB) and try again."
  fi
  log "Detected external drive: $TARGET"
fi

# ── Verify mount point ───────────────────────────────────────────

[[ -d "$TARGET" ]] || fail "Target path '$TARGET' does not exist."
mountpoint -q "$TARGET" || fail "Target path '$TARGET' is not a mount point."

# ── Check free disk space (require ≥ 10 GB) ──────────────────────

FREE_KB=$(df -k --output=avail "$TARGET" | tail -1)
FREE_GB=$(( FREE_KB / 1024 / 1024 ))
log "Free space on drive: ${FREE_GB} GB"
(( FREE_GB >= MIN_FREE_GB )) || \
  fail "Not enough free space on drive (${FREE_GB} GB available, ${MIN_FREE_GB} GB required)."

# ── Create timestamped backup directory ─────────────────────────

TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
BACKUP_DIR="${TARGET}/Sovran_SystemsOS_Backup/${TIMESTAMP}"
mkdir -p "$BACKUP_DIR"
log "Backup destination: $BACKUP_DIR"

# ── Stage 1/4: NixOS configuration ──────────────────────────────

log ""
log "── Stage 1/4: NixOS configuration (/etc/nixos) ──────────────"
if [[ -d /etc/nixos ]]; then
  rsync -a --info=progress2 /etc/nixos/ "$BACKUP_DIR/nixos/" 2>&1 | tee -a "$BACKUP_LOG" || \
    fail "Stage 1 failed while copying /etc/nixos"
  log "Stage 1 complete."
else
  log "WARNING: /etc/nixos not found — skipping."
fi

# ── Stage 2/4: Secrets ──────────────────────────────────────────

log ""
log "── Stage 2/4: Secrets ───────────────────────────────────────"
mkdir -p "$BACKUP_DIR/secrets"

if [[ "$ROLE" == "desktop" ]]; then
  log "Skipping /etc/nix-bitcoin-secrets — not applicable for Desktop Only role."
else
  if [[ -e /etc/nix-bitcoin-secrets ]]; then
    rsync -a --info=progress2 /etc/nix-bitcoin-secrets "$BACKUP_DIR/secrets/" 2>&1 | tee -a "$BACKUP_LOG" || \
      log "WARNING: Could not copy /etc/nix-bitcoin-secrets — continuing."
  else
    log "  (not found: /etc/nix-bitcoin-secrets — skipping)"
  fi
fi

log "Stage 2 complete."

# ── Stage 3/4: Home directory ────────────────────────────────────

log ""
log "── Stage 3/4: Home directory (/home) ───────────────────────"
if [[ -d /home ]]; then
  rsync -a --info=progress2 \
    --exclude='.cache/' \
    --exclude='.local/share/Trash/' \
    --exclude='*/Trash/' \
    /home/ "$BACKUP_DIR/home/" 2>&1 | tee -a "$BACKUP_LOG" || \
    fail "Stage 3 failed while copying /home"
  log "Stage 3 complete."
else
  log "WARNING: /home not found — skipping."
fi

# ── Stage 4/4: System data ───────────────────────────────────────

log ""
log "── Stage 4/4: System data (/var/lib) ────────────────────────"
if [[ "$ROLE" == "desktop" ]]; then
  if [[ -d /var/lib ]]; then
    rsync -a --info=progress2 \
      --filter='- /lnd/***' \
      --exclude='logs/' \
      --exclude='log/' \
      --exclude='*/logs/' \
      --exclude='*/log/' \
      /var/lib/ "$BACKUP_DIR/var-lib/" 2>&1 | tee -a "$BACKUP_LOG" || \
      fail "Stage 4 failed while copying /var/lib for Desktop Only role"
    log "Stage 4 complete (Desktop Only role excludes /var/lib/lnd)."
  else
    log "WARNING: /var/lib not found — skipping."
  fi
elif [[ -d /var/lib ]]; then
  rsync -a --info=progress2 \
    --exclude='logs/' \
    --exclude='log/' \
    --exclude='*/logs/' \
    --exclude='*/log/' \
    /var/lib/ "$BACKUP_DIR/var-lib/" 2>&1 | tee -a "$BACKUP_LOG" || \
    fail "Stage 4 failed while copying /var/lib"
  log "Stage 4 complete."
else
  log "WARNING: /var/lib not found — skipping."
fi

# ── Generate manifest ────────────────────────────────────────────

log ""
log "Generating BACKUP_MANIFEST.txt …"
{
  echo "Sovran_SystemsOS Backup Manifest"
  echo "Generated: $(date)"
  echo "Hostname:  $(hostname)"
  echo "Role:      $ROLE_LABEL"
  echo "Target:    $TARGET"
  echo ""
  echo "Contents:"
  find "$BACKUP_DIR" -mindepth 1 -maxdepth 2 | sort
} > "$BACKUP_DIR/BACKUP_MANIFEST.txt"
log "Manifest written to $BACKUP_DIR/BACKUP_MANIFEST.txt"

# ── Done ─────────────────────────────────────────────────────────

log ""
log "All Finished! Your data is now backed up to a third location."
log "Please eject the drive safely before removing it from your Sovran Pro."
set_status "SUCCESS"
