#!/usr/bin/env bash

cd /home/free/Downloads



#### SCRIPT 1 ####

/run/current-system/sw/bin/wget "https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/file_fixes_and_new_services/sovran-pro-flake-update.sh"

/run/current-system/sw/bin/bash /home/free/Downloads/sovran-pro-flake-update.sh

rm -rf /home/free/Downloads/sovran-pro-flake-update.sh



#### SCRIPT 2 ####

/run/current-system/sw/bin/wget "https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/file_fixes_and_new_services/add-custom-nix.sh"

/run/current-system/sw/bin/bash /home/free/Downloads/add-custom-nix.sh

rm -rf /home/free/Downloads/add-custom.nix.sh


#### REMOVAL OF MAIN SCRIPT ####

rm -rf /home/free/Downloads/Sovran_SystemsOS_File_Fixes_And_New_Services.sh