{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.services.wordpress {

  # ── MariaDB database ──────────────────────────────────────
  services.mysql = {
    enable = true;
    package = pkgs.mariadb;
  };

  # ── Auto-generate DB password and initialize ────────���─────
  systemd.services.wordpress-db-init = {
    description = "Initialize WordPress MariaDB database with auto-generated password";
    after = [ "mysql.service" ];
    requires = [ "mysql.service" ];
    before = [ "wordpress-init.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ config.services.mysql.package pkgs.pwgen pkgs.coreutils ];
    script = ''
      set -euo pipefail

      SECRET_FILE="/var/lib/secrets/wordpressdb"

      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p /var/lib/secrets
        pwgen -s 64 1 > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
      fi

      DB_PASS=$(cat "$SECRET_FILE")

      mysql -u root <<SQL
        CREATE DATABASE IF NOT EXISTS wordpressdb;
        CREATE USER IF NOT EXISTS 'wpusr'@'localhost' IDENTIFIED BY '$DB_PASS';
        ALTER USER 'wpusr'@'localhost' IDENTIFIED BY '$DB_PASS';
        GRANT ALL ON wordpressdb.* TO 'wpusr'@'localhost';
        FLUSH PRIVILEGES;
      SQL
    '';
  };

  # ── Fully automated WordPress setup ───────────────────────
  systemd.services.wordpress-init = {
    description = "Download, extract, and fully configure WordPress";
    after = [ "network-online.target" "mysql.service" "phpfpm-wordpress.service" "wordpress-db-init.service" ];
    wants = [ "network-online.target" ];
    requires = [ "mysql.service" "wordpress-db-init.service" ];
    wantedBy = [ "multi-user.target" ];

    unitConfig = {
      ConditionPathExists = "!/var/lib/www/wordpress/wp-config.php";
    };

    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };

    path = with pkgs; [ curl unzip wp-cli pwgen php coreutils shadow util-linux ];

    script = ''
      set -euo pipefail

      INSTALL_DIR="/var/lib/www/wordpress"
      DOMAIN=$(cat /var/lib/domains/wordpress)
      DB_NAME="wordpressdb"
      DB_USER="wpusr"
      DB_PASS=$(cat /var/lib/secrets/wordpressdb)
      DB_HOST="localhost"
      ADMIN_USER=$(pwgen -s 16 1)
      ADMIN_PASS=$(pwgen -s 24 1)
      EMAIL_DOMAIN="''${DOMAIN#*.}"
      if ! echo "$EMAIL_DOMAIN" | grep -q '\.'; then
        EMAIL_DOMAIN="$DOMAIN"
      fi
      ADMIN_EMAIL="$ADMIN_USER@$EMAIL_DOMAIN"

      echo "══════════════════════════════════════════════"
      echo "  WordPress Automated Installation"
      echo "══════════════════════════════════════════════"

      if [ ! -f "$INSTALL_DIR/wp-includes/version.php" ]; then
          echo "Downloading WordPress..."
          TEMP_DIR=$(mktemp -d)
          curl -L -o "$TEMP_DIR/wordpress.zip" "https://wordpress.org/latest.zip"
          unzip -q "$TEMP_DIR/wordpress.zip" -d "$TEMP_DIR"
          mkdir -p "$INSTALL_DIR"
          cp -a "$TEMP_DIR/wordpress/"* "$INSTALL_DIR/"
          rm -rf "$TEMP_DIR"
          echo "Download complete."
      fi

      chown -R caddy:root "$INSTALL_DIR"
      find "$INSTALL_DIR" -type d -exec chmod 755 {} \;
      find "$INSTALL_DIR" -type f -exec chmod 644 {} \;
      chmod -R 775 "$INSTALL_DIR/wp-content"

      echo "Generating wp-config.php..."
      cd "$INSTALL_DIR"
      /run/wrappers/bin/su -s /bin/sh caddy -c "
        wp config create \
          --dbname='$DB_NAME' \
          --dbuser='$DB_USER' \
          --dbpass='$DB_PASS' \
          --dbhost='$DB_HOST' \
          --skip-check
      "

      echo "Waiting for database..."
      for i in $(seq 1 30); do
          if /run/wrappers/bin/su -s /bin/sh caddy -c "wp db check" 2>/dev/null; then
              break
          fi
          sleep 2
      done

      echo "Running WordPress core install..."
      /run/wrappers/bin/su -s /bin/sh caddy -c "
        wp core install \
          --url='https://$DOMAIN' \
          --title='Sovran_SystemsOS' \
          --admin_user='$ADMIN_USER' \
          --admin_password='$ADMIN_PASS' \
          --admin_email='$ADMIN_EMAIL' \
          --skip-email
      "

      /run/wrappers/bin/su -s /bin/sh caddy -c "
        wp option update blogdescription 'Powered by Sovran_SystemsOS'
        wp option update permalink_structure '/%postname%/'
        wp option update default_ping_status 'closed'
        wp option update default_comment_status 'closed'
        wp rewrite flush
      "

      /run/wrappers/bin/su -s /bin/sh caddy -c "
        wp config set DISALLOW_FILE_EDIT true --raw
        wp config set WP_AUTO_UPDATE_CORE true --raw
        wp config set FORCE_SSL_ADMIN true --raw
      "

      CREDS_FILE="/var/lib/secrets/wordpress-admin"
      cat > "$CREDS_FILE" << CREDS
WordPress Admin Credentials
═══════════════════════════
URL:      https://$DOMAIN/wp-admin/
Username: $ADMIN_USER
Password: $ADMIN_PASS
Email:    $ADMIN_EMAIL
CREDS
      chmod 600 "$CREDS_FILE"

      echo ""
      echo "══════════════════════════════════════════════"
      echo "  WordPress installation complete!"
      echo "  Credentials saved to: $CREDS_FILE"
      echo "══════════════════════════════════════════════"
    '';
  };

  systemd.services.wordpress-detect-existing = {
    description = "Detect pre-existing WordPress installation and populate hub credentials";
    after = [ "mysql.service" ];
    wants = [ "mysql.service" ];
    wantedBy = [ "multi-user.target" ];

    unitConfig = {
      ConditionPathExists = [
        "/var/lib/www/wordpress/wp-config.php"
        "!/var/lib/secrets/wordpress-admin"
      ];
    };

    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };

    path = with pkgs; [ coreutils gnused ];

    script = ''
      set -euo pipefail

      CREDS_FILE="/var/lib/secrets/wordpress-admin"
      DOMAIN_FILE="/var/lib/domains/wordpress"
      DOMAIN="your-domain"

      if [ -f "$DOMAIN_FILE" ]; then
        FILE_DOMAIN="$(sed -n '1{s/^[[:space:]]*//;s/[[:space:]]*$//;p;}' "$DOMAIN_FILE")"
        if [ -n "$FILE_DOMAIN" ]; then
          DOMAIN="$FILE_DOMAIN"
        fi
      fi

      mkdir -p /var/lib/secrets

      cat > "$CREDS_FILE" << CREDS
WordPress (Pre-existing Installation)
═══════════════════════════════════════
URL:      https://$DOMAIN/wp-admin/
Note:     This WordPress was installed before Sovran_SystemsOS.
          Use your existing admin credentials to log in.
Reset:    wp user update <username> --user_pass=<new-password>
CREDS
      chmod 600 "$CREDS_FILE"
    '';
  };

  services.phpfpm.pools.wordpress = {
    user = "caddy";
    group = "php";
    phpPackage = config.sovran_systemsOS.phpPackage;
    settings = {
      "pm" = "dynamic";
      "pm.max_children" = 75;
      "pm.start_servers" = 10;
      "pm.min_spare_servers" = 5;
      "pm.max_spare_servers" = 20;
      "pm.max_requests" = 500;
      "clear_env" = "no";
      "listen" = "/run/phpfpm/wordpress.sock";
    };
  };

  systemd.tmpfiles.rules = [
    "d /var/lib/www 0755 caddy root -"
    "d /var/lib/www/wordpress 0755 caddy root -"
  ];

  environment.systemPackages = with pkgs; [ wp-cli unzip ];
  
  sovran_systemsOS.domainRequirements = [
    { name = "wordpress"; label = "WordPress"; example = "blog.yourdomain.com"; }
  ];
}
