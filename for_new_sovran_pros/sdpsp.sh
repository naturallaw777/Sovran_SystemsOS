#!/usr/bin/env bash

GREEN="\e[32m"
LIGHTBLUE="\e[94m"
ENDCOLOR="\e[0m"

lsblk

echo -e "${GREEN}What block for New Sovran Pro Second drive?${ENDCOLOR}";read commitroot

parted /dev/"$commitroot" -- mklabel gpt
parted /dev/"$commitroot" -- mkpart primary 0% 100%

lsblk

echo -e "${GREEN}What partition with New Sovran Pro Second Drive?${ENDCOLOR}";read commitsecond

mkfs.ext4 -L "BTCEcoandBackup" /dev/"$commitsecond"

sudo mkdir -p /mnt

mount /dev/"$commitsecond" /mnt

sudo mkdir -p /mnt/BTCEcoandBackup/Bitcoin_Node

sudo mkdir -p /mnt/BTCEcoandBackup/Electrs_Data

sudo mkdir -p /mnt/BTCEcoandBackup/NixOS_Snapshot_Backup

sudo mkdir -p /mnt/BTCEcoandBackup/clightning_db_Backup

sudo systemctl stop bitcoind electrs nbxplorer btcpayserver lnd rtl lightning-loop lightning-pool

rsync -ar --info=progress2 --info=name0 /run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node/ /mnt/BTCEcoandBackup/Bitcoin_Node/

rsync -ar --info=progress2 --info=name0 /run/media/Second_Drive/BTCEcoandBackup/Electrs_Data/ /mnt/BTCEcoandBackup/Electrs_Data/

sudo systemctl start bitcoind electrs nbxplorer btcpayserver lnd rtl lightning-loop lightning-pool

sudo chown bitcoin:bitcoin /mnt/BTCEcoandBackup/Bitcoin_Node -R

sudo chown electrs:electrs /mnt/BTCEcoandBackup/Electrs_Data -R

sudo chmod 770 /mnt/BTCEcoandBackup/Bitcoin_Node -R

sudo chmod 770 /mnt/BTCEcoandBackup/Electrs_Data -R

sudo umount /dev/"$commitsecond"

echo -e "All Finished!"

