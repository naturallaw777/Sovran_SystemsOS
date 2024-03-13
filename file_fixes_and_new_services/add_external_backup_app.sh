#!/usr/bin/env bash
   
function log_console () {
  echo "`date` :: $1" >> /var/lib/beacons/awesome.log
  echo $1
}


#### CHECK TO SEE IF IT HAS BEEN RUN BEFORE ####

FILE=/var/lib/beacons/file_fixes_and_new_services/add_external_backup_app/completed

   if [ -e $FILE ]; then

      /run/current-system/sw/bin/echo "File Found :), No Need to Run ... Exiting"
         
      exit 1

   fi


#### CREATE INITIAL TAG ####

/run/current-system/sw/bin/mkdir -p /var/lib/beacons/file_fixes_and_new_services/add_external_backup_app ; touch /var/lib/beacons/file_fixes_and_new_services/add_external_backup_app/started

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Create Initial Tag"

      exit 1

   fi


#### MAIN SCRIPT ####

cd /home/free/Downloads

/run/current-system/sw/bin/wget "https://git.sovransystems.com/Sovran_Systems/Software/raw/branch/main/Sovran_SystemsOS_External_Backup/sovran_systemsOS_external_backup_local_installer/sovran_systemsOS_external_backup_install.sh"

/run/current-system/sw/bin/bash "sovran_systemsOS_external_backup_install.sh"

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Run add_external_backup_app"

      exit 1

   fi



#### CREATE COMPELETE TAG ####

/run/current-system/sw/bin/touch /var/lib/beacons/file_fixes_and_new_services/add_external_backup_app/completed

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Create Completed Tag"

      exit 1

   fi

      
exit 0