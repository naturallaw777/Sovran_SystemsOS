#!/usr/bin/env bash
set -euo pipefail

LOG=/tmp/sovran-install.log
exec > >(tee -a "$LOG") 2>&1

export PATH=/run/current-system/sw/bin:$PATH

# Changed to 2TB cutoff
BYTES_2TB=$((2 * 1024 * 1024 * 1024 * 1024))
LOGO="/etc/sovran/logo.png"

human_size() {
  numfmt --to=iec --suffix=B "$1"
}

zenity --info --window-icon="$LOGO" --text="Sovran SystemsOS Installer\n\nWARNING:\nThis installer will ERASE ALL DATA on selected disks.\n\nPress OK to continue."

# Filter out USB drives and loop/cdrom devices so it doesn't try to install to the installation media
mapfile -t DISKS < <(lsblk -b -dno NAME,SIZE,TYPE,RO,TRAN -e 7,11 | awk '$3=="disk" && $4=="0" && $5!="usb" {print $1":"$2}')

if [ "${#DISKS[@]}" -eq 0 ]; then
  zenity --error --window-icon="$LOGO" --text="No valid internal drives found. (USB drives are ignored)"
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

# Updated to check against 2TB
if [ -n "$DATA_DISK" ] && [ "$DATA_SIZE" -lt "$BYTES_2TB" ]; then
  zenity --warning --window-icon="$LOGO" --text="Second disk detected (${DATA_DISK}), but it is smaller than 2TB.\n\nIt will NOT be used."
  DATA_DISK=""
  DATA_SIZE=""
fi

SUMMARY="Boot disk: /dev/${BOOT_DISK} ($(human_size "$BOOT_SIZE"))"
if [ -n "$DATA_DISK" ]; then
  SUMMARY="${SUMMARY}\nData disk: /dev/${DATA_DISK} ($(human_size "$DATA_SIZE"))"
else
  SUMMARY="${SUMMARY}\nData disk: none"
fi

ROLE=$(zenity --list --radiolist \
  --window-icon="$LOGO" \
  --title="Choose Install Role" \
  --column="" --column="Role" \
  TRUE "Server-Desktop (default)" \
  FALSE "Desktop" \
  FALSE "Node (Bitcoin-only)" || true)

if [ -z "$ROLE" ]; then
  ROLE="Server-Desktop (default)"
fi

CONFIRM=$(zenity --entry --window-icon="$LOGO" --text="WARNING: This will ERASE ALL DATA on:\n\n${SUMMARY}\n\nType ERASE to continue.")
if [ "$CONFIRM" != "ERASE" ]; then
  zenity --error --window-icon="$LOGO" --text="Install cancelled."
  exit 1
fi

BOOT_PATH="/dev/${BOOT_DISK}"
DATA_PATH=""
if [ -n "$DATA_DISK" ]; then
  DATA_PATH="/dev/${DATA_DISK}"
fi

# Run Disko to partition and format drives
echo "Running Disko to partition and format drives..."
disko --mode disko /etc/sovran/flake/iso/disko.nix --argstr device "$BOOT_PATH" --argstr dataDevice "$DATA_PATH"

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

EOF

nixos-install --root /mnt --flake /mnt/etc/nixos#nixos

zenity --warning --width=600 --title="INSTALLATION COMPLETE! 🚨 PLEASE READ" --text="<b><span size='large'>Installation Successful!</span></b>

Before you reboot, please write down your main login details:

<b>Username:</b> free
<b>Password:</b> free

🚨 <b>CRITICAL:</b> Do not lose this password! If you forget this, you will be permanently locked out of your computer.

📁 <b>Other Passwords:</b> Once the system reboots, it will finish building your forts and generate all the passwords for your apps (Nextcloud, Bitcoin, Matrix, etc.). It will save them in a secure PDF in your <b>Documents</b> folder.

Click OK to reboot into your new system!"

reboot
