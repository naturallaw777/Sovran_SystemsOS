{ config, pkgs, lib, ... }:

{
  services.caddy = {
    enable = true;
    user = "caddy";
    group = "root";
    configFile = "/run/caddy/Caddyfile";
  };

  systemd.services.caddy-generate-config = {
    description = "Generate Caddyfile from /var/lib/domains at runtime";
    before = [ "caddy.service" ];
    requiredBy = [ "caddy.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      RuntimeDirectory = "caddy";
    };
    path = [ pkgs.coreutils ];
    script = ''
      MATRIX=$(cat /var/lib/domains/matrix)
      WORDPRESS=$(cat /var/lib/domains/wordpress)
      NEXTCLOUD=$(cat /var/lib/domains/nextcloud)
      BTCPAY=$(cat /var/lib/domains/btcpayserver)
      VAULTWARDEN=$(cat /var/lib/domains/vaultwarden)
      HAVEN=$(cat /var/lib/domains/haven)
      ACME_EMAIL=$(cat /var/lib/domains/sslemail)

      # Start with global config
      cat > /run/caddy/Caddyfile <<EOF
{
  email $ACME_EMAIL
}
EOF

      # If element-calling is enabled, it wrote a snippet with
      # enhanced Matrix vhosts (.well-known, element-calling routes)
      if [ -f /run/caddy/element-calling.snippet ]; then
        cat /run/caddy/element-calling.snippet >> /run/caddy/Caddyfile
      else
        # Fallback: basic Matrix vhosts without element-calling
        cat >> /run/caddy/Caddyfile <<EOF

$MATRIX {
  reverse_proxy /_matrix/* http://localhost:8008
  reverse_proxy /_synapse/client/* http://localhost:8008
}

$MATRIX:8448 {
  reverse_proxy http://localhost:8008
}
EOF
      fi

      # Append remaining vhosts
      cat >> /run/caddy/Caddyfile <<EOF

$WORDPRESS {
  encode gzip zstd
  root * /var/lib/www/wordpress
  php_fastcgi unix//run/phpfpm/mypool.sock
  file_server browse
}

$NEXTCLOUD {
  encode gzip zstd
  root * /var/lib/www/nextcloud
  php_fastcgi unix//run/phpfpm/mypool.sock {
    trusted_proxies private_ranges
  }
  file_server
  redir /.well-known/carddav /remote.php/dav/ 301
  redir /.well-known/caldav /remote.php/dav/ 301
  header {
    Strict-Transport-Security max-age=31536000;
  }
}

$BTCPAY {
  reverse_proxy http://localhost:23000
  encode gzip zstd
}

$VAULTWARDEN {
  reverse_proxy http://localhost:8777
  encode gzip zstd
}

$HAVEN {
  reverse_proxy localhost:3355 {
    header_up Host {host}
    header_up X-Real-IP {remote_host}
    header_up X-Forwarded-For {remote_host}
    header_up X-Forwarded-Proto {scheme}
    transport http {
      versions 1.1
    }
  }
  request_body {
    max_size 100MB
  }
}
EOF
    '';
  };
}
