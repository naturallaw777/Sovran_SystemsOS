{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.services.synapse {

  services.postgresql = {
    ensureDatabases = [ "matrix-synapse" ];
    ensureUsers = [
      {
        name = "matrix-synapse";
        ensureDBOwnership = true;
      }
    ];
  };

  # ── Generate registration secret if missing ─────────────────
  systemd.services.matrix-synapse-secret-init = {
    description = "Generate Matrix Synapse registration secret if missing";
    wantedBy = [ "multi-user.target" ];
    before = [ "matrix-synapse.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.pwgen pkgs.coreutils ];
    script = ''
      SECRET_FILE="/var/lib/matrix-synapse/registration-secret"
      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p /var/lib/matrix-synapse
        pwgen -s 64 1 > "$SECRET_FILE"
        chown matrix-synapse:matrix-synapse "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
        echo "Generated Matrix registration secret"
      else
        echo "Matrix registration secret already exists, skipping"
      fi
    '';
  };

  # ── Generate DB password if missing ─────────────────────────
  systemd.services.matrix-synapse-db-init = {
    description = "Generate Matrix Synapse DB password if missing";
    wantedBy = [ "multi-user.target" ];
    before = [ "matrix-synapse.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.pwgen ];
    script = ''
      SECRET_FILE="/var/lib/matrix-synapse/db-password"
      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p /var/lib/matrix-synapse
        pwgen -s 32 1 > "$SECRET_FILE"
        chown matrix-synapse:matrix-synapse "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
        echo "Generated new DB password at $SECRET_FILE"
      else
        echo "DB password already exists, skipping"
      fi
    '';
  };

  # ── Generate runtime config from domain files ───────────────
  systemd.services.matrix-synapse-runtime-config = {
    description = "Generate Synapse runtime config from domain files";
    before = [ "matrix-synapse.service" ];
    after = [ "matrix-synapse-db-init.service" "matrix-synapse-secret-init.service" ];
    requiredBy = [ "matrix-synapse.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    unitConfig = {
      ConditionPathExists = "/var/lib/domains/matrix";
    };
    path = [ pkgs.coreutils ];
    script = ''
      MATRIX=$(cat /var/lib/domains/matrix)

      mkdir -p /run/matrix-synapse

      cat > /run/matrix-synapse/runtime-config.yaml <<EOF
server_name: "$MATRIX"
public_baseurl: "https://$MATRIX"
registration_shared_secret_path: "/var/lib/matrix-synapse/registration-secret"
EOF

      chown matrix-synapse:matrix-synapse /run/matrix-synapse/runtime-config.yaml
      chmod 640 /run/matrix-synapse/runtime-config.yaml
    '';
  };

  # ── Synapse service ─────────────────────────────────────────
  services.matrix-synapse = {
    enable = true;
    extraConfigFiles = [
      "/run/matrix-synapse/runtime-config.yaml"
    ];
    settings = {
      database = {
        name = "psycopg2";
        args = {
          host = "localhost";
          database = "matrix-synapse";
          user = "matrix-synapse";
        };
      };
      push.include_content = false;
      url_preview_enabled = true;
      group_unread_count_by_room = false;
      encryption_enabled_by_default_for_room_type = "invite";
      allow_profile_lookup_over_federation = false;
      allow_device_name_lookup_over_federation = false;
      url_preview_ip_range_blacklist = [
        "10.0.0.0/8" "100.64.0.0/10" "169.254.0.0/16" "172.16.0.0/12"
        "192.0.0.0/24" "192.0.2.0/24" "192.168.0.0/16" "192.88.99.0/24"
        "198.18.0.0/15" "198.51.100.0/24" "2001:db8::/32" "203.0.113.0/24"
        "224.0.0.0/4" "::1/128" "fc00::/7" "fe80::/10" "fec0::/10" "ff00::/8"
      ];
      url_preview_ip_ranger_whitelist = [ "127.0.0.1" ];
      presence.enabled = true;
      enable_registration = false;
      listeners = [
        {
          port = 8008;
          bind_addresses = [ "::1" ];
          type = "http";
          tls = false;
          x_forwarded = true;
          resources = [
            { names = [ "client" ]; compress = true; }
            { names = [ "federation" ]; compress = false; }
          ];
        }
      ];
    };
  };

  systemd.services.matrix-synapse.after = [ "matrix-synapse-secret-init.service" ];
  systemd.services.matrix-synapse.wants = [ "matrix-synapse-secret-init.service" ];
  
  
    # ── Auto-generate Admin and Test users ──────────────────────
  systemd.services.matrix-synapse-create-users = {
    description = "Create Admin and Test users for Matrix Synapse";
    wantedBy = [ "multi-user.target" ];
    after = [ "matrix-synapse.service" ];
    requires = [ "matrix-synapse.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.pwgen pkgs.matrix-synapse pkgs.curl pkgs.coreutils pkgs.jq ];
    script = ''
      set -uo pipefail

      # Wait for Synapse to be fully responsive
      for i in {1..30}; do
        if curl -s http://localhost:8008/_matrix/client/versions > /dev/null; then
          break
        fi
        sleep 2
      done

      DOMAIN=$(cat /var/lib/domains/matrix)
      CREDS_FILE="/var/lib/secrets/matrix-users"
      SECRET=$(cat /var/lib/matrix-synapse/registration-secret)

      mkdir -p /var/lib/secrets

      ADMIN_USER="admin"
      TEST_USER="test"
      ADMIN_PASS=""
      TEST_PASS=""

      # Only run user registration if we haven't already generated the credentials file
      if [ ! -f "$CREDS_FILE" ]; then
        ADMIN_PASS=$(pwgen -s 24 1)
        TEST_PASS=$(pwgen -s 24 1)

        ADMIN_CREATED=true
        TEST_CREATED=true

        # Create Admin user (tolerate "already exists")
        if ! register_new_matrix_user -c /run/matrix-synapse/runtime-config.yaml \
          -u "$ADMIN_USER" -p "$ADMIN_PASS" -a http://localhost:8008 2>&1; then
          echo "Admin user already exists, skipping."
          ADMIN_CREATED=false
        fi

        # Create Test user (tolerate "already exists")
        if ! register_new_matrix_user -c /run/matrix-synapse/runtime-config.yaml \
          -u "$TEST_USER" -p "$TEST_PASS" --no-admin http://localhost:8008 2>&1; then
          echo "Test user already exists, skipping."
          TEST_CREATED=false
        fi

        # Write credentials file
        if [ "$ADMIN_CREATED" = true ] && [ "$TEST_CREATED" = true ]; then
          cat > "$CREDS_FILE" << CREDS
Matrix (Element) Credentials
════════════════════════════
Homeserver URL: https://$DOMAIN

[ Admin Account ]
Username: @$ADMIN_USER:$DOMAIN
Password: $ADMIN_PASS

[ Test Account ]
Username: @$TEST_USER:$DOMAIN
Password: $TEST_PASS
CREDS
        else
          cat > "$CREDS_FILE" << CREDS
Matrix (Element) Credentials
════════════════════════════
Homeserver URL: https://$DOMAIN

[ Admin Account ]
Username: @$ADMIN_USER:$DOMAIN
Password: $(if [ "$ADMIN_CREATED" = true ]; then echo "$ADMIN_PASS"; else echo "(pre-existing — password set during original setup)"; fi)

[ Test Account ]
Username: @$TEST_USER:$DOMAIN
Password: $(if [ "$TEST_CREATED" = true ]; then echo "$TEST_PASS"; else echo "(pre-existing — password set during original setup)"; fi)
CREDS
        fi

        chmod 600 "$CREDS_FILE"
      fi

      # Always write individual credential files for the hub UI, even if the bulk
      # credentials file already existed from a prior run (umask 077 ensures mode 600).
      # If passwords were not freshly generated above, parse them from the bulk file.
      if [ -z "$ADMIN_PASS" ]; then
        ADMIN_PASS=$(awk '/\[ Admin Account \]/{f=1} f && /^Password:/{sub(/^Password: /,""); print; exit}' "$CREDS_FILE")
        [ -z "$ADMIN_PASS" ] && ADMIN_PASS="Password not available — check $CREDS_FILE"
      fi
      if [ -z "$TEST_PASS" ]; then
        TEST_PASS=$(awk '/\[ Test Account \]/{f=1} f && /^Password:/{sub(/^Password: /,""); print; exit}' "$CREDS_FILE")
        [ -z "$TEST_PASS" ] && TEST_PASS="Password not available — check $CREDS_FILE"
      fi
      (umask 077; echo "https://$DOMAIN" > /var/lib/secrets/matrix-homeserver-url)
      (umask 077; echo "@$ADMIN_USER:$DOMAIN" > /var/lib/secrets/matrix-admin-username)
      (umask 077; echo "$ADMIN_PASS" > /var/lib/secrets/matrix-admin-password)
      (umask 077; echo "@$TEST_USER:$DOMAIN" > /var/lib/secrets/matrix-test-username)
      (umask 077; echo "$TEST_PASS" > /var/lib/secrets/matrix-test-password)

      echo "Matrix users setup completed."
    '';
  };

  sovran_systemsOS.domainRequirements = [
    { name = "matrix"; label = "Matrix Synapse"; example = "matrix.yourdomain.com"; }
  ];
}
