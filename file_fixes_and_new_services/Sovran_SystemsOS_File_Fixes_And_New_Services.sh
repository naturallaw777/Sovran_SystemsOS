#!/usr/bin/env bash

set -ex

cd /home/free/Downloads

wget "https://git.sovransystems.com/Sovran_Systems/test.sh"

bash /home/free/Downloads/test.sh

rm -rf /home/free/Downloads/test.sh

exit 0 