{ config, pkgs, lib, ... }:

let
  exposeBtcpay = config.sovran_systemsOS.web.btcpayserver;
  extraVhosts = config.sovran_systemsOS.caddy.extraVirtualHosts;

  # True when any service needs HTTPS/ACME (domain-based vhosts)
  needsHttpsPorts =
    config.sovran_systemsOS.web.btcpayserver
    || config.sovran_systemsOS.services.synapse
    || config.sovran_systemsOS.services.wordpress
    || config.sovran_systemsOS.services.nextcloud
    || config.sovran_systemsOS.services.vaultwarden
    || config.sovran_systemsOS.features.haven
    || config.sovran_systemsOS.features."nwc-wallets"
    || config.sovran_systemsOS.features.element-calling;
in
{
  services.caddy = {
    # Only enable Caddy when at least one domain-based service needs it or
    # the operator has defined custom vhosts.  This prevents Caddy from
    # running on Desktop Only installs that have no web services configured.
    enable = needsHttpsPorts || extraVhosts != "";
    user = "caddy";
    group = "root";
  };

  # Only open ports 80/443 when at least one domain-based service is active
  networking.firewall.allowedTCPPorts = lib.mkIf needsHttpsPorts [ 80 443 ];
  networking.firewall.allowedUDPPorts = lib.mkIf needsHttpsPorts [ 80 443 ];

  systemd.tmpfiles.rules = [
    "d /var/lib/domains 0755 caddy root -"
  ];

  # Override ExecStart + ExecReload to point at the runtime-generated Caddyfile
  systemd.services.caddy.serviceConfig = {
    ExecStart = lib.mkForce [
      ""
      "${pkgs.caddy}/bin/caddy run --config /run/caddy/Caddyfile --adapter caddyfile"
    ];
    ExecReload = lib.mkForce [
      ""
      "${pkgs.caddy}/bin/caddy reload --config /run/caddy/Caddyfile --adapter caddyfile --force"
    ];
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
      LIGHTNING=$(read_domain lightning)
      ACME_EMAIL=$(read_domain sslemail)

      # Start with global config — use ACME only when domain-based services are active
      ${if needsHttpsPorts then ''
      cat > /run/caddy/Caddyfile <<EOF
{
  email $ACME_EMAIL
}
EOF
      '' else ''
      cat > /run/caddy/Caddyfile <<EOF
{
  auto_https off
}
EOF
      ''}

      # ── Matrix ──────────────────────────────────────
      if [ -n "$MATRIX" ]; then
        if [ -f /run/caddy/element-calling.snippet ]; then
          cat /run/caddy/element-calling.snippet >> /run/caddy/Caddyfile
        else
          cat >> /run/caddy/Caddyfile <<EOF

$MATRIX {
  reverse_proxy /_matrix/* http://localhost:8008
  reverse_proxy /_synapse/client/* http://localhost:8008
  handle /.well-known/matrix/server {
    header Content-Type application/json
    respond \`{"m.server":"$MATRIX:443"}\` 200
  }
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
  php_fastcgi unix//run/phpfpm/wordpress.sock
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
  php_fastcgi unix//run/phpfpm/nextcloud.sock {
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

      # ── Wallet Connections LNURL ──────────────────────
      if [ -n "$LIGHTNING" ]; then
        cat >> /run/caddy/Caddyfile <<EOF

$LIGHTNING {
  # LNURL discovery and callback are served by the dedicated
  # nwc-lnurl service on loopback port 8181.  Only these paths
  # are proxied; the Alby Hub management port (18080) is never exposed.
  reverse_proxy /.well-known/lnurlp/* http://127.0.0.1:8181
  reverse_proxy /lnurlp/* http://127.0.0.1:8181
}
EOF
      fi

      # ── Sovran Hub (LAN access via mDNS) ────────────
      cat >> /run/caddy/Caddyfile <<EOF

http://sovransystemsos.local {
  reverse_proxy localhost:8937
  header {
    Clear-Site-Data "\"cache\""
    Cache-Control "no-store, no-cache, must-revalidate, max-age=0"
    Pragma "no-cache"
    Expires "0"
  }
}
EOF

      # ── RTL (LAN access) ────────────────────────────
      cat >> /run/caddy/Caddyfile <<EOF

:3051 {
  reverse_proxy :3050
  encode gzip zstd
}
EOF

      # ── Mempool (LAN access) ────────────────────────
      cat >> /run/caddy/Caddyfile <<EOF

:60847 {
  reverse_proxy :60845
  encode gzip zstd
}
EOF

      # ── Custom vhosts from custom.nix ──────────────
      cat >> /run/caddy/Caddyfile <<'CUSTOM_VHOSTS_EOF'
${extraVhosts}
CUSTOM_VHOSTS_EOF
    '';
  };
}
