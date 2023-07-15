#!/usr/bin/env bash

### First make sure USB Flash Drive has latest NixOS image

### Then plug in power and ether cord to new blank Sovran Pro and then plug in USB Flash Drive with the NixOS installer image; then turn on.

### Second once booted into the installer image type:
 
 ### "sudo su"
 ### "passwd"
 ### then type "a"
 ### then "ip a" 


#### Third - GO TO LAPTOP and send script to the HOUSE-SOVRANPRO...

	### rsync -avP -e "ssh -i ~/.ssh/sovransystems" /home/free/Documents/Sovran\ Systems/Sovran\ Pro\ Scripts/Step_2_pspv2 root@172.88.122.161:/home/free/Documents/New_Install_Scripts


#### Fourth - FROM LAPTOP LOGIN to the HOUSE-SOVRANPRO transfer this script to The New Sovran Pro...
	
	### Open terminal Log into the HOUSE-SOVRANPRO

	### ssh -i ~/.ssh/sovransystems root@172.88.122.161

	### NOW WHILE LOGGED INTO HOUSE-SOVRANPRO type...
	
	### rsync -avP -e ssh /home/free/Documents/New_Install_Scripts/Step_2_psp root@192.168.0.?:/root


## Then log in with ssh root@192.168.1.[whatever is the ip of the New Sovran Pro]

## Then run bash Step_2_psp

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
	];

	services.openssh = {
		enable = true;
		permitRootLogin = "yes";
		};
}

EOT

nixos-install

reboot

#### After reboot from Laptop WHILE LOGGED INTO The TestSovranPro

	### rsync -avP -e ssh /root/.ssh/authorized_keys root@192.168.[whatever is the ip of the New Sovran Pro]:/root/

### Then type login into the New Sovran Pro to send the sp script: 
	
	### "ssh root@192.168.1.[whatever the ip is]"  
	### then password is "a"
	### then wget command...
	### "wget https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/sp"

#### Then type:

	### "bash sp" (which the script "sp" is Step 3)
