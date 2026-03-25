{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features.rdp {

  services.gnome.gnome-remote-desktop.enable = true;

  networking.firewall.allowedTCPPorts = [ 3389 ];

  environment.systemPackages = with pkgs; [
    freerdp
  ];

  systemd.services.gnome-remote-desktop = {
    wantedBy = [ "graphical.target" ];
    after = [ "graphical.target" ];
    serviceConfig = {
      Restart = "on-failure";
      RestartSec = 5;
    };
  };

  systemd.services.gnome-remote-desktop-setup = {
    description = "Configure GNOME Remote Desktop RDP";
    wantedBy = [ "multi-user.target" ];
    before = [ "gnome-remote-desktop.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [
      pkgs.gnome-remote-desktop
      pkgs.polkit
      pkgs.openssl
    ];
    script = ''
      # Generate a default password file if one doesn't exist
      if [ ! -f /var/lib/gnome-remote-desktop/rdp-password ]; then
        mkdir -p /var/lib/gnome-remote-desktop
        openssl rand -base64 16 > /var/lib/gnome-remote-desktop/rdp-password
        chmod 600 /var/lib/gnome-remote-desktop/rdp-password
        echo "Generated new RDP password at /var/lib/gnome-remote-desktop/rdp-password"
      fi

      # Enable RDP backend and set credentials
      grdctl --system rdp enable
      grdctl --system rdp set-credentials sovran "$(cat /var/lib/gnome-remote-desktop/rdp-password)"
    '';
  };
}
