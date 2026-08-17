{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.services.bitcoin {

  # ── Sparrow Wallet Auto-Connect ─────────────────────────────
  systemd.services.sparrow-autoconnect = {
    description = "Auto-configure Sparrow Wallet to use local Electrs node";
    after = [ "electrs.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.coreutils pkgs.iproute2 ];
    script = ''
      CONFIG_FILE="/home/free/.sparrow/config"

      if [ -f "$CONFIG_FILE" ]; then
        echo "Sparrow config already exists, skipping"
        exit 0
      fi

      # Wait for Electrs to be ready (up to 30 attempts)
      ATTEMPTS=0
      until ss -ltn 2>/dev/null | grep -q ':50001' || [ "$ATTEMPTS" -ge 30 ]; do
        ATTEMPTS=$((ATTEMPTS + 1))
        sleep 2
      done

      mkdir -p /home/free/.sparrow

      cat > "$CONFIG_FILE" << 'EOF'
{
  "mode": "ONLINE",
  "serverType": "ELECTRUM_SERVER",
  "electrumServer": "tcp://127.0.0.1:50001",
  "useProxy": false
}
EOF

      chown -R free:users /home/free/.sparrow
      echo "Sparrow auto-configured to use local Electrs node"
    '';
  };

  # ── Zeus Connect (lndconnect URL for mobile wallet) ──────────
  systemd.services.zeus-connect-setup = {
    description = "Save Zeus lndconnect URL";
    wantedBy = [ "multi-user.target" ];
    after = [ "lnd.service" "onion-addresses.service" ];
    wants = [ "lnd.service" "onion-addresses.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    # sudo is required: the lndconnect wrapper re-execs as the lnd user so it
    # can read admin.macaroon (not group-readable).
    path = [ pkgs.coreutils pkgs.gnugrep pkgs.sudo "/run/current-system/sw" ];
    script = ''
      SECRET_FILE="/var/lib/secrets/zeus-connect-url"
      mkdir -p /var/lib/secrets

      # LND may still be creating the wallet / macaroon, and the dedicated
      # lnd-rest onion hostname is published by onion-addresses.service.
      URL=""
      ATTEMPTS=0
      while [ "$ATTEMPTS" -lt 60 ]; do
        if command -v lndconnect >/dev/null 2>&1; then
          URL=$(lndconnect --url 2>/dev/null | tr -d '\r' | tail -n 1 || true)
        fi
        # Zeus LND REST over Tor: lndconnect://<v3-onion>:8080?macaroon=...
        if echo "$URL" | grep -q '^lndconnect://' \
           && echo "$URL" | grep -q '\.onion' \
           && echo "$URL" | grep -q 'macaroon='; then
          break
        fi
        URL=""
        ATTEMPTS=$((ATTEMPTS + 1))
        sleep 2
      done

      if [ -n "$URL" ]; then
        printf '%s\n' "$URL" > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
        echo "Zeus connect URL saved."
      else
        echo "No valid lndconnect URL available yet."
      fi
    '';
  };

  # ── Refresh Zeus URL periodically (certs/macaroons may rotate)
  systemd.timers.zeus-connect-setup = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "2min";
      OnUnitActiveSec = "30min";
      Unit = "zeus-connect-setup.service";
    };
  };

}
