#!/usr/bin/env bash

# wget https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/sp.sh


GREEN="\e[32m"
LIGHTBLUE="\e[94m"
ENDCOLOR="\e[0m"

#

pushd /etc/nixos/

  wget https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/flake.nix

  chown root:root /etc/nixos/ -R
  
  chmod 770 /etc/nixos/ -R

popd

#

mkdir /var/lib/domains

touch /var/lib/domains/btcpayserver
touch /var/lib/domains/matrix
touch /var/lib/domains/nextcloud
touch /var/lib/domains/sslemail
touch /var/lib/domains/vaultwarden
touch /var/lib/domains/wordpress

#

echo -e "${GREEN}What is your New Matrix (Element Chat) domain name?${ENDCOLOR}"
read 
echo -n $REPLY > /var/lib/domains/matrix

echo -e "${GREEN}What is your New Wordpress domain name?${ENDCOLOR}"
read 
echo -n $REPLY > /var/lib/domains/wordpress

echo -e "${GREEN}What is your New Nextcloud domain name?${ENDCOLOR}"
read 
echo -n $REPLY > /var/lib/domains/nextcloud

echo -e "${GREEN}What is your New BTCPayserver domain name?${ENDCOLOR}"
read 
echo -n $REPLY > /var/lib/domains/btcpayserver

echo -e "${GREEN}What is your New Vaultwarden domain name?${ENDCOLOR}"
read 
echo -n $REPLY > /var/lib/domains/vaultwarden

echo -e "${GREEN}What is the email you would like to use to manage the SSL certificates for your domains?${ENDCOLOR}"
read 
echo -n $REPLY > /var/lib/domains/sslemail

#

mkdir /var/lib/nextcloudaddition

cat > /var/lib/nextcloudaddition/nextcloudaddition <<- "EOF"


'trusted_proxies' => 
  array (
    0 => '127.0.0.1',
  ),
  'default_locale' => 'en_US',
  'default_phone_region' => 'US',
  'memcache.local' => '\\OC\\Memcache\\APCu',

EOF

#

mkdir /var/lib/njalla/

cat > /var/lib/njalla/njalla.sh <<- "EOF"

#!/usr/bin/env bash

