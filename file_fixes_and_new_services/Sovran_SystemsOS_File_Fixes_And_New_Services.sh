#!/usr/bin/env bash

set -ex

cd /home/free/Downloads

/run/current-system/sw/bin/wget "https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/file_fixes_and_new_services/test.sh"

/run/current-system/sw/bin/bash /home/free/Downloads/test.sh

rm -rf /home/free/Downloads/test.sh

rm -rf /home/free/Downloads/Sovran_SystemsOS_File_Fixes_And_New_Services.sh

exit 0 