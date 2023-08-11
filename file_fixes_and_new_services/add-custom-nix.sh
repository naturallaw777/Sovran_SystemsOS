#!/usr/bin/env bash
   
function log_console () {
  echo "`date` :: $1" >> /var/lib/beacons/awesome.log
  echo $1
}


#### CHECK TO SEE IF IT HAS BEEN RUN BEFORE ####

FILE=/var/lib/beacons/file_fixes_and_new_services/add-custom-nix/completed

   if [ -e $FILE ]; then

      /run/current-system/sw/bin/echo "File Found :), No Need to Run ... Exiting"
         
      exit 1

   fi


#### CREATE INITIAL TAG ####

/run/current-system/sw/bin/mkdir -p /var/lib/beacons/file_fixes_and_new_services/add-custom-nix ; touch /var/lib/beacons/file_fixes_and_new_services/add-custom-nix/started

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Create Initial Tag"

      exit 1

   fi


#### MAIN SCRIPT ####

/run/current-system/sw/bin/mkdir /etc/nixos/custom.nix

/run/current-system/sw/bin/cat > /etc/nixos/custom.nix <<- "EOF"

{config, pkgs, lib, ...}:

/*
Add custom NixOS modules here.
/*
let
   personalization = import ./personalization.nix;
   
   in
{



}

*\

EOF


   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Run add-custom-nix"

      exit 1

   fi



#### CREATE COMPELETE TAG ####

/run/current-system/sw/bin/touch /var/lib/beacons/file_fixes_and_new_services/add-custom-nix/completed

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Create Completed Tag"

      exit 1

   fi

      
exit 0