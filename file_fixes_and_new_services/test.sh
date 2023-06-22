#!/usr/bin/env bash
   
exec 3>&1 4>&2
trap 'exec 2>&4 1>&3' 0 1 2 3
exec 1> /var/lib/beacons/awesome.log 2>&1

#### CHECK TO SEE IF IT HAS BEEN RUN BEFORE ####

FILE=/var/lib/beacons/file_fixes_and_new_services/jitsi/started

   if [ -e $FILE ]; then

      /run/current-system/sw/bin/echo "File Found, No Need to Run ... exiting"
         
      exit 1

   fi


#### CREATE INITIAL TAG ####

/run/current-system/sw/bin/mkdir -p /var/lib/beacons/file_fixes_and_new_services/jitsi ; touch /var/lib/beacons/file_fixes_and_new_services/jitsi/started

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Create Initial Tag"

      exit 1

   fi


#### MAIN SCRIPT ####

/run/current-system/sw/bin/mkdir /var/lib/cool

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Create Cool"

      exit 1

   fi



#### CREATE COMPELETE TAG ####

/run/current-system/sw/bin/touch /var/lib/beacons/file_fixes_and_new_services/jitsi/completed

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Create Completed Tag"

      exit 1

   fi

      
exit 0