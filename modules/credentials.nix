{ config, pkgs, lib, ... }:

let
  # ── Helper: change 'free' password and save it ─────────────
  change-free-password = pkgs.writeShellScriptBin "change-free-password" ''
    set -euo pipefail
    SECRET_FILE="/var/lib/secrets/free-password"

    if [ "$(id -u)" -ne 0 ]; then
      echo "Error: must be run as root (use sudo)." >&2
      exit 1
    fi

    echo -n "New password for free: "
    read -rs NEW_PASS
    echo
    echo -n "Confirm password: "
    read -rs CONFIRM
    echo

    if [ "$NEW_PASS" != "$CONFIRM" ]; then
      echo "Passwords do not match." >&2
      exit 1
    fi

    if [ -z "$NEW_PASS" ]; then
      echo "Password cannot be empty." >&2
      exit 1
    fi

    echo "free:$NEW_PASS" | ${pkgs.shadow}/bin/chpasswd
    mkdir -p /var/lib/secrets
    echo "$NEW_PASS" > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE"
    echo "Password for 'free' updated and saved."
    echo "$NEW_PASS" | ${pkgs.gnome-keyring}/bin/gnome-keyring-daemon --unlock || echo "Warning: GNOME Keyring re-key failed." >&2
    echo "GNOME Keyring re-keyed with new password."
  '';
in
{
  # ── Make helper available system-wide ───────────────────────
  environment.systemPackages = [ change-free-password ];

  # ── Shell aliases: intercept 'passwd free' ─────────────────
  programs.bash.interactiveShellInit = ''
    passwd() {
      if [ "$1" = "free" ]; then
        echo ""
        echo "╔══════════════════════════════════════════════════════╗"
        echo "║  ⚠  Use 'sudo change-free-password' instead.       ║"
        echo "║                                                      ║"
        echo "║  'passwd free' only updates /etc/shadow.             ║"
        echo "║  The Hub credentials view will NOT be updated.       ║"
        echo "╚══════════════════════════════════════════════════════╝"
        echo ""
        return 1
      fi
      command passwd "$@"
    }
  '';

  programs.fish.interactiveShellInit = ''
    function passwd --wraps passwd
      if test "$argv[1]" = "free"
        echo ""
        echo "╔══════════════════════════════════════════════════════╗"
        echo "║  ⚠  Use 'sudo change-free-password' instead.       ║"
        echo "║                                                      ║"
        echo "║  'passwd free' only updates /etc/shadow.             ║"
        echo "║  The Hub credentials view will NOT be updated.       ║"
        echo "╚════════════════════════════��═════════════════════════╝"
        echo ""
        return 1
      end
      command passwd $argv
    end
  '';

  # ── 1. Auto-Generate Root Password (Runs once) ─────────────
  systemd.services.root-password-setup = {
    description = "Generate and set a random root password";
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.pwgen pkgs.shadow pkgs.coreutils ];
    script = ''
      SECRET_FILE="/var/lib/secrets/root-password"
      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p /var/lib/secrets
        ROOT_PASS=$(pwgen -s 20 1)
        echo "root:$ROOT_PASS" | chpasswd
        echo "$ROOT_PASS" > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
      fi
    '';
  };

  # ── 1b. Generate random 'free' password on first boot ──────
  systemd.services.free-password-setup = {
    description = "Generate and set a random 'free' user password";
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.pwgen pkgs.shadow pkgs.coreutils ];
    script = ''
      SECRET_FILE="/var/lib/secrets/free-password"
      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p /var/lib/secrets
        FREE_PASS=$(pwgen -s 20 1)
        echo "free:$FREE_PASS" | chpasswd
        echo "$FREE_PASS" > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
      fi
    '';
  };

  # ── 2. Unlock GNOME Keyring on graphical session start ─────
  systemd.services.gnome-keyring-unlock = {
    description = "Unlock GNOME Keyring with stored free password";
    after = [ "free-password-setup.service" "display-manager.service" ];
    wants = [ "free-password-setup.service" ];
    wantedBy = [ "graphical-session.target" ];
    serviceConfig = {
      Type = "oneshot";
      User = "free";
      ExecStartPre = "${pkgs.coreutils}/bin/sleep 3";
    };
    path = [ pkgs.gnome-keyring pkgs.coreutils ];
    script = ''
      SECRET_FILE="/var/lib/secrets/free-password"
      if [ -f "$SECRET_FILE" ]; then
        gnome-keyring-daemon --unlock < "$SECRET_FILE"
        echo "GNOME Keyring unlocked with stored password."
      else
        echo "No password file found, skipping keyring unlock."
      fi
    '';
  };

}
