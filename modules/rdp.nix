{ config, pkgs, lib, ... }:

let
  cfg = config.sovran_systemsOS.features.rdp;
in
lib.mkIf cfg {

  services.gnome.gnome-remote-desktop.enable = true;

  networking.firewall.allowedTCPPorts = [ 3389 ];

  environment.systemPackages = with pkgs; [
    freerdp
  ];

  # Ensure correct directory ownership declaratively
  systemd.tmpfiles.rules = [
    "d /var/lib/gnome-remote-desktop 0700 gnome-remote-desktop gnome-remote-desktop -"
  ];

  # 🔹 Single unified setup service
  systemd.services.gnome-remote-desktop-setup = {
    description = "GNOME Remote Desktop (TLS + RDP config)";

    wantedBy = [ "multi-user.target" ];

    # Run AFTER daemon is up, but don't fail if it isn't
    after = [ "gnome-remote-desktop.service" ];
    wants = [ "gnome-remote-desktop.service" ];

    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };

    script = ''
      set -euo pipefail

      CERT_DIR=/var/lib/gnome-remote-desktop
      KEY_FILE=$CERT_DIR/rdp-tls.key
      CRT_FILE=$CERT_DIR/rdp-tls.crt

      echo "[GRD] Ensuring TLS cert exists..."

      if [ ! -f "$KEY_FILE" ]; then
        ${pkgs.util-linux}/bin/runuser -u gnome-remote-desktop -- \
          ${pkgs.freerdp}/bin/winpr-makecert -silent -rdp \
          -path "$CERT_DIR" rdp-tls
      fi

      echo "[GRD] Waiting for daemon..."

      # Wait for GRD to be responsive (prevents race condition)
      for i in $(seq 1 10); do
        if ${pkgs.gnome-remote-desktop}/bin/grdctl rdp show >/dev/null 2>&1; then
          break
        fi
        sleep 1
      done

      echo "[GRD] Applying configuration..."

      ${pkgs.gnome-remote-desktop}/bin/grdctl rdp set-tls-key "$KEY_FILE"
      ${pkgs.gnome-remote-desktop}/bin/grdctl rdp set-tls-cert "$CRT_FILE"
      ${pkgs.gnome-remote-desktop}/bin/grdctl rdp enable

      # Idempotent credential setup
      if ! ${pkgs.gnome-remote-desktop}/bin/grdctl rdp show | grep -q username; then
        ${pkgs.gnome-remote-desktop}/bin/grdctl rdp set-credentials "free" "a"
      fi

      echo "[GRD] Setup complete"
    '';
  };

}
