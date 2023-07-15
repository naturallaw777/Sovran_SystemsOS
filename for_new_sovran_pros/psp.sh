#!/usr/bin/env bash

GREEN="\e[32m"
LIGHTBLUE="\e[94m"
ENDCOLOR="\e[0m"

lsblk

echo -e "${GREEN}What block for Root drive (usually sda)?${ENDCOLOR}";read commitroot

parted /dev/"$commitroot" -- mklabel gpt
parted /dev/"$commitroot" -- mkpart primary 512MB -7MB
parted /dev/"$commitroot" -- mkpart ESP fat32 1MB 512MB
parted /dev/"$commitroot" -- set 2 esp on

lsblk

echo -e "${GREEN}What partition for Root drive (usually sda1)?${ENDCOLOR}";read commitrootpartition

echo -e "${GREEN}What partition for Boot drive (usually sda2)?${ENDCOLOR}";read commitbootpartition

mkfs.ext4 -L nixos /dev/"$commitrootpartition"

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

  nix = {
  package = pkgs.nixUnstable;
	extraOptions = ''
		experimental-features = nix-command flakes
	'';
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