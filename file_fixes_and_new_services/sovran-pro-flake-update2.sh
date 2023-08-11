#!/usr/bin/env bash
   
function log_console () {
  echo "`date` :: $1" >> /var/lib/beacons/awesome.log
  echo $1
}


#### CHECK TO SEE IF IT HAS BEEN RUN BEFORE ####

FILE=/var/lib/beacons/file_fixes_and_new_services/sovran-pro-flake-update2/completed

   if [ -e $FILE ]; then

      /run/current-system/sw/bin/echo "File Found :), No Need to Run ... Exiting"
         
      exit 1

   fi


#### CREATE INITIAL TAG ####

/run/current-system/sw/bin/mkdir -p /var/lib/beacons/file_fixes_and_new_services/sovran-pro-flake-update2 ; touch /var/lib/beacons/file_fixes_and_new_services/sovran-pro-flake-update2/started

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Create Initial Tag"

      exit 1

   fi


#### MAIN SCRIPT ####

/run/current-system/sw/bin/rm /etc/nixos/flake.nix

/run/current-system/sw/bin/cat > /etc/nixos/flake.nix <<- "EOF"

{
   description = "Sovran_SystemsOS for the Sovran Pro from Sovran Systems";

   inputs = {
      
      Sovran_Systems.url = "git+https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS";
   
   };

   outputs = { self, Sovran_Systems, ... }@inputs: {
      
      nixosConfigurations."nixos" = Sovran_Systems.inputs.nixpkgs.lib.nixosSystem {
         
         system = "x86_64-linux";
         
         modules = [ 

            ./custom.nix  

            ./hardware-configuration.nix

            Sovran_Systems.nixosModules.Sovran_SystemsOS 

         ];
      
      };
   
   };

}

EOF


   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Run sovran-pro-flake-update2"

      exit 1

   fi



#### CREATE COMPELETE TAG ####

/run/current-system/sw/bin/touch /var/lib/beacons/file_fixes_and_new_services/sovran-pro-flake-update2/completed

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Create Completed Tag"

      exit 1

   fi

      
exit 0