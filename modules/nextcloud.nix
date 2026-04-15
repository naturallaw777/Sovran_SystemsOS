{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.services.nextcloud {

  # ── PostgreSQL database ───────────────────────────────────
  services.postgresql = {
    enable = true;
  };

  # ── Auto-generate DB password and initialize ──────────────
  systemd.services.nextcloud-db-init = {
    description = "Initialize Nextcloud PostgreSQL database with auto-generated password";
    after = [ "postgresql.service" ];
    requires = [ "postgresql.service" ];
    before = [ "nextcloud-init.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ config.services.postgresql.package pkgs.pwgen pkgs.coreutils ];
    script = ''
      set -euo pipefail

      SECRET_FILE="/var/lib/secrets/nextclouddb"

      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p /var/lib/secrets
        pwgen -s 64 1 > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
      fi

      DB_PASS=$(cat "$SECRET_FILE")

      psql -U postgres <<SQL
        DO \$\$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ncusr') THEN
            CREATE ROLE "ncusr" WITH LOGIN PASSWORD '$DB_PASS';
          ELSE
            ALTER ROLE "ncusr" WITH LOGIN PASSWORD '$DB_PASS';
          END IF;
        END
        \$\$;
      SQL

      if ! psql -U postgres -lqt | cut -d \| -f 1 | grep -qw "nextclouddb"; then
        psql -U postgres -c "CREATE DATABASE nextclouddb WITH OWNER ncusr TEMPLATE template0 LC_COLLATE = 'C' LC_CTYPE = 'C';"
      fi
    '';
  };

  # ── Fully automated Nextcloud setup ───────────────────────
  systemd.services.nextcloud-init = {
    description = "Download, extract, and fully configure Nextcloud";
    after = [ "network-online.target" "postgresql.service" "phpfpm-mypool.service" "nextcloud-db-init.service" ];
    wants = [ "network-online.target" ];
    requires = [ "postgresql.service" "nextcloud-db-init.service" ];
    wantedBy = [ "multi-user.target" ];

    unitConfig = {
      ConditionPathExists = "!/var/lib/www/nextcloud/config/config.php";
    };

    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };

    path = with pkgs; [ curl unzip php pwgen coreutils shadow util-linux ];

    script = ''
      set -euo pipefail

      INSTALL_DIR="/var/lib/www/nextcloud"
      DATA_DIR="/var/lib/nextcloud"
      DOMAIN=$(cat /var/lib/domains/nextcloud)
      DB_NAME="nextclouddb"
      DB_USER="ncusr"
      DB_PASS=$(cat /var/lib/secrets/nextclouddb)
      DB_HOST="localhost"
      ADMIN_USER=$(pwgen -s 16 1)
      ADMIN_PASS=$(pwgen -s 24 1)

      echo "══════════════════════════════════════════════"
      echo "  Nextcloud Automated Installation"
      echo "══════════════════════════════════════════════"

      if [ ! -f "$INSTALL_DIR/occ" ]; then
          echo "Downloading Nextcloud..."
          TEMP_DIR=$(mktemp -d)
          curl -L -o "$TEMP_DIR/nextcloud.zip" "https://download.nextcloud.com/server/releases/latest.zip"
          unzip -q "$TEMP_DIR/nextcloud.zip" -d "$TEMP_DIR"
          mkdir -p "$INSTALL_DIR"
          cp -a "$TEMP_DIR/nextcloud/"* "$INSTALL_DIR/"
          rm -rf "$TEMP_DIR"
          echo "Download complete."
      fi

      chown -R caddy:php "$INSTALL_DIR"
      find "$INSTALL_DIR" -type d -exec chmod 750 {} \;
      find "$INSTALL_DIR" -type f -exec chmod 640 {} \;
      chmod -R 770 "$INSTALL_DIR/apps"
      chmod -R 770 "$INSTALL_DIR/config"

      if [ ! -d "$DATA_DIR" ]; then
          mkdir -p "$DATA_DIR"
          chown -R caddy:php "$DATA_DIR"
          chmod -R 770 "$DATA_DIR"
      fi

      echo "Waiting for PostgreSQL..."
      for i in $(seq 1 30); do
          if /run/wrappers/bin/su -s /bin/sh caddy -c "php -r \"new PDO('pgsql:host=$DB_HOST;dbname=$DB_NAME', '$DB_USER', '$DB_PASS');\"" 2>/dev/null; then
              echo "Database ready."
              break
          fi
          sleep 2
      done

      echo "Running Nextcloud installation..."
      /run/wrappers/bin/su -s /bin/sh caddy -c "
        php $INSTALL_DIR/occ maintenance:install \
          --database 'pgsql' \
          --database-name '$DB_NAME' \
          --database-user '$DB_USER' \
          --database-pass '$DB_PASS' \
          --database-host '$DB_HOST' \
          --admin-user '$ADMIN_USER' \
          --admin-pass '$ADMIN_PASS' \
          --data-dir '$DATA_DIR'
      "

      /run/wrappers/bin/su -s /bin/sh caddy -c "
        php $INSTALL_DIR/occ config:system:set trusted_domains 0 --value='$DOMAIN'
        php $INSTALL_DIR/occ config:system:set overwrite.cli.url --value='https://$DOMAIN'
        php $INSTALL_DIR/occ config:system:set overwritehost --value='$DOMAIN'
        php $INSTALL_DIR/occ config:system:set overwriteprotocol --value='https'
      "

      /run/wrappers/bin/su -s /bin/sh caddy -c "
        php $INSTALL_DIR/occ config:system:set trusted_proxies 0 --value='127.0.0.1'
        php $INSTALL_DIR/occ config:system:set trusted_proxies 1 --value='::1'
        php $INSTALL_DIR/occ config:system:set forwarded_for_headers 0 --value='HTTP_X_FORWARDED_FOR'
        php $INSTALL_DIR/occ config:system:set default_phone_region --value='US'
        php $INSTALL_DIR/occ config:system:set maintenance_window_start --type=integer --value=1
        php $INSTALL_DIR/occ config:system:set memcache.local --value='\OC\Memcache\APCu'
        php $INSTALL_DIR/occ config:system:set memcache.locking --value='\OC\Memcache\APCu'
        php $INSTALL_DIR/occ config:system:set server_id --value=\"\$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')\"
        php $INSTALL_DIR/occ background:cron
      "

      /run/wrappers/bin/su -s /bin/sh caddy -c "
        php $INSTALL_DIR/occ integrity:check-core
        php $INSTALL_DIR/occ maintenance:repair
        php $INSTALL_DIR/occ db:add-missing-indices
        php $INSTALL_DIR/occ db:add-missing-columns
        php $INSTALL_DIR/occ db:add-missing-primary-keys
        php $INSTALL_DIR/occ maintenance:repair --include-expensive
        php $INSTALL_DIR/occ app:info app_api >/dev/null 2>&1 && php $INSTALL_DIR/occ app:disable app_api || true
      "

      /run/wrappers/bin/su -s /bin/sh caddy -c "
        php $INSTALL_DIR/occ app:install calendar || true
        php $INSTALL_DIR/occ app:install contacts || true
        php $INSTALL_DIR/occ app:install tasks || true
        php $INSTALL_DIR/occ app:install notes || true
        php $INSTALL_DIR/occ app:install deck || true
        php $INSTALL_DIR/occ app:enable calendar || true
        php $INSTALL_DIR/occ app:enable contacts || true
        php $INSTALL_DIR/occ app:enable tasks || true
        php $INSTALL_DIR/occ app:enable notes || true
        php $INSTALL_DIR/occ app:enable deck || true
      "

      CREDS_FILE="/var/lib/secrets/nextcloud-admin"
      cat > "$CREDS_FILE" << CREDS
Nextcloud Admin Credentials
═══════════════════════════
URL:      https://$DOMAIN/
Username: $ADMIN_USER
Password: $ADMIN_PASS
CREDS
      chmod 600 "$CREDS_FILE"

      echo ""
      echo "══════════════════════════════════════════════"
      echo "  Nextcloud installation complete!"
      echo "  Credentials saved to: $CREDS_FILE"
      echo "══════════════════════════════════════════════"
    '';
  };

  services.cron.systemCronJobs = [
    "*/5 * * * * caddy /run/current-system/sw/bin/php -f /var/lib/www/nextcloud/cron.php"
  ];

  systemd.tmpfiles.rules = [
    "d /var/lib/www 0755 caddy php -"
    "d /var/lib/www/nextcloud 0750 caddy php -"
    "d /var/lib/nextcloud 0770 caddy php -"
  ];

  services.phpfpm.pools.mypool.phpOptions = lib.mkAfter ''
    output_buffering = 0
  '';

  environment.systemPackages = with pkgs; [ unzip ];
  
  sovran_systemsOS.domainRequirements = [
    { name = "nextcloud"; label = "Nextcloud"; example = "cloud.yourdomain.com"; }
  ];
}
