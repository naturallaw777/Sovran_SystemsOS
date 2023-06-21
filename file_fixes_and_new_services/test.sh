#!/usr/bin/env bash
   
exec 1> /var/lib/beacons/awesome.log 2>&1
set -x


#### CHECK TO SEE IF IT HAS BEEN RUN BEFORE ####

FILE=/var/lib/beacons/file_fixes_and_new_services/jitsi/started

   if [ -e $FILE ]; then

      echo "File Found, No Need to Run ... exiting"
         
      exit 1

   fi


#### CREATE INITIAL TAG ####

mkdir -p /var/lib/beacons/file_fixes_and_new_services/jitsi ; touch /var/lib/beacons/file_fixes_and_new_services/jitsi/started

   if [[ $? != 0 ]]; then

      echo "Could Not Create Initial Tag"

      exit 1

   fi


#### MAIN SCRIPT ####

mkdir /var/lib/cool

   if [[ $? != 0 ]]; then

      echo "Could Not Create Cool"

      exit 1

   fi



#### CREATE COMPELETE TAG ####

touch /var/lib/beacons/file_fixes_and_new_services/jitsi/completed

   if [[ $? != 0 ]]; then

      echo "Could Not Create Completed Tag"

      exit 1

   fi

      
exit 0