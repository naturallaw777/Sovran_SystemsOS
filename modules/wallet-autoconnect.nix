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
  "serverType": "ELECTRUM_SERVER",
  "electrumServer": "tcp://127.0.0.1:50001",
  "useProxy": false
}
EOF

      chown -R free:users /home/free/.sparrow
      echo "Sparrow auto-configured to use local Electrs node"
    '';
  };

  # ── Bisq 1 Auto-Connect ─────────────────────────────────────
  systemd.services.bisq-autoconnect = {
    description = "Auto-configure Bisq to use local Bitcoin node";
    after = [ "bitcoind.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.coreutils pkgs.iproute2 ];
    script = ''
      BISQ_CONF="/home/free/.local/share/Bisq/bisq.properties"

      if [ -f "$BISQ_CONF" ]; then
        echo "Bisq config already exists, skipping"
        exit 0
      fi

      # Wait for bitcoind RPC to be ready (up to 30 attempts)
      ATTEMPTS=0
      until ss -ltn 2>/dev/null | grep -q ':8333' || [ "$ATTEMPTS" -ge 30 ]; do
        ATTEMPTS=$((ATTEMPTS + 1))
        sleep 2
      done

      mkdir -p /home/free/.local/share/Bisq

      cat > "$BISQ_CONF" << 'EOF'
btcNodes=127.0.0.1:8333
useTorForBtc=true
useCustomBtcNodes=true
EOF

      chown -R free:users /home/free/.local/share/Bisq
      echo "Bisq auto-configured to use local Bitcoin node"
    '';
  };

  # ── Zeus Connect (lndconnect URL for mobile wallet) ──────────
  systemd.services.zeus-connect-setup = {
    description = "Save Zeus lndconnect URL";
    wantedBy = [ "multi-user.target" ];
    after = [ "lnd.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.coreutils "/run/current-system/sw" ];
    script = ''
      SECRET_FILE="/var/lib/secrets/zeus-connect-url"
      mkdir -p -m 700 /var/lib/secrets

      URL=""
      if command -v lndconnect >/dev/null 2>&1; then
        URL=$(lndconnect --url 2>/dev/null || true)
      elif command -v lnconnect-clnrest >/dev/null 2>&1; then
        URL=$(lnconnect-clnrest --url 2>/dev/null || true)
      fi

      if [ -n "$URL" ]; then
        echo "$URL" > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
        echo "Zeus connect URL saved."
      else
        echo "No lndconnect URL available yet."
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
