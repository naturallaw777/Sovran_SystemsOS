{

matrix_url = builtins.readFile /var/lib/domains/matrix;
wordpress_url = builtins.readFile /var/lib/domains/wordpress;
nextcloud_url = builtins.readFile /var/lib/domains/nextcloud;
btcpayserver_url = builtins.readFile /var/lib/domains/btcpayserver;
caddy_email_for_acme = builtins.readFile /var/lib/domains/sslemail;
vaultwarden_url = builtins.readFile /var/lib/domains/vaultwarden;
haven_url = builtins.readFile /var/lib/domains/haven;
element-calling_url = builtins.readFile /var/lib/domains/element-calling;

##

external_ip_secret = builtins.readFile /var/lib/secrets/external_ip;
coturn_static_auth_secret = builtins.readFile /var/lib/secrets/turn;

##

matrixdb = builtins.readFile /var/lib/secrets/matrixdb;
nextclouddb = builtins.readFile /var/lib/secrets/nextclouddb;
wordpressdb = builtins.readFile /var/lib/secrets/wordpressdb;


}
