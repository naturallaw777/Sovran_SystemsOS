{

matrix_url = builtins.readFile /var/lib/domains/matrix;
wordpress_url = builtins.readFile /var/lib/domains/wordpress;
nextcloud_url = builtins.readFile /var/lib/domains/nextcloud;
btcpayserver_url = builtins.readFile /var/lib/domains/btcpayserver;
caddy_email_for_zerossl = builtins.readFile /var/lib/domains/sslemail;
vaultwarden_url = builtins.readFile /var/lib/domains/vaultwarden;
onlyoffice_url = builtins.readFile /var/lib/domains/onlyoffice;

##

age.identityPaths = [ "/root/.ssh/agenix/agenix-secret-keys" ];

##

age.secrets.turn.file = /var/lib/agenix-secrets/turn.age;
age.secrets.matrix_reg_secret.file = /var/lib/agenix-secrets/matrix_reg_secret.age;
age.secrets.matrixdb.file = /var/lib/agenix-secrets/matrixdb.age;
age.secrets.nextclouddb.file = /var/lib/agenix-secrets/nextclouddb.age;
age.secrets.wordpressdb.file = /var/lib/agenix-secrets/wordpressdb.age;

##

external_ip_secret = builtins.readFile /var/lib/secrets/external_ip;
onlyofficejwtSecretFile = /var/lib/secrets/onlyofficejwtSecretFile;

}
