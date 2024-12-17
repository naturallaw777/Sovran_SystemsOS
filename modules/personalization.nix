{

matrix_url = builtins.readFile /var/lib/domains/matrix;
wordpress_url = builtins.readFile /var/lib/domains/wordpress;
nextcloud_url = builtins.readFile /var/lib/domains/nextcloud;
btcpayserver_url = builtins.readFile /var/lib/domains/btcpayserver;
caddy_email_for_acme = builtins.readFile /var/lib/domains/sslemail;
vaultwarden_url = builtins.readFile /var/lib/domains/vaultwarden;

##

external_ip_secret = builtins.readFile /var/lib/secrets/external_ip;
coturn_static_auth_secret = builtins.readFile /var/lib/secrets/turn;

}
