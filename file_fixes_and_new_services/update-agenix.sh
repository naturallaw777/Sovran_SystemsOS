#!/usr/bin/env bash
   
#### CHECK TO SEE IF IT HAS BEEN RUN BEFORE ####

FILE=/var/lib/beacons/file_fixes_and_new_services/update-agenix/completed

   if [ -e $FILE ]; then

      /run/current-system/sw/bin/echo "File Found :), No Need to Run ... Exiting"
         
      exit 1

   fi


#### CREATE INITIAL TAG ####

/run/current-system/sw/bin/mkdir -p /var/lib/beacons/file_fixes_and_new_services/update-agenix ; touch /var/lib/beacons/file_fixes_and_new_services/update-agenix/started

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Create Initial Tag"

      exit 1

   fi


#### MAIN SCRIPT ####

/run/current-system/sw/bin/rm -rf /var/lib/agenix-secrets/nextclouddb.age

/run/current-system/sw/bin/rm -rf /var/lib/agenix-secrets/wordpressdb.age

/run/current-system/sw/bin/rm -rf /var/lib/agenix-secrets/turn.age

/run/current-system/sw/bin/rm -rf /var/lib/agenix-secrets/matrixdb.age 

/run/current-system/sw/bin/rm -rf /var/lib/agenix-secrets/matrix_reg_secret.age 


pushd /var/lib/agenix-secrets/

		
	/run/current-system/sw/bin/echo -n $(/run/current-system/sw/bin/cat /var/lib/secrets/wordpressdb) | /EDITOR='/run/current-system/sw/bin/cp /dev/stdin' run/current-system/sw/bin/nix run github:ryantm/agenix -- -e wordpressdb.age -i /root/.ssh/agenix/agenix-secret-keys

	/run/current-system/sw/bin/echo -n $(/run/current-system/sw/bin/cat /var/lib/secrets/nextclouddb) | EDITOR='/run/current-system/sw/bin/cp /dev/stdin' /run/current-system/sw/bin/nix run github:ryantm/agenix -- -e nextclouddb.age -i /root/.ssh/agenix/agenix-secret-keys

	/run/current-system/sw/bin/echo -n $(/run/current-system/sw/bin/cat /var/lib/secrets/matrixdb) | EDITOR='/run/current-system/sw/bin/cp /dev/stdin' /run/current-system/sw/bin/nix run github:ryantm/agenix -- -e matrixdb.age -i /root/.ssh/agenix/agenix-secret-keys

	/run/current-system/sw/bin/echo -n $(/run/current-system/sw/bin/cat /var/lib/secrets/turn) | EDITOR='/run/current-system/sw/bin/cp /dev/stdin' /run/current-system/sw/bin/nix run github:ryantm/agenix -- -e turn.age -i /root/.ssh/agenix/agenix-secret-keys

	/run/current-system/sw/bin/echo -n $(/run/current-system/sw/bin/cat /var/lib/secrets/matrix_reg_secret) | EDITOR='/run/current-system/sw/bin/cp /dev/stdin' /run/current-system/sw/bin/nix run github:ryantm/agenix -- -e matrix_reg_secret.age -i /root/.ssh/agenix/agenix-secret-keys


popd


   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Run update-agenix"

      exit 1

   fi



#### CREATE COMPELETE TAG ####

/run/current-system/sw/bin/touch /var/lib/beacons/file_fixes_and_new_services/update-agenix/completed

   if [[ $? != 0 ]]; then

      /run/current-system/sw/bin/echo "Could Not Create Completed Tag"

      exit 1

   fi

      
exit 0

