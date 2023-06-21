#!/usr/bin/env bash

set -ex

cd /home/free/Downloads

wget "https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/file_fixes_and_new_services/test.sh"

bash /home/free/Downloads/test.sh

rm -rf /home/free/Downloads/test.sh

exit 0 