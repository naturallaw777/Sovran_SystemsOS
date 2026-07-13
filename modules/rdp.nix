{ config, lib, pkgs, ... }:

lib.mkIf config.sovran_systemsOS.features.rdp {

  # Enable the GNOME Remote Desktop service at the system level
  services.gnome.gnome-remote-desktop.enable = true;

  # Open RDP port in the firewall
  networking.firewall.allowedTCPPorts = [ 3389 ];

  # Ensure the service only starts after setup succeeds
  systemd.services.gnome-remote-desktop = {
    wantedBy = [ "graphical.target" ];
    after = [ "gnome-remote-desktop-setup.service" ];
    requires = [ "gnome-remote-desktop-setup.service" ];
  };

  systemd.tmpfiles.rules = [
    "d /var/lib/gnome-remote-desktop/.local 0700 gnome-remote-desktop gnome-remote-desktop -"
    "d /var/lib/gnome-remote-desktop/.local/share 0700 gnome-remote-desktop gnome-remote-desktop -"
    "d /var/lib/gnome-remote-desktop/.local/share/gnome-remote-desktop 0700 gnome-remote-desktop gnome-remote-desktop -"
    "d /var/lib/gnome-remote-desktop/tls 0700 gnome-remote-desktop gnome-remote-desktop -"
  ];

  systemd.services.gnome-remote-desktop-setup = {
    description = "Configure GNOME Remote Desktop RDP";
    wantedBy = [ "graphical.target" ];
    before = [ "gnome-remote-desktop.service" ];
    after = [
      "dbus.service"
      "systemd-tmpfiles-setup.service"
      "network-online.target"
      "gnome-remote-desktop-configuration.service"
    ];
    wants = [
      "network-online.target"
      "gnome-remote-desktop-configuration.service"
    ];
    serviceConfig = {
      Type = "oneshot";
      TimeoutStartSec = "2min";
    };
    path = [
      pkgs.coreutils
      pkgs.gawk
      pkgs.gnome-remote-desktop
      pkgs.hostname
      pkgs.openssl
      pkgs.polkit
      pkgs.systemd
      pkgs.util-linux
    ];
    script = ''
      set -euo pipefail

      STATE_DIR="/var/lib/gnome-remote-desktop"
      TLS_DIR="$STATE_DIR/tls"
      USERNAME_FILE="$STATE_DIR/rdp-username"
      PASSWORD_FILE="$STATE_DIR/rdp-password"
      CRED_FILE="$STATE_DIR/rdp-credentials"
      DEFAULT_USERNAME="sovran"

      grdctl_system() {
        local rc=0

        if timeout --kill-after=5s 10s \
          runuser -u gnome-remote-desktop -- \
          grdctl --system "$@"; then
          return 0
        else
          rc=$?
        fi

        if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
          echo "grdctl command timed out: $*" >&2
        fi
        echo "grdctl command failed (exit $rc): $*" >&2

        return "$rc"
      }

      mkdir -p "$STATE_DIR/.local/share/gnome-remote-desktop" "$TLS_DIR"
      chown -R gnome-remote-desktop:gnome-remote-desktop "$STATE_DIR"
      chmod 700 \
        "$STATE_DIR" \
        "$STATE_DIR/.local" \
        "$STATE_DIR/.local/share" \
        "$STATE_DIR/.local/share/gnome-remote-desktop" \
        "$TLS_DIR"

      NEED_REGEN=0
      if [ ! -f "$TLS_DIR/rdp-tls.crt" ] || [ ! -f "$TLS_DIR/rdp-tls.key" ]; then
        NEED_REGEN=1
      elif [ "$(stat -c '%U:%G' "$TLS_DIR/rdp-tls.key" 2>/dev/null)" != "gnome-remote-desktop:gnome-remote-desktop" ]; then
        NEED_REGEN=1
      fi

      if [ "$NEED_REGEN" = "1" ]; then
        rm -f "$TLS_DIR/rdp-tls.key" "$TLS_DIR/rdp-tls.crt"
        openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
          -sha256 -nodes -days 3650 \
          -keyout "$TLS_DIR/rdp-tls.key" \
          -out "$TLS_DIR/rdp-tls.crt" \
          -subj "/CN=gnome-remote-desktop"
        echo "Generated new RDP TLS certificate"
      fi

      chown gnome-remote-desktop:gnome-remote-desktop "$TLS_DIR/rdp-tls.key" "$TLS_DIR/rdp-tls.crt"
      chmod 600 "$TLS_DIR/rdp-tls.key"
      chmod 644 "$TLS_DIR/rdp-tls.crt"

      if [ ! -f "$USERNAME_FILE" ]; then
        printf '%s\n' "$DEFAULT_USERNAME" > "$USERNAME_FILE"
      fi
      USERNAME="$(tr -d '\n' < "$USERNAME_FILE")"
      if [ -z "$USERNAME" ]; then
        USERNAME="$DEFAULT_USERNAME"
        printf '%s\n' "$USERNAME" > "$USERNAME_FILE"
      fi
      if [ "''${#USERNAME}" -gt 32 ]; then
        echo "RDP username is too long (''${#USERNAME} characters, maximum 32): $USERNAME from $USERNAME_FILE" >&2
        exit 1
      fi
      case "$USERNAME" in
        [A-Za-z_][A-Za-z0-9_-]*)
          ;;
        *)
          echo "RDP username must start with a letter or underscore and contain only letters, numbers, underscores, and hyphens: $USERNAME from $USERNAME_FILE" >&2
          exit 1
          ;;
      esac
      chown gnome-remote-desktop:gnome-remote-desktop "$USERNAME_FILE"
      chmod 600 "$USERNAME_FILE"

      if [ ! -f "$PASSWORD_FILE" ]; then
        openssl rand -base64 16 > "$PASSWORD_FILE"
      fi
      PASSWORD="$(tr -d '\n' < "$PASSWORD_FILE")"
      if [ -z "$PASSWORD" ]; then
        echo "RDP password file is empty: $PASSWORD_FILE" >&2
        exit 1
      fi
      if [ "''${#PASSWORD}" -lt 8 ]; then
        echo "RDP password is too short (''${#PASSWORD} characters, minimum 8): $PASSWORD_FILE" >&2
        exit 1
      fi
      chown gnome-remote-desktop:gnome-remote-desktop "$PASSWORD_FILE"
      chmod 600 "$PASSWORD_FILE"

      LOCAL_IP="$(hostname -I | awk '{print $1}')"
      if [ -z "$LOCAL_IP" ]; then
        LOCAL_IP="127.0.0.1"
      fi

      cat > "$CRED_FILE" <<EOF
      ========================================
       GNOME Remote Desktop (RDP) Credentials
      ========================================

       Username: $USERNAME
       Password: $PASSWORD

       Connect from any RDP client to:
         $LOCAL_IP:3389

      ========================================
      EOF

      chown gnome-remote-desktop:gnome-remote-desktop "$CRED_FILE"
      chmod 600 "$CRED_FILE"

      grdctl_system rdp enable
      grdctl_system rdp set-tls-cert "$TLS_DIR/rdp-tls.crt"
      grdctl_system rdp set-tls-key "$TLS_DIR/rdp-tls.key"
      grdctl_system rdp set-credentials "$USERNAME" "$PASSWORD"

      echo "GNOME Remote Desktop RDP configured successfully"
    '';
  };
}
