{ config, pkgs, lib, ... }:

let
  sovran-factory-seal = pkgs.writeShellScriptBin "sovran-factory-seal" ''
    set -euo pipefail

    if [ "$(id -u)" -ne 0 ]; then
      echo "Error: must be run as root." >&2
      exit 1
    fi

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║          ⚠  SOVRAN FACTORY SEAL — WARNING  ⚠               ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  This command will PERMANENTLY DELETE:                       ║"
    echo "║    • All generated passwords and secrets                     ║"
    echo "║    • LND wallet data (seed words, channels, macaroons)       ║"
    echo "║    • SSH factory login key                                   ║"
    echo "║    • Application databases (Matrix, Nextcloud, WordPress)    ║"
    echo "║    • Vaultwarden database                                    ║"
    echo "║                                                              ║"
    echo "║  After sealing, all credentials will be regenerated fresh   ║"
    echo "║  when the customer boots the device for the first time.     ║"
    echo "║                                                              ║"
    echo "║  DO NOT run this on a customer's live system.               ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo -n "Type SEAL to confirm: "
    read -r CONFIRM
    if [ "$CONFIRM" != "SEAL" ]; then
      echo "Aborted." >&2
      exit 1
    fi

    echo ""
    echo "Sealing system..."

    # ── 1. Delete all generated secrets ──────────────────────────────
    echo "  Wiping secrets..."
    [ -d /var/lib/secrets ] && find /var/lib/secrets -mindepth 1 -delete || true
    rm -rf /var/lib/matrix-synapse/registration-secret
    rm -rf /var/lib/matrix-synapse/db-password
    rm -rf /var/lib/gnome-remote-desktop/rdp-password
    rm -rf /var/lib/gnome-remote-desktop/rdp-username
    rm -rf /var/lib/gnome-remote-desktop/rdp-credentials
    rm -rf /var/lib/livekit/livekit_keyFile
    rm -rf /etc/nix-bitcoin-secrets/*

    # ── 2. Wipe LND wallet (seed words, wallet DB, macaroons) ────────
    echo "  Wiping LND wallet data..."
    rm -rf /var/lib/lnd/*

    # ── 3. Wipe SSH factory key so it regenerates with new passphrase ─
    echo "  Removing SSH factory key..."
    rm -f /home/free/.ssh/factory_login /home/free/.ssh/factory_login.pub
    if [ -f /root/.ssh/authorized_keys ]; then
      sed -i '/factory_login/d' /root/.ssh/authorized_keys
    fi

    # ── 4. Drop application databases ────────────────────────────────
    echo "  Dropping application databases..."
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS \"matrix-synapse\";" 2>/dev/null || true
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS nextclouddb;" 2>/dev/null || true
    mysql -u root -e "DROP DATABASE IF EXISTS wordpressdb;" 2>/dev/null || true

    # ── 5. Remove application config files (so init services re-run) ─
    echo "  Removing application config files..."
    rm -rf /var/lib/www/wordpress/wp-config.php
    rm -rf /var/lib/www/nextcloud/config/config.php

    # ── 6. Wipe Vaultwarden database ──────────────────────────────────
    echo "  Wiping Vaultwarden data..."
    rm -rf /var/lib/bitwarden_rs/*
    rm -rf /var/lib/vaultwarden/*

    # ── 7. Set sealed flag and remove onboarded flag ─────────────────
    echo "  Setting sealed flag..."
    touch /var/lib/sovran-factory-sealed
    rm -f /var/lib/sovran-customer-onboarded

    echo ""
    echo "System sealed. Power off now or the system will shut down in 10 seconds."
    sleep 10
    poweroff
  '';

in
{
  environment.systemPackages = [ sovran-factory-seal ];

  # ── Legacy security check: warn existing (pre-seal) machines ───────
  systemd.services.sovran-legacy-security-check = {
    description = "Check for legacy (pre-factory-seal) security status";
    wantedBy = [ "multi-user.target" ];
    after = [ "local-fs.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.coreutils pkgs.python3 ];
    script = ''
      # If sealed AND onboarded — fully clean, nothing to do
      [ -f /var/lib/sovran-factory-sealed ] && [ -f /var/lib/sovran-customer-onboarded ] && exit 0

      # If sealed but not yet onboarded — seal was run, customer hasn't finished setup yet, that's fine
      [ -f /var/lib/sovran-factory-sealed ] && exit 0

      # If onboarded but NOT sealed — installer ran without factory seal!
      if [ -f /var/lib/sovran-customer-onboarded ] && [ ! -f /var/lib/sovran-factory-sealed ]; then
        mkdir -p /var/lib/sovran
        echo "unsealed" > /var/lib/sovran/security-status
        cat > /var/lib/sovran/security-warning << 'EOF'
This machine was set up without the factory seal process. Factory test data — including SSH keys, database contents, and wallet information — may still be present on this system. It is strongly recommended to back up any important data and re-install using a fresh ISO, or contact Sovran Systems support for assistance.
EOF
        exit 0
      fi

      # If the user completed Hub onboarding, they've addressed security
      [ -f /var/lib/sovran/onboarding-complete ] && exit 0

      # If the free password has been changed from ALL known factory defaults, no warning needed
      if [ -f /etc/shadow ]; then
        FREE_HASH=$(grep '^free:' /etc/shadow | cut -d: -f2)
        if [ -n "$FREE_HASH" ] && [ "$FREE_HASH" != "!" ] && [ "$FREE_HASH" != "*" ]; then
          STILL_DEFAULT=false
          for DEFAULT_PW in "free" "gosovransystems"; do
            EXPECTED=$(DEFAULT_PW="$DEFAULT_PW" FREE_HASH="$FREE_HASH" python3 -c \
              "import crypt, os; print(crypt.crypt(os.environ['DEFAULT_PW'], os.environ['FREE_HASH']))")
            if [ "$EXPECTED" = "$FREE_HASH" ]; then
              STILL_DEFAULT=true
              break
            fi
          done
          if [ "$STILL_DEFAULT" = "false" ]; then
            # Password was changed — clear any legacy warning and exit
            rm -f /var/lib/sovran/security-status /var/lib/sovran/security-warning
            exit 0
          fi
        fi
      fi

      # No flags at all + secrets exist = legacy (pre-seal era) machine
      if [ -f /var/lib/secrets/root-password ]; then
        mkdir -p /var/lib/sovran
        echo "legacy" > /var/lib/sovran/security-status
        echo "This system was deployed before the factory seal feature. Your passwords may be known to the factory. Please change your passwords through the Sovran Hub." > /var/lib/sovran/security-warning
      fi
    '';
  };
}
