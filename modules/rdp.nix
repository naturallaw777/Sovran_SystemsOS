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

  systemd.tmpfiles.rules = [
    "d /var/lib/gnome-remote-desktop 0750 gnome-remote-desktop gnome-remote-desktop -"
    "d /var/lib/gnome-remote-desktop/.local 0750 gnome-remote-desktop gnome-remote-desktop -"
    "d /var/lib/gnome-remote-desktop/.local/share 0750 gnome-remote-desktop gnome-remote-desktop -"
    "d /var/lib/gnome-remote-desktop/.local/share/gnome-remote-desktop 0750 gnome-remote-desktop gnome-remote-desktop -"
  ];

  systemd.services.gnome-remote-desktop-setup = {
    description = "Configure GNOME Remote Desktop RDP";
    wantedBy = [ "multi-user.target" ];
    before = [ "gnome-remote-desktop.service" ];
    after = [ "systemd-tmpfiles-setup.service" "network-online.target" ];
    wants = [ "network-online.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [
      pkgs.gnome-remote-desktop
      pkgs.polkit
      pkgs.openssl
      pkgs.hostname
      pkgs.gawk
    ];
    script = ''
      # Ensure directory structure exists
      mkdir -p /var/lib/gnome-remote-desktop/.local/share/gnome-remote-desktop
      chown -R gnome-remote-desktop:gnome-remote-desktop /var/lib/gnome-remote-desktop

      CRED_FILE="/var/lib/gnome-remote-desktop/rdp-credentials"
      PASSWORD=""

      # Generate password on first boot only
      if [ ! -f /var/lib/gnome-remote-desktop/rdp-password ]; then
        PASSWORD=$(openssl rand -base64 16)
        echo "$PASSWORD" > /var/lib/gnome-remote-desktop/rdp-password
        chmod 600 /var/lib/gnome-remote-desktop/rdp-password
      else
        PASSWORD=$(cat /var/lib/gnome-remote-desktop/rdp-password)
      fi

      # Get current IP address
      LOCAL_IP=$(hostname -I | awk '{print $1}')

      # Always rewrite the credentials file with the current IP
      cat > "$CRED_FILE" <<EOF
      ========================================
       GNOME Remote Desktop (RDP) Credentials
      ========================================

       Username: sovran
       Password: $PASSWORD

       Connect from any RDP client to:
         $LOCAL_IP:3389

      ========================================
      EOF

      chmod 600 "$CRED_FILE"

      # Enable RDP backend and set credentials
      grdctl --system rdp enable
      grdctl --system rdp set-credentials sovran "$PASSWORD"
    '';
  };
}
