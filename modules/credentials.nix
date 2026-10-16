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
}