IP=$(wget -qO- https://ipecho.net/plain ; echo)

## Manually Add DDNS Script From Njalla User Account AFTER Install

curl "https://...${IP}"

EOF

#

mkdir /var/lib/external_ip

cat > /var/lib/external_ip/external_ip.sh <<- "EOF"

#!/usr/bin/env bash

IP=$(wget -qO- https://ipecho.net/plain ; echo)

echo "${IP}" > /var/lib/secrets/external_ip

EOF

#

mkdir /var/lib/agenix-secrets/

cat > /var/lib/agenix-secrets/secrets.nix <<- "EOF"

let

  root = "placeholder" ;

in

{

  "wordpressdb.age".publicKeys = [ root ];
  
  "matrixdb.age".publicKeys = [ root ];

  "nextclouddb.age".publicKeys = [ root ];

  "turn.age".publicKeys = [ root ];

  "matrix_reg_secret.age".publicKeys = [ root ];

}

EOF

#

mkdir /var/lib/secrets
mkdir /var/lib/secrets/vaultwarden

touch /var/lib/secrets/nextclouddb
touch /var/lib/secrets/wordpressdb
touch /var/lib/secrets/matrixdb
touch /var/lib/secrets/turn
touch /var/lib/secrets/matrix_reg_secret
touch /var/lib/secrets/main
touch /var/lib/secrets/vaultwarden/vaultwarden.env
touch /var/lib/secrets/external_ip

echo -n $(pwgen -s 17 -1) > /var/lib/secrets/nextclouddb 
echo -n $(pwgen -s 17 -1) > /var/lib/secrets/wordpressdb 
echo -n $(pwgen -s 17 -1) > /var/lib/secrets/matrixdb
echo -n $(pwgen -s 17 -1) > /var/lib/secrets/turn
echo -n $(pwgen -s 17 -1) > /var/lib/secrets/matrix_reg_secret
echo -n $(pwgen -s 17 -1) > /var/lib/secrets/main
echo -n ADMIN_TOKEN=$(openssl rand -base64 48
) > /var/lib/secrets/vaultwarden/vaultwarden.env

#

mkdir -p /root/.ssh/agenix

ssh-keygen -q -N "" -t ed25519 -f /root/.ssh/agenix/agenix-secret-keys

sed -i -e "0,/root.*/{s::root = $(cat /root/.ssh/agenix/agenix-secret-keys.pub):};s:root@nixos::" /var/lib/agenix-secrets/secrets.nix

sed -i 's:\(root =[[:blank:]]*\)\(.*\):\1"\2";:' /var/lib/agenix-secrets/secrets.nix

#

pushd /var/lib/agenix-secrets

  echo -n $(cat /var/lib/secrets/wordpressdb) | EDITOR='cp /dev/stdin' nix run github:ryantm/agenix -- -e wordpressdb.age -i /root/.ssh/agenix/agenix-secret-keys

  echo -n $(cat /var/lib/secrets/nextclouddb) | EDITOR='cp /dev/stdin' nix run github:ryantm/agenix -- -e nextclouddb.age -i /root/.ssh/agenix/agenix-secret-keys

  echo -n $(cat /var/lib/secrets/matrixdb) | EDITOR='cp /dev/stdin' nix run github:ryantm/agenix -- -e matrixdb.age -i /root/.ssh/agenix/agenix-secret-keys

  echo -n $(cat /var/lib/secrets/turn) | EDITOR='cp /dev/stdin' nix run github:ryantm/agenix -- -e turn.age -i /root/.ssh/agenix/agenix-secret-keys

  echo -n $(cat /var/lib/secrets/matrix_reg_secret) | EDITOR='cp /dev/stdin' nix run github:ryantm/agenix -- -e matrix_reg_secret.age -i /root/.ssh/agenix/agenix-secret-keys

popd

#

pushd /etc/nixos

  nix flake update

  nixos-rebuild switch --impure

popd

#

chown root:root /var/lib/secrets/main -R

chown root:root /var/lib/secrets/external_ip -R

chown matrix-synapse:matrix-synapse /var/lib/secrets/matrix_reg_secret -R

chown matrix-synapse:matrix-synapse /var/lib/secrets/matrixdb -R

chown postgres:postgres /var/lib/secrets/nextclouddb -R

chown turnserver:turnserver /var/lib/secrets/turn -R

chown mysql:mysql /var/lib/secrets/wordpressdb -R

chown vaultwarden:vaultwarden /var/lib/secrets/vaultwarden -R


chmod 770 /var/lib/secrets/ -R

#

chown caddy:php /var/lib/domains -R

chmod 770 /var/lib/domains -R

#

pushd /etc/nixos

  nix flake update

  nixos-rebuild switch --impure

popd

#

set -x

wget -P /var/lib/www/downloadwp https://wordpress.org/latest.zip

wget -P /var/lib/www/downloadnc https://download.nextcloud.com/server/releases/latest.zip

unzip /var/lib/www/downloadwp/latest.zip -d /var/lib/www/

unzip /var/lib/www/downloadnc/latest.zip -d /var/lib/www/

rm -rf /var/lib/www/downloadwp

rm -rf /var/lib/www/downloadnc

chown caddy:php /var/lib/www -R

chmod 770 /var/lib/www -R

#

mkdir /var/lib/nextcloud

chown caddy:php /var/lib/nextcloud -R

chmod 770 /var/lib/nextcloud -R

#

mkdir /var/lib/coturn

chown turnserver:turnserver /var/lib/coturn -R

chmod 770 /var/lib/coturn -R

#

echo "root:$(cat /var/lib/secrets/main)" | chpasswd -c SHA512

echo "free:a" | chpasswd -c SHA512

#

sudo -u free flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

#

rm -rf /root/sp.sh

#

chown bitcoin:bitcoin /run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node -R

chmod 770 /run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node -R

chown electrs:electrs /run/media/Second_Drive/BTCEcoandBackup/Electrs_Data -R

chmod 770 /run/media/Second_Drive/BTCEcoandBackup/Electrs_Data -R

#

pushd /etc/nixos

  nix flake update

  nixos-rebuild switch --impure

popd

#

mkdir -p /home/free/Downloads

pushd /home/free/Downloads

  wget https://git.sovransystems.com/Sovran_Systems/Software/raw/branch/main/Sovran_SystemsOS_Reseter/sovran_systemsOS_reseter_local_installer/sovran_systemsOS_reseter_install.sh

  bash sovran_systemsOS_reseter_install.sh

popd

#

pushd /home/free/Downloads

  wget https://git.sovransystems.com/Sovran_Systems/Software/raw/branch/main/Sovran_SystemsOS_Updater/sovran_systemsOS_updater_local_installer/sovran_systemsOS_updater_install.sh

  bash sovran_systemsOS_updater_install.sh

popd

#

mkdir -p /home/free/Pictures

pushd /home/free/Pictures

  wget https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/Wallpaper_Dark_Wide.png

  chown free:users /home/free -R

  chmod 770 /home/free -R

popd

#

pushd /home/free/Downloads

  sudo -u free wget https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/raw/branch/main/for_new_sovran_pros/Sovran_SystemsOS-Desktop

popd

#

wp=$(cat /var/lib/secrets/wordpressdb)

sudo mysql -u root -e "SET PASSWORD FOR wpusr@localhost = PASSWORD('${wp}')";

#

mkdir /root/.ssh

mkdir -p /home/free/.ssh

chown free:users /home/free/.ssh -R

touch /root/.ssh/authorized_keys

sudo -u free ssh-keygen -q -N "gosovransystems" -t ed25519 -f /home/free/.ssh/factory_login

chmod 700 /home/free/.ssh -R

echo "$(cat /home/free/.ssh/factory_login.pub)" >> /root/.ssh/authorized_keys

#

sudo matrix-synapse-register_new_matrix_user -u admin -p a -a

sudo echo "no" | matrix-synapse-register_new_matrix_user -u test -p a

# This key is removed before shipping as it allows Sovran Systems to access the machine via root remotely. 

echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCQa3DEhx9RUtV0WopfFuL3cjQt2fBzp5wOg/hkj0FXyZXpp+F47Td1B9mKMNvucINaMQB6T0mW6c70fyT92gZO2OqCff6aeWovtTd9ynRgtJbny/qvVSShDbJcR7nSMeVPoDRaYs18fuA50guYnfoYAkaXyXPmVQ0uK84HwIB5j8gq6GMji7vv+TTNhDP8qOceUzt1DYPo9Z2JSnkFey+Z/fmxWJGsu+MSrA0/PPENEmf6L0ZSgxnu3gHEtdyX2hrFzjE16y3G0wSQzbWJb8MJO0KRSMcyvz6AzOSW4RYdXR1c+4JiciKRdnIAYYHfg7tnZT9wC9AzHjdEbmmrlF05mtjXKnxbPgGY0tlRSYo7B5E0k2zfi30MkIJ6kIE9TMM2z/+1KstrQN4OKBTGomBTYQaRQCT6dGpRTR+b8lOvUcnCSuat1sUC2M2VGFcBbDbKD0FyXy/vOk1pgA4I7GoESWQClnl+ntRg8HrW4oVTX2KpqR2CXjlF956HJGqHW6k= free@nixos" >> /root/.ssh/authorized_keys

#

set +x

echo -e "${GREEN}These four passwords are generated for convenience to use for the Web front end setup UI accounts for Nextcloud, Wordpress, VaultWarden, and BTCPayserver (if you want to use them).${ENDCOLOR} \n"

echo -e "$(pwgen -s 17 -1) \n"
echo -e "$(pwgen -s 17 -1) \n"
echo -e "$(pwgen -s 17 -1) \n"
echo -e "$(pwgen -s 17 -1) \n"

#

DOMAIN=$(cat /var/lib/domains/matrix)


cp -n /var/lib/caddy/.local/share/caddy/certificates/acme.zerossl.com-v2-dv90/${DOMAIN}/${DOMAIN}.crt /var/lib/coturn/${DOMAIN}.crt.pem
      
cp -n /var/lib/caddy/.local/share/caddy/certificates/acme.zerossl.com-v2-dv90/${DOMAIN}/${DOMAIN}.key /var/lib/coturn/${DOMAIN}.key.pem

bash /var/lib/external_ip/external_ip.sh

chown turnserver:turnserver /var/lib/coturn -R

chmod 770 /var/lib/coturn -R

#

pushd /etc/nixos

  nix flake update

  nixos-rebuild switch --impure

popd

#

echo -e "${LIGHTBLUE}One last thing, you need to put the Njalla DDNS info from Njalla into njalla.sh.${ENDCOLOR} \n"

echo -e "${GREEN}All Finished! Please Reboot then Enjoy your New Sovran Pro!${ENDCOLOR} \n"
