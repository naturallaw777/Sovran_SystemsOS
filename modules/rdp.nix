{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features.rdp {

  services.gnome.gnome-remote-desktop.enable = true;

  networking.firewall.allowedTCPPorts = [ 3389 ];

  environment.systemPackages = with pkgs; [
    freerdp
  ];

  # gnome-remote-desktop ships a system service that needs to be explicitly enabled
  systemd.services.gnome-remote-desktop = {
    wantedBy = [ "graphical.target" ];
    after = [ "graphical.target" ];
    serviceConfig = {
      Restart = "on-failure";
      RestartSec = 5;
    };
  };

  # Configure RDP credentials and enable RDP mode on first boot
  systemd.services.gnome-remote-desktop-setup = {
    description = "Configure GNOME Remote Desktop RDP";
    wantedBy = [ "multi-user.target" ];
    before = [ "gnome-remote-desktop.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.gnome-remote-desktop ];
    script = ''
      # Enable RDP backend
      grdctl --system rdp enable

      # Disable requiring a prompt/handshake for unattended access
      grdctl --system rdp set-credentials sovran "$(cat /var/lib/gnome-remote-desktop/rdp-password 2>/dev/null || echo 'changeme')"

      # Generate a default password file if one doesn't exist
      if [ ! -f /var/lib/gnome-remote-desktop/rdp-password ]; then
        mkdir -p /var/lib/gnome-remote-desktop
        ${pkgs.openssl}/bin/openssl rand -base64 16 > /var/lib/gnome-remote-desktop/rdp-password
        chmod 600 /var/lib/gnome-remote-desktop/rdp-password
        echo "Generated new RDP password at /var/lib/gnome-remote-desktop/rdp-password"
      fi

      grdctl --system rdp set-credentials sovran "$(cat /var/lib/gnome-remote-desktop/rdp-password)"
    '';
  };
}
