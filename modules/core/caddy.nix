{ config, pkgs, lib, ... }:

let
  exposeBtcpay = config.sovran_systemsOS.web.btcpayserver;
in
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
      read_domain() {
        if [ -f "/var/lib/domains/$1" ]; then
          cat "/var/lib/domains/$1"
        else
          echo ""
        fi
      }

      MATRIX=$(read_domain matrix)
      WORDPRESS=$(read_domain wordpress)
      NEXTCLOUD=$(read_domain nextcloud)
      BTCPAY=$(read_domain btcpayserver)
      VAULTWARDEN=$(read_domain vaultwarden)
      HAVEN=$(read_domain haven)
      ACME_EMAIL=$(read_domain sslemail)

      # Start with global config
      cat > /run/caddy/Caddyfile <<EOF
{
  email $ACME_EMAIL
}
EOF

      # ── Matrix ──────────────────────────────────────
      if [ -n "$MATRIX" ]; then
        if [ -f /run/caddy/element-calling.snippet ]; then
          cat /run/caddy/element-calling.snippet >> /run/caddy/Caddyfile
        else
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
      fi

      # ── WordPress ───────────────────────────────────
      if [ -n "$WORDPRESS" ]; then
        cat >> /run/caddy/Caddyfile <<EOF

$WORDPRESS {
  encode gzip zstd
  root * /var/lib/www/wordpress
  php_fastcgi unix//run/phpfpm/mypool.sock
  file_server browse
}
EOF
      fi

      # ── Nextcloud ───────────────────────────────────
      if [ -n "$NEXTCLOUD" ]; then
        cat >> /run/caddy/Caddyfile <<EOF

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
EOF
      fi

      # ── BTCPay (only if web exposure is enabled) ────
      ${if exposeBtcpay then ''
      if [ -n "$BTCPAY" ]; then
        cat >> /run/caddy/Caddyfile <<EOF

$BTCPAY {
  reverse_proxy http://localhost:23000
  encode gzip zstd
}
EOF
      fi
      '' else ''
      # BTCPay web exposure disabled by sovran_systemsOS.web.btcpayserver = false
      ''}

      # ── Vaultwarden ─────────────────────────────────
      if [ -n "$VAULTWARDEN" ]; then
        cat >> /run/caddy/Caddyfile <<EOF

$VAULTWARDEN {
  reverse_proxy http://localhost:8777
  encode gzip zstd
}
EOF
      fi

      # ── Haven ───────────────────────────────────────
      if [ -n "$HAVEN" ]; then
        cat >> /run/caddy/Caddyfile <<EOF

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
      fi

      # ── Sovran Hub (LAN access via mDNS) ────────────
      cat >> /run/caddy/Caddyfile <<EOF

http://sovransystemsos.local {
  reverse_proxy localhost:8937
}
EOF

      # ── RTL (LAN access) ────────────────────────────
      cat >> /run/caddy/Caddyfile <<EOF

http://127.0.0.1:3051, http://sovransystemsos.local:3051 {
  reverse_proxy :3050
  encode gzip zstd
}
EOF

      # ── Mempool (LAN access) ────────────────────────
      cat >> /run/caddy/Caddyfile <<EOF

http://127.0.0.1:60847, http://sovransystemsos.local:60847 {
  reverse_proxy :60845
  encode gzip zstd
}
EOF
    '';
  };
}
