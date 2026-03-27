{ config, pkgs, lib, ... }:

let
  cfg = config.sovran_systemsOS.services.wordpress;
in
{
  options.sovran_systemsOS.services.wordpress = {
    enable = lib.mkEnableOption "WordPress (raw PHP served by Caddy)";
  };

  config = lib.mkIf cfg.enable {

    # ── Caddy vhost is now handled centrally in caddy.nix ─────

    # ── MariaDB database ──────────────────────────────────────
    services.mysql = {
      enable = true;
      package = pkgs.mariadb;
    };

    # ── Auto-generate DB password and initialize ──────────────
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

        # Existing machines already have this file — leave it alone
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
      after = [ "network-online.target" "mysql.service" "phpfpm-mypool.service" "wordpress-db-init.service" ];
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

      path = with pkgs; [ curl unzip wp-cli pwgen php coreutils ];

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
        ADMIN_EMAIL="$ADMIN_USER@''${DOMAIN#*.}"

        echo "══════════════════════════════════════════════"
        echo "  WordPress Automated Installation"
        echo "══════════════════════════════════════════════"

        # ── Download ────────────────────────────────────
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

        # ── Set permissions ─────────────────────────────
        chown -R caddy:root "$INSTALL_DIR"
        find "$INSTALL_DIR" -type d -exec chmod 755 {} \;
        find "$INSTALL_DIR" -type f -exec chmod 644 {} \;
        chmod -R 775 "$INSTALL_DIR/wp-content"

        # ── Generate wp-config.php ──────────────────────
        echo "Generating wp-config.php..."
        cd "$INSTALL_DIR"
        su -s /bin/sh caddy -c "
          wp config create \
            --dbname='$DB_NAME' \
            --dbuser='$DB_USER' \
            --dbpass='$DB_PASS' \
            --dbhost='$DB_HOST' \
            --skip-check
        "

        # ── Wait for database to be ready ───────────────
        echo "Waiting for database..."
        for i in $(seq 1 30); do
            if su -s /bin/sh caddy -c "wp db check" 2>/dev/null; then
                break
            fi
            sleep 2
        done

        # ── Run WordPress install ───────────────────────
        echo "Running WordPress core install..."
        su -s /bin/sh caddy -c "
          wp core install \
            --url='https://$DOMAIN' \
            --title='Sovran_SystemsOS' \
            --admin_user='$ADMIN_USER' \
            --admin_password='$ADMIN_PASS' \
            --admin_email='$ADMIN_EMAIL' \
            --skip-email
        "

        # ── Configure WordPress settings ────────────────
        echo "Configuring WordPress..."
        su -s /bin/sh caddy -c "
          wp option update blogdescription 'Powered by Sovran_SystemsOS'
          wp option update permalink_structure '/%postname%/'
          wp option update default_ping_status 'closed'
          wp option update default_comment_status 'closed'
          wp rewrite flush
        "

        # ── Security hardening ──────────────────────────
        echo "Applying security settings..."
        su -s /bin/sh caddy -c "
          wp config set DISALLOW_FILE_EDIT true --raw
          wp config set WP_AUTO_UPDATE_CORE true --raw
          wp config set FORCE_SSL_ADMIN true --raw
        "

        # ── Save admin credentials ──────────────────────
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
        echo ""
        echo "  URL:      https://$DOMAIN/wp-admin/"
        echo "  Username: $ADMIN_USER"
        echo "  Password: $ADMIN_PASS"
        echo ""
        echo "  Credentials saved to: $CREDS_FILE"
        echo "══════════════════════════════════════════════"
      '';
    };

    # ── Ensure directories ────────────────────────────────────
    systemd.tmpfiles.rules = [
      "d /var/lib/www 0755 caddy root -"
      "d /var/lib/www/wordpress 0755 caddy root -"
    ];

    environment.systemPackages = with pkgs; [
      wp-cli
      unzip
    ];
  };
}
