sudo mkdir -p /var/lib/domains

# One domain per file — just the bare domain, no https://
echo "matrix.yourdomain.com"      | sudo tee /var/lib/domains/matrix
echo "cloud.yourdomain.com"       | sudo tee /var/lib/domains/nextcloud
echo "blog.yourdomain.com"        | sudo tee /var/lib/domains/wordpress
echo "pay.yourdomain.com"         | sudo tee /var/lib/domains/btcpayserver
echo "vault.yourdomain.com"       | sudo tee /var/lib/domains/vaultwarden
echo "you@yourdomain.com"         | sudo tee /var/lib/domains/sslemail

# Only if you enable these features:
echo "relay.yourdomain.com"       | sudo tee /var/lib/domains/haven
echo "call.yourdomain.com"        | sudo tee /var/lib/domains/element-calling
