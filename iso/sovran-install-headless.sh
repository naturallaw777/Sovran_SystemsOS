#!/usr/bin/env bash
# sovran-install-headless.sh — Non-interactive remote installer for Sovran_SystemsOS

usage() {
    cat <<'USAGE'
Usage: sovran-install-headless.sh [OPTIONS]

Options:
  --disk /dev/sda              Target OS disk (required)
  --data-disk /dev/sdb         Data disk for Bitcoin (optional)
  --role server|desktop|node   Installation role (default: server)
  --deploy-key "ssh-ed25519 AAAA..."  SSH pubkey for remote access after install
  --relay-host HOST            Reverse tunnel relay hostname
  --relay-user USER            Relay username (default: deploy)
  --relay-port PORT            Relay SSH port (default: 22)
  --tunnel-port PORT           Reverse tunnel port on relay (default: 2222)
  --headscale-server URL       Headscale login server for post-install Tailnet
  --headscale-key KEY          Headscale pre-auth key for the installed OS
USAGE
}

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
DISK=""
DATA_DISK=""
ROLE="server"
DEPLOY_KEY=""
RELAY_HOST=""
RELAY_USER="deploy"
RELAY_PORT="22"
TUNNEL_PORT="2222"
HEADSCALE_SERVER=""
HEADSCALE_KEY=""

FLAKE="/etc/sovran/flake"
LOG="/tmp/sovran-headless-install.log"

BYTES_256GB=$((256 * 1024 * 1024 * 1024))
BYTES_2TB=$((2 * 1000 * 1000 * 1000 * 1000))

# ── Logging ───────────────────────────────────────────────────────────────────
exec > >(tee -a "$LOG") 2>&1

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
    log "ERROR: $*"
    exit 1
}

# ── Argument parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --disk)        DISK="$2";        shift 2 ;;
        --data-disk)   DATA_DISK="$2";   shift 2 ;;
        --role)        ROLE="$2";        shift 2 ;;
        --deploy-key)  DEPLOY_KEY="$2";  shift 2 ;;
        --relay-host)  RELAY_HOST="$2";  shift 2 ;;
        --relay-user)  RELAY_USER="$2";  shift 2 ;;
        --relay-port)  RELAY_PORT="$2";  shift 2 ;;
        --tunnel-port) TUNNEL_PORT="$2"; shift 2 ;;
        --headscale-server) HEADSCALE_SERVER="$2"; shift 2 ;;
        --headscale-key)    HEADSCALE_KEY="$2";    shift 2 ;;
        -h|--help)
            usage
            exit 0
            ;;
        *) die "Unknown argument: $1" ;;
    esac
done

# ── Validate required arguments ───────────────────────────────────────────────
[[ -n "$DISK" ]] || die "--disk is required"

case "$ROLE" in
    server|desktop|node) ;;
    *) die "--role must be one of: server, desktop, node" ;;
esac

# ── Validate disk existence and size ─────────────────────────────────────────
log "=== Validating disks ==="

[[ -b "$DISK" ]] || die "OS disk not found: $DISK"

disk_size_bytes() {
    local dev="$1"
    lsblk -b -dno SIZE "$dev" 2>/dev/null || echo 0
}

OS_SIZE=$(disk_size_bytes "$DISK")
log "OS disk $DISK: $OS_SIZE bytes"
[[ "$OS_SIZE" -ge "$BYTES_256GB" ]] \
    || die "OS disk $DISK is too small ($(( OS_SIZE / 1024 / 1024 / 1024 )) GB). Minimum is 256 GB."

if [[ -n "$DATA_DISK" ]]; then
    [[ -b "$DATA_DISK" ]] || die "Data disk not found: $DATA_DISK"
    [[ "$DATA_DISK" != "$DISK" ]] || die "OS disk and data disk cannot be the same device"
    DATA_SIZE=$(disk_size_bytes "$DATA_DISK")
    log "Data disk $DATA_DISK: $DATA_SIZE bytes"
    [[ "$DATA_SIZE" -ge "$BYTES_2TB" ]] \
        || die "Data disk $DATA_DISK is too small ($(( DATA_SIZE / 1024 / 1024 / 1024 )) GB). Minimum is 2 TB."
fi

# ── Helper: partition suffix ──────────────────────────────────────────────────
part_suffix() {
    local dev="$1" n="$2"
    if [[ "$dev" == *nvme* ]]; then
        echo "${dev}p${n}"
    else
        echo "${dev}${n}"
    fi
}

# ── Step 1: Wipe disks ────────────────────────────────────────────────────────
log "=== Wiping disk(s) ==="

sgdisk --zap-all "$DISK"
wipefs --all --force "$DISK"

if [[ -n "$DATA_DISK" ]]; then
    sgdisk --zap-all "$DATA_DISK"
    wipefs --all --force "$DATA_DISK"
fi

partprobe "$DISK"
[[ -n "$DATA_DISK" ]] && partprobe "$DATA_DISK"
sleep 2

# ── Step 2: Partition OS disk ─────────────────────────────────────────────────
log "=== Partitioning OS disk ==="

sgdisk \
    -n "1:1M:+512M" -t "1:EF00" -c "1:ESP" \
    -n "2:0:0"      -t "2:8300" -c "2:root" \
    "$DISK"

partprobe "$DISK"
sleep 2

# ── Step 3: Partition data disk (if present) ──────────────────────────────────
if [[ -n "$DATA_DISK" ]]; then
    log "=== Partitioning data disk ==="
    sgdisk \
        -n "1:1M:0" -t "1:8300" -c "1:primary" \
        "$DATA_DISK"
    partprobe "$DATA_DISK"
    sleep 2
fi

