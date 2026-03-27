{ config, pkgs, lib, ... }:

{
  # The cron job scans /var/lib/njalla/hooks.d/ for DDNS URLs
  systemd.services.njalla-ddns = {
    description = "Njalla Dynamic DNS Updater";
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    serviceConfig = {
      Type = "oneshot";
    };
    script = ''
      set -euo pipefail

      IP=$(${pkgs.dig}/bin/dig @resolver4.opendns.com myip.opendns.com +short -4)

      if [ -z "$IP" ]; then
        echo "Failed to resolve external IP"
        exit 1
      fi

      # Only update if IP changed
      LAST_IP_FILE="/var/lib/njalla/.last_ip"
      LAST_IP=""
      [ -f "$LAST_IP_FILE" ] && LAST_IP=$(cat "$LAST_IP_FILE")

      if [ "$IP" = "$LAST_IP" ]; then
        echo "IP unchanged ($IP), skipping"
        exit 0
      fi

      echo -n "$IP" > "$LAST_IP_FILE"
      echo "IP changed to $IP, updating DNS records..."

      # Update external_ip secret
      echo -n "$IP" > /var/lib/secrets/external_ip

      # Process each DDNS hook
      HOOKS_DIR="/var/lib/njalla/hooks.d"
      mkdir -p "$HOOKS_DIR"

      for hook in "$HOOKS_DIR"/*; do
        [ -f "$hook" ] || continue
        DDNS_URL=$(cat "$hook")
        SERVICE=$(basename "$hook")
        echo "Updating $SERVICE..."
        ${pkgs.curl}/bin/curl -s "''${DDNS_URL}''${IP}" || echo "Failed: $SERVICE"
      done

      echo "Done."
    '';
  };

  # Run every 15 minutes
  systemd.timers.njalla-ddns = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "*:0/15";
      Persistent = true;
    };
  };

  # Ensure directory exists
  systemd.tmpfiles.rules = [
    "d /var/lib/njalla 0700 root root -"
    "d /var/lib/njalla/hooks.d 0700 root root -"
  ];
}