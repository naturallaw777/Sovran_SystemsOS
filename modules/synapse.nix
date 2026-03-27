{ config, pkgs, lib, ... }:

{
  # ── PostgreSQL database for Matrix ──────────────────────────
  services.postgresql = {
    enable = true;
    ensureDatabases = [ "matrix-synapse" ];
    ensureUsers = [
      {
        name = "matrix-synapse";
        ensureDBOwnership = true;
      }
    ];
  };

  # ── Auto-generate DB password and initialize ────────────────
  systemd.services.matrix-synapse-db-init = {
    description = "Initialize Matrix Synapse PostgreSQL database with auto-generated password";
    after = [ "postgresql.service" ];
    requires = [ "postgresql.service" ];
    before = [ "matrix-synapse.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ config.services.postgresql.package pkgs.pwgen pkgs.coreutils ];
    script = ''
      SECRET_DIR="/var/lib/secrets"
      SECRET_FILE="$SECRET_DIR/matrix_db_secret"

      mkdir -p "$SECRET_DIR"

      if [ ! -f "$SECRET_FILE" ]; then
        pwgen -s 64 1 > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
        chown matrix-synapse:matrix-synapse "$SECRET_FILE"
      fi

      DB_PASS=$(cat "$SECRET_FILE")

      psql -U postgres -c "ALTER ROLE \"matrix-synapse\" WITH LOGIN PASSWORD '$DB_PASS';"

      if ! psql -U postgres -lqt | cut -d \| -f 1 | grep -qw "matrix-synapse"; then
        psql -U postgres -c "CREATE DATABASE \"matrix-synapse\" WITH OWNER \"matrix-synapse\" TEMPLATE template0 LC_COLLATE = 'C' LC_CTYPE = 'C';"
      fi
    '';
  };

  # ── Generate Synapse runtime config from /var/lib/domains ───
  systemd.services.matrix-synapse-runtime-config = {
    description = "Generate Matrix Synapse runtime config from domain files";
    before = [ "matrix-synapse.service" ];
    after = [ "matrix-synapse-db-init.service" ];
    requiredBy = [ "matrix-synapse.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.coreutils ];
    script = ''
      MATRIX=$(cat /var/lib/domains/matrix)
      RUNTIME_DIR="/run/matrix-synapse"
      mkdir -p "$RUNTIME_DIR"

      cat > "$RUNTIME_DIR/runtime-config.yaml" <<EOF
      server_name: "$MATRIX"
      EOF

      chown matrix-synapse:matrix-synapse "$RUNTIME_DIR/runtime-config.yaml"
      chmod 640 "$RUNTIME_DIR/runtime-config.yaml"
    '';
  };

  # ── Synapse service ─────────────────────────────────────────
  lib.mkIf config.sovran_systemsOS.features.synapse {
    services.matrix-synapse = {
      enable = true;
      extraConfigFiles = [ "/run/matrix-synapse/runtime-config.yaml" ];
      settings = {
        push.include_content = false;
        group_unread_count_by_room = false;
        encryption_enabled_by_default_for_room_type = "invite";
        allow_profile_lookup_over_federation = false;
        allow_device_name_lookup_over_federation = false;
        # server_name is injected at runtime via extraConfigFiles
        url_preview_enabled = true;
        max_upload_size = "1024M";
        url_preview_ip_range_blacklist = [
          "10.0.0.0/8"
          "100.64.0.0/10"
          "169.254.0.0/16"
          "172.16.0.0/12"
          "192.0.0.0/24"
          "192.0.2.0/24"
          "192.168.0.0/16"
          "192.88.99.0/24"
          "198.18.0.0/15"
          "198.51.100.0/24"
          "2001:db8::/32"
          "203.0.113.0/24"
          "224.0.0.0/4"
          "::1/128"
          "fc00::/7"
          "fe80::/10"
          "fec0::/10"
          "ff00::/8"
        ];
        url_preview_ip_ranger_whitelist = [ "127.0.0.1" ];
        presence.enabled = true;
        enable_registration = false;
        registration_shared_secret = config.age.secrets.matrix_reg_secret.path;
        listeners = [
          {
            port = 8008;
            bind_addresses = [ "::1" ];
            type = "http";
            tls = false;
            x_forwarded = true;
            resources = [
              {
                names = [ "client" ];
                compress = true;
              }
              {
                names = [ "federation" ];
                compress = false;
              }
            ];
          }
        ];
      };
    };
  }
}
