{

matrix_url = builtins.readFile /var/lib/domains/matrix;
wordpress_url = builtins.readFile /var/lib/domains/wordpress;
nextcloud_url = builtins.readFile /var/lib/domains/nextcloud;
btcpayserver_url = builtins.readFile /var/lib/domains/btcpayserver;
caddy_email_for_zerossl = builtins.readFile /var/lib/domains/sslemail;
vaultwarden_url = builtins.readFile /var/lib/domains/vaultwarden;

wordpressdb_pass = builtins.readFile /var/lib/secrets/wordpressdb;
matrix-synapsedb_pass = builtins.readFile /var/lib/secrets/matrixdb;
nextclouddb_pass = builtins.readFile /var/lib/secrets/nextclouddb;
turn_shared = builtins.readFile /var/lib/secrets/turn;
matrix_reg_secret = builtins.readFile /var/lib/secrets/matrix_reg_secret;
external_ip_secret = builtins.readFile /var/lib/secrets/external_ip;

}
