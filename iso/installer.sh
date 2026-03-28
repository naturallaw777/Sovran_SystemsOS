#!/usr/bin/env bash
set -euo pipefail

LOG=/tmp/sovran-install.log
exec > >(tee -a "$LOG") 2>&1

export PATH=/run/current-system/sw/bin:$PATH

BYTES_4TB=$((4 * 1024 * 1024 * 1024 * 1024))

human_size() {
  numfmt --to=iec --suffix=B "$1"
}

zenity --info --width=500 --text="Sovran SystemsOS Installer\n\nWARNING:\nThis installer will ERASE ALL DATA on selected disks.\n\nPress OK to continue."

mapfile -t DISKS < <(lsblk -b -dno NAME,SIZE,TYPE | awk '$3=="disk"{print $1":"$2}')
if [ "${#DISKS[@]}" -eq 0 ]; then
  zenity --error --text="No disks found."
  exit 1
fi

IFS=$'\n' DISKS_SORTED=($(printf "%s\n" "${DISKS[@]}" | sort -t: -k2,2n))
unset IFS

BOOT_DISK="${DISKS_SORTED[0]%%:*}"
BOOT_SIZE="${DISKS_SORTED[0]##*:}"

DATA_DISK=""
DATA_SIZE=""

if [ "${#DISKS_SORTED[@]}" -ge 2 ]; then
  DATA_DISK="${DISKS_SORTED[-1]%%:*}"
  DATA_SIZE="${DISKS_SORTED[-1]##*:}"
fi

if [ -n "$DATA_DISK" ] && [ "$DATA_SIZE" -lt "$BYTES_4TB" ]; then
  zenity --warning --width=500 --text="Second disk detected (${DATA_DISK}), but it is smaller than 4TB.\n\nIt will NOT be used."
  DATA_DISK=""
  DATA_SIZE=""
fi

SUMMARY="Boot disk: /dev/${BOOT_DISK} ($(human_size "$BOOT_SIZE"))"
if [ -n "$DATA_DISK" ]; then
  SUMMARY="${SUMMARY}\nData disk: /dev/${DATA_DISK} ($(human_size "$DATA_SIZE"))"
else
  SUMMARY="${SUMMARY}\nData disk: none"
fi

ROLE=$(zenity --list --radiolist --width=500 --height=250 \
  --title="Choose Install Role" \
  --column="" --column="Role" \
  TRUE "Server-Desktop (default)" \
  FALSE "Desktop" \
  FALSE "Node (Bitcoin-only)" || true)

if [ -z "$ROLE" ]; then
  ROLE="Server-Desktop (default)"
fi

CONFIRM=$(zenity --entry --width=500 --text="WARNING: This will ERASE ALL DATA on:\n\n${SUMMARY}\n\nType ERASE to continue.")
if [ "$CONFIRM" != "ERASE" ]; then
  zenity --error --text="Install cancelled."
  exit 1
fi

BOOT_PATH="/dev/${BOOT_DISK}"
PART_SUFFIX=""
if [[ "$BOOT_DISK" =~ ^(nvme|mmcblk) ]]; then
  PART_SUFFIX="p"
fi

parted --script "$BOOT_PATH" mklabel gpt
parted --script "$BOOT_PATH" mkpart ESP fat32 1MiB 512MiB
parted --script "$BOOT_PATH" set 1 esp on
parted --script "$BOOT_PATH" mkpart primary ext4 512MiB 100%

partprobe "$BOOT_PATH"
udevadm settle

mkfs.fat -F 32 -n boot "${BOOT_PATH}${PART_SUFFIX}1"
mkfs.ext4 -F -L sovran_systemsos "${BOOT_PATH}${PART_SUFFIX}2"

if [ -n "$DATA_DISK" ]; then
  DATA_PATH="/dev/${DATA_DISK}"
  part_suffix_data=""
  if [[ "$DATA_DISK" =~ ^(nvme|mmcblk) ]]; then
    part_suffix_data="p"
  fi

  parted --script "$DATA_PATH" mklabel gpt
  parted --script "$DATA_PATH" mkpart primary ext4 1MiB 100%
  partprobe "$DATA_PATH"
  udevadm settle
  mkfs.ext4 -F -L BTCEcoandBackup "${DATA_PATH}${part_suffix_data}1"
fi

mkdir -p /mnt
mount /dev/disk/by-label/sovran_systemsos /mnt
mkdir -p /mnt/boot/efi
mount /dev/disk/by-label/boot /mnt/boot/efi

if [ -n "$DATA_DISK" ]; then
  mkdir -p /mnt/run/media/Second_Drive
  mount /dev/disk/by-label/BTCEcoandBackup /mnt/run/media/Second_Drive
fi

nixos-generate-config --root /mnt

cp /mnt/etc/nixos/hardware-configuration.nix /tmp/hardware-configuration.nix
rm -rf /mnt/etc/nixos/*
cp -a /etc/sovran/flake/* /mnt/etc/nixos/
cp /tmp/hardware-configuration.nix /mnt/etc/nixos/hardware-configuration.nix

cat > /mnt/etc/nixos/custom.nix <<EOF
{ config, lib, ... }:
{
  sovran_systemsOS.roles.server-desktop = ${ROLE == "Server-Desktop (default)"};
  sovran_systemsOS.roles.desktop = ${ROLE == "Desktop"};
  sovran_systemsOS.roles.node = ${ROLE == "Node (Bitcoin-only)"};
}
EOF

nixos-install --root /mnt --flake /mnt/etc/nixos#nixos

zenity --info --text="Install complete. Rebooting..."
reboot