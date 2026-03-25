{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features.rdp {

  services.gnome.gnome-remote-desktop.enable = true;
  
  systemd.services.gnome-remote-desktop = { 
    wantedBy = [ "graphical.target" ]; # for starting the unit automatically at boot
  };
  
  services.displayManager.autoLogin.enable = lib.mkForce false;
  
  networking.firewall.allowedTCPPorts = [ 3389 ];

  environment.systemPackages = with pkgs; [
    freerdp
  ];

  systemd.services.gnome-remote-desktop-setup = {
    description = "Initialize GNOME Remote Desktop RDP TLS and config";
    wantedBy = [ "multi-user.target" ];
    after = [ "gnome-remote-desktop.service" ];

    serviceConfig = {
      Type = "oneshot";
      StateDirectory = "gnome-remote-desktop";
    };

    script = ''
      set -e

      CERT_DIR=/var/lib/gnome-remote-desktop
      KEY_FILE=$CERT_DIR/rdp-tls.key
      CRT_FILE=$CERT_DIR/rdp-tls.crt

      if [ ! -f "$KEY_FILE" ]; then
        echo "Generating RDP TLS certificate..."

        runuser -u gnome-remote-desktop -- \
          ${pkgs.freerdp}/bin/winpr-makecert -silent -rdp \
          -path "$CERT_DIR" rdp-tls
      else
        echo "TLS key already exists, skipping generation"
      fi

      # Always ensure config is set (safe to re-run)
      ${pkgs.gnome.gnome-remote-desktop}/bin/grdctl --system rdp set-tls-key "$KEY_FILE"
      ${pkgs.gnome.gnome-remote-desktop}/bin/grdctl --system rdp set-tls-cert "$CRT_FILE"
      ${pkgs.gnome.gnome-remote-desktop}/bin/grdctl --system rdp enable
      ${pkgs.gnome.gnome-remote-desktop}/bin/grdctl --system rdp set-credentials "free" "a"
    '';
  };
}
