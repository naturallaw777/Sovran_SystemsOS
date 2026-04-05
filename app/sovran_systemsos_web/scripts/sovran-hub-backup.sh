#!/usr/bin/env bash
# ── Sovran Hub Backup Script ─────────────────────────────────────
# Backs up Sovran_SystemsOS data to an external USB hard drive.
# Designed for the Hub web UI (no GUI dependencies).
#
# Usage:
#   BACKUP_TARGET=/run/media/<user>/<drive> bash sovran-hub-backup.sh
#   (or run with no env var to auto-detect the first external drive)

set -euo pipefail

BACKUP_LOG="/var/log/sovran-hub-backup.log"
BACKUP_STATUS="/var/log/sovran-hub-backup.status"
MEDIA_ROOT="/run/media"
MIN_FREE_GB=10

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

# ── Initialise log file ──────────────────────────────────────────

: > "$BACKUP_LOG"
set_status "RUNNING"

log "=== Sovran_SystemsOS Hub Backup ==="
log "Starting backup process…"

# ── Detect target drive ──────────────────────────────────────────

if [[ -n "${BACKUP_TARGET:-}" ]]; then
  TARGET="$BACKUP_TARGET"
  log "Using specified backup target: $TARGET"
else
  log "Auto-detecting external drives under $MEDIA_ROOT …"
  TARGET=""
  if [[ -d "$MEDIA_ROOT" ]]; then
    # Walk /run/media/<user>/<drive>
    while IFS= read -r -d '' mnt; do
      if mountpoint -q "$mnt" 2>/dev/null; then
        TARGET="$mnt"
        break
      fi
    done < <(find "$MEDIA_ROOT" -mindepth 2 -maxdepth 2 -type d -print0 2>/dev/null)
  fi
  if [[ -z "$TARGET" ]]; then
    fail "No external drive detected under $MEDIA_ROOT. " \
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

for SRC in /etc/nix-bitcoin-secrets /var/lib/domains; do
  if [[ -e "$SRC" ]]; then
    rsync -a --info=progress2 "$SRC" "$BACKUP_DIR/secrets/" 2>&1 | tee -a "$BACKUP_LOG" || \
      log "WARNING: Could not copy $SRC — continuing."
  else
    log "  (not found: $SRC — skipping)"
  fi
done

# Hub state files from /var/lib/secrets/
if [[ -d /var/lib/secrets ]]; then
  mkdir -p "$BACKUP_DIR/secrets/hub-state"
  rsync -a --info=progress2 /var/lib/secrets/ "$BACKUP_DIR/secrets/hub-state/" 2>&1 | tee -a "$BACKUP_LOG" || \
    log "WARNING: Could not copy /var/lib/secrets — continuing."
else
  log "  (not found: /var/lib/secrets — skipping)"
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

# ── Stage 4/4: Wallet and node data ─────────────────────────────

log ""
log "── Stage 4/4: Wallet and node data (/var/lib/lnd) ──────────"
if [[ -d /var/lib/lnd ]]; then
  rsync -a --info=progress2 \
    --exclude='logs/' \
    /var/lib/lnd/ "$BACKUP_DIR/lnd/" 2>&1 | tee -a "$BACKUP_LOG" || \
    fail "Stage 4 failed while copying /var/lib/lnd"
  log "Stage 4 complete."
else
  log "WARNING: /var/lib/lnd not found — skipping."
fi

# ── Generate manifest ────────────────────────────────────────────

log ""
log "Generating BACKUP_MANIFEST.txt …"
{
  echo "Sovran_SystemsOS Backup Manifest"
  echo "Generated: $(date)"
  echo "Hostname:  $(hostname)"
  echo "Target:    $TARGET"
  echo ""
  echo "Contents:"
  find "$BACKUP_DIR" -mindepth 1 -maxdepth 2 | sort
} > "$BACKUP_DIR/BACKUP_MANIFEST.txt"
log "Manifest written to $BACKUP_DIR/BACKUP_MANIFEST.txt"

# ── Done ─────────────────────────────────────────────────────────

log ""
log "All Finished! Please eject the drive before removing it from your Sovran Pro."
set_status "SUCCESS"