# ── Step 4: Format partitions ─────────────────────────────────────────────────
log "=== Formatting partitions ==="

BOOT_P1=$(part_suffix "$DISK" 1)
BOOT_P2=$(part_suffix "$DISK" 2)

mkfs.vfat -F 32 "$BOOT_P1"
mkfs.ext4 -F -L sovran_systemsos "$BOOT_P2"

if [[ -n "$DATA_DISK" ]]; then
    DATA_P1=$(part_suffix "$DATA_DISK" 1)
    mkfs.ext4 -F -L BTCEcoandBackup "$DATA_P1"
fi

# ── Step 5: Mount filesystems ─────────────────────────────────────────────────
log "=== Mounting filesystems ==="

mount "$BOOT_P2" /mnt
mkdir -p /mnt/boot/efi
mount -o umask=0077,defaults "$BOOT_P1" /mnt/boot/efi

if [[ -n "$DATA_DISK" ]]; then
    DATA_P1=$(part_suffix "$DATA_DISK" 1)
    mkdir -p /mnt/run/media/Second_Drive
    mount "$DATA_P1" /mnt/run/media/Second_Drive

    # ── Step 6: Create Bitcoin data directories ─────────────────────────────
    log "=== Creating Bitcoin data directories ==="
    mkdir -p /mnt/run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node
    mkdir -p /mnt/run/media/Second_Drive/BTCEcoandBackup/Electrs_Data
    mkdir -p /mnt/run/media/Second_Drive/BTCEcoandBackup/NixOS_Snapshot_Backup
fi

# ── Step 7: Generate hardware config ─────────────────────────────────────────
log "=== Generating hardware config ==="
nixos-generate-config --root /mnt

# ── Step 8: Copy flake source ─────────────────────────────────────────────────
log "=== Copying flake to /mnt ==="
cp /mnt/etc/nixos/hardware-configuration.nix /tmp/hardware-configuration.nix
rm -rf /mnt/etc/nixos/
mkdir -p /mnt/etc/nixos
cp -a "${FLAKE}/." /mnt/etc/nixos/
cp /tmp/hardware-configuration.nix /mnt/etc/nixos/hardware-configuration.nix

# ── Step 9: Write role-state.nix ─────────────────────────────────────────────
log "=== Writing role config ==="

case "$ROLE" in
    server)
        IS_SERVER=true; IS_DESKTOP=false; IS_NODE=false ;;
    desktop)
        IS_SERVER=false; IS_DESKTOP=true; IS_NODE=false ;;
    node)
        IS_SERVER=false; IS_DESKTOP=false; IS_NODE=true ;;
esac

cat > /mnt/etc/nixos/role-state.nix <<EOF
# THIS FILE IS AUTO-GENERATED BY THE INSTALLER. DO NOT EDIT.
{ config, lib, ... }:
{
  sovran_systemsOS.roles.server_plus_desktop = lib.mkDefault ${IS_SERVER};
  sovran_systemsOS.roles.desktop = lib.mkDefault ${IS_DESKTOP};
  sovran_systemsOS.roles.node = lib.mkDefault ${IS_NODE};
}
EOF

# ── Step 10: Write custom.nix with deploy config ──────────────────────────────
log "=== Writing custom.nix ==="

if [[ -n "$DEPLOY_KEY" ]]; then
    cat > /mnt/etc/nixos/custom.nix <<EOF
{ config, lib, ... }:
{
  sovran_systemsOS.deploy = {
    enable = true;
    authorizedKey = "${DEPLOY_KEY}";
    relayHost = "${RELAY_HOST}";
    relayUser = "${RELAY_USER}";
    relayPort = ${RELAY_PORT};
    reverseTunnelPort = ${TUNNEL_PORT};
$([ -n "${HEADSCALE_SERVER}" ] && echo "    headscaleServer = \"${HEADSCALE_SERVER}\";")
  };
}
EOF
else
    cp /mnt/etc/nixos/custom.template.nix /mnt/etc/nixos/custom.nix
fi

# ── Write Headscale auth key if provided ─────────────────────────────────────
if [[ -n "$HEADSCALE_KEY" ]]; then
    mkdir -p /mnt/var/lib/secrets
    echo "$HEADSCALE_KEY" > /mnt/var/lib/secrets/headscale-authkey
    chmod 600 /mnt/var/lib/secrets/headscale-authkey
    log "Headscale auth key written to /mnt/var/lib/secrets/headscale-authkey"
fi

# ── Step 11: Copy configs to host for flake evaluation ───────────────────────
log "=== Copying config files to host /etc/nixos for flake evaluation ==="
mkdir -p /etc/nixos
cp /mnt/etc/nixos/role-state.nix /etc/nixos/role-state.nix
cp /mnt/etc/nixos/custom.nix /etc/nixos/custom.nix
cp /mnt/etc/nixos/hardware-configuration.nix /etc/nixos/hardware-configuration.nix

# ── Step 12: Run nixos-install ────────────────────────────────────────────────
log "=== Running nixos-install ==="
nixos-install \
    --root /mnt \
    --flake /mnt/etc/nixos#nixos \
    --no-root-password \
    --impure

log "=== Installation complete! ==="
log "You can now reboot into Sovran_SystemsOS."
log "After reboot, the machine will be accessible via SSH on port 22 (if --deploy-key was provided)."
[[ -n "$RELAY_HOST" ]] && \
    log "Reverse tunnel will connect to ${RELAY_USER}@${RELAY_HOST}:${RELAY_PORT} — forward port ${TUNNEL_PORT} maps to the machine's SSH."
[[ -n "$HEADSCALE_SERVER" ]] && \
    log "Tailscale will connect to Headscale at ${HEADSCALE_SERVER} on first boot."
