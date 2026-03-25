{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features.rdp {

  services.gnome.gnome-remote-desktop.enable = true;

  networking.firewall.allowedTCPPorts = [ 3389 ];

  environment.systemPackages = with pkgs; [
    freerdp
  ];

  systemd.services.gnome-remote-desktop-setup = {
    description = "GNOME Remote Desktop RDP Setup";
    
    wantedBy = [ "multi-user.target" ];

    after = [
      "gnome-remote-desktop.service"
    ];

    requires = [
      "gnome-remote-desktop.service"
    ];

    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;

    };

    script = ''
      set -euo pipefail

      CERT_DIR=/var/lib/gnome-remote-desktop
      KEY_FILE=$CERT_DIR/rdp-tls.key
      CRT_FILE=$CERT_DIR/rdp-tls.crt

      if [ ! -f "$KEY_FILE" ]; then
        echo "Generating RDP TLS certificate..."

        ${pkgs.freerdp}/bin/winpr-makecert -silent -rdp \
          -path "$CERT_DIR" rdp-tls

        chown gnome-remote-desktop:gnome-remote-desktop $CERT_DIR/*
      fi

      # Configure RDP
      ${pkgs.gnome-remote-desktop}/bin/grdctl --system rdp set-tls-key "$KEY_FILE"
      ${pkgs.gnome-remote-desktop}/bin/grdctl --system rdp set-tls-cert "$CRT_FILE"
      ${pkgs.gnome-remote-desktop}/bin/grdctl --system rdp enable

      # Only set credentials if not already set
      if ! ${pkgs.gnome-remote-desktop}/bin/grdctl rdp show | grep -q "username"; then
        ${pkgs.gnome-remote-desktop}/bin/grdctl rdp set-credentials "free" "a"
      fi
    '';
  };
  
  systemd.services.gnome-remote-desktop-permission = {
      description = "GNOME Remote Desktop File Permission";
      
      wantedBy = [ "multi-user.target" ];

      after = [
        "gnome-remote-desktop.service"
      ];

      requires = [
        "gnome-remote-desktop.service"
      ];

      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;

      };

      script = ''
        chown gnome-remote-desktop:gnome-remote-desktop /var/lib/gnome-remote-desktop -R
      '';
    };

}
