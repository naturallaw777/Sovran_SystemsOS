{ config, lib, pkgs, ... }:

lib.mkIf config.sovran_systemsOS.features.rdp {

  users.users.gnome-remote-desktop = {
    isSystemUser = true;
    group = "gnome-remote-desktop";
    home = "/var/lib/gnome-remote-desktop";
    createHome = true;
  };
  users.groups.gnome-remote-desktop = {};

  # Enable the GNOME Remote Desktop service at the system level
  services.gnome.gnome-remote-desktop.enable = true;

  # Open RDP port in the firewall
  networking.firewall.allowedTCPPorts = [ 3389 ];

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

      # Regenerate TLS certificate if missing OR if ownership is wrong
      # (disable/re-enable cycle can break ownership or grdctl state)
      NEED_REGEN=0
      if [ ! -f "$TLS_DIR/rdp-tls.crt" ] || [ ! -f "$TLS_DIR/rdp-tls.key" ]; then
        NEED_REGEN=1
      elif [ "$(stat -c '%U' "$TLS_DIR/rdp-tls.key" 2>/dev/null)" != "gnome-remote-desktop" ]; then
        NEED_REGEN=1
      fi

      if [ "$NEED_REGEN" = "1" ]; then
        mkdir -p "$TLS_DIR"
        rm -f "$TLS_DIR/rdp-tls.key" "$TLS_DIR/rdp-tls.crt"
        openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
          -sha256 -nodes -days 3650 \
          -keyout "$TLS_DIR/rdp-tls.key" \
          -out "$TLS_DIR/rdp-tls.crt" \
          -subj "/CN=gnome-remote-desktop"
        echo "Generated new RDP TLS certificate"
      fi

      # Always fix ownership and permissions (handles re-enable after disable)
      chown -R gnome-remote-desktop:gnome-remote-desktop "$TLS_DIR"
      chmod 600 "$TLS_DIR/rdp-tls.key"
      chmod 644 "$TLS_DIR/rdp-tls.crt"

      # Configure TLS certificate
      grdctl --system rdp set-tls-cert "$TLS_DIR/rdp-tls.crt"
      grdctl --system rdp set-tls-key "$TLS_DIR/rdp-tls.key"

      # Generate password on first boot only
      PASSWORD=""
      if [ ! -f /var/lib/gnome-remote-desktop/rdp-password ]; then
        PASSWORD=$(openssl rand -base64 16)
        echo "$PASSWORD" > /var/lib/gnome-remote-desktop/rdp-password
      else
        PASSWORD=$(cat /var/lib/gnome-remote-desktop/rdp-password)
      fi
      chown root:gnome-remote-desktop /var/lib/gnome-remote-desktop/rdp-password
      chmod 640 /var/lib/gnome-remote-desktop/rdp-password

      # Write username to a separate file for the hub
      echo "sovran" > /var/lib/gnome-remote-desktop/rdp-username
      chown root:gnome-remote-desktop /var/lib/gnome-remote-desktop/rdp-username
      chmod 640 /var/lib/gnome-remote-desktop/rdp-username

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

      # Disable the system-level RDP endpoint so connections go through the user session
      grdctl --system rdp disable || true

      echo "GNOME Remote Desktop RDP configured successfully"
    '';
  };

  # User-level service that enables RDP screen sharing within the free user's graphical session.
  # This avoids the GDM "Session Already Running" conflict caused by the system-level RDP endpoint.
  systemd.user.services.gnome-remote-desktop-session = {
    description = "Enable GNOME Remote Desktop screen sharing for user session";
    wantedBy = [ "graphical-session.target" ];
    after = [ "graphical-session.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [
      pkgs.gnome-remote-desktop
    ];
    script = ''
      # Read the password generated by the system-level setup service.
      # Wait for the password file to be available (system service may still be running).
      for i in $(seq 1 30); do
        [ -f /var/lib/gnome-remote-desktop/rdp-password ] && break
        sleep 1
      done

      if [ ! -f /var/lib/gnome-remote-desktop/rdp-password ]; then
        echo "ERROR: Timed out waiting for RDP password file"
        exit 1
      fi

      PASSWORD=$(cat /var/lib/gnome-remote-desktop/rdp-password 2>/dev/null || echo "")
      if [ -z "$PASSWORD" ]; then
        echo "ERROR: RDP password file is empty"
        exit 1
      fi

      # Enable RDP in the user session (screen sharing mode — takes over existing desktop)
      grdctl rdp enable
      grdctl rdp set-credentials sovran "$PASSWORD"
      grdctl rdp disable-view-only || true

      echo "GNOME Remote Desktop user-session screen sharing enabled"
    '';
  };

  # Add free user to gnome-remote-desktop group so the user-level service can read credential files
  users.users.free.extraGroups = [ "gnome-remote-desktop" ];
}
