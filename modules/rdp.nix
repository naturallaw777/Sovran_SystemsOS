{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features.rdp {

  services.gnome.gnome-remote-desktop.enable = true;

  networking.firewall.allowedTCPPorts = [ 3389 ];

  environment.systemPackages = with pkgs; [
    freerdp
  ];

  # The NixOS module installs the unit but doesn't enable it — we just need to start it and order it
  systemd.services.gnome-remote-desktop = {
    wantedBy = [ "graphical.target" ];
    after = [ "gnome-remote-desktop-setup.service" ];
    wants = [ "gnome-remote-desktop-setup.service" ];
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

      TLS_DIR="/var/lib/gnome-remote-desktop/tls"
      CRED_FILE="/var/lib/gnome-remote-desktop/rdp-credentials"

      # Generate TLS certificate if it doesn't exist
      if [ ! -f "$TLS_DIR/rdp-tls.crt" ]; then
        mkdir -p "$TLS_DIR"
        openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
          -sha256 -nodes -days 3650 \
          -keyout "$TLS_DIR/rdp-tls.key" \
          -out "$TLS_DIR/rdp-tls.crt" \
          -subj "/CN=gnome-remote-desktop"
        chown -R gnome-remote-desktop:gnome-remote-desktop "$TLS_DIR"
        chmod 600 "$TLS_DIR/rdp-tls.key"
        chmod 644 "$TLS_DIR/rdp-tls.crt"
        echo "Generated RDP TLS certificate"
      fi

      # Configure TLS certificate
      grdctl --system rdp set-tls-cert "$TLS_DIR/rdp-tls.crt"
      grdctl --system rdp set-tls-key "$TLS_DIR/rdp-tls.key"

      # Generate password on first boot only
      PASSWORD=""
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

      echo "GNOME Remote Desktop RDP configured successfully"
    '';
  };
}
