#!/usr/bin/env bash

# Begin: curl https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/psp.sh -o psp.sh

GREEN="\e[32m"
LIGHTBLUE="\e[94m"
ENDCOLOR="\e[0m"

lsblk

echo -e "${GREEN}What block for file-tree-root of drive (usually nvme0n1)?${ENDCOLOR}";read commitroot

parted /dev/"$commitroot" -- mklabel gpt
parted /dev/"$commitroot" -- mkpart primary 512MB -16GB
parted /dev/"$commitroot" -- mkpart swap linux-swap -16GB 100%
parted /dev/"$commitroot" -- mkpart ESP fat32 1MB 512MB
parted /dev/"$commitroot" -- set 3 esp on

lsblk

echo -e "${GREEN}What partition for Boot-Partition (usually nvme0n1p1)?${ENDCOLOR}";read commitbootpartition

echo -e "${GREEN}What partition for Main-Partition (usually nvme0n1p2)?${ENDCOLOR}";read commitmainpartition

echo -e "${GREEN}What partition for Swap-Partition (usually nvme0n1p3)?${ENDCOLOR}";read commitswappartition



mkfs.ext4 -L nixos /dev/"$commitmainpartition"

mkswap -L swap /dev/"$commitswappartition"

mkfs.fat -F 32 -n boot /dev/"$commitbootpartition"

mount /dev/disk/by-label/nixos /mnt

mkdir -p /mnt/boot/efi                   

mount /dev/disk/by-label/boot /mnt/boot/efi



nixos-generate-config --root /mnt

rm /mnt/etc/nixos/configuration.nix

cat <<EOT >> /mnt/etc/nixos/configuration.nix         
{ config, pkgs, ... }: {
  
  imports = [
	
	./hardware-configuration.nix
  
  ];

  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;
	boot.loader.efi.efiSysMountPoint = "/boot/efi";

	nix.settings.experimental-features = [ "nix-command" "flakes" ];

	users.users = {
		free = {
			isNormalUser = true;
			description = "free";
			extraGroups = [ "networkmanager" ];
		};
	};

	environment.systemPackages = with pkgs; [
		wget
		git
		ranger
		fish
		pwgen
		openssl
	];

	services.openssh = {
		enable = true;
		permitRootLogin = "yes";
	};
}

EOT

nixos-install

reboot