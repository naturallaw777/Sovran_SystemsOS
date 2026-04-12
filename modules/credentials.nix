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
    # Delete the old GNOME Keyring so it is recreated with the new password on next GDM login.
    rm -rf /home/free/.local/share/keyrings/*
    echo "GNOME Keyring files cleared — a fresh keyring will be created on next login."
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
    path = [ pkgs.shadow pkgs.coreutils ];
    script = ''
      SECRET_FILE="/var/lib/secrets/root-password"
      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p /var/lib/secrets
        # Generate a diceware-style passphrase: word-word-word-N
        WORDS="apple barn brook cabin cedar cloud coral crane delta eagle ember \
               fern field flame flora flint frost grove haven hedge holly heron \
               jade juniper kelp larch lemon lilac linden loch lotus maple marsh \
               meadow mist mossy mount oak ocean olive petal pine pixel plum pond \
               prism quartz raven ridge river robin rocky rose rowan sage sand \
               sierra silver slate snow solar spark spruce stone storm summit \
               swift thorn tide timber torch trout vale vault vine walnut wave \
               willow wren amber aspen birch blaze bloom bluff coast copper crest \
               dune elder fjord forge glade glen glow gulf"
        WORD_ARRAY=($WORDS)
        COUNT=''${#WORD_ARRAY[@]}
        W1=''${WORD_ARRAY[$((RANDOM % COUNT))]}
        W2=''${WORD_ARRAY[$((RANDOM % COUNT))]}
        W3=''${WORD_ARRAY[$((RANDOM % COUNT))]}
        DIGIT=$((RANDOM % 10))
        ROOT_PASS="$W1-$W2-$W3-$DIGIT"
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
    path = [ pkgs.shadow pkgs.coreutils ];
    script = ''
      SECRET_FILE="/var/lib/secrets/free-password"
      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p /var/lib/secrets
        # Generate a diceware-style passphrase: word-word-word-N
        WORDS="apple barn brook cabin cedar cloud coral crane delta eagle ember \
               fern field flame flora flint frost grove haven hedge holly heron \
               jade juniper kelp larch lemon lilac linden loch lotus maple marsh \
               meadow mist mossy mount oak ocean olive petal pine pixel plum pond \
               prism quartz raven ridge river robin rocky rose rowan sage sand \
               sierra silver slate snow solar spark spruce stone storm summit \
               swift thorn tide timber torch trout vale vault vine walnut wave \
               willow wren amber aspen birch blaze bloom bluff coast copper crest \
               dune elder fjord forge glade glen glow gulf"
        WORD_ARRAY=($WORDS)
        COUNT=''${#WORD_ARRAY[@]}
        W1=''${WORD_ARRAY[$((RANDOM % COUNT))]}
        W2=''${WORD_ARRAY[$((RANDOM % COUNT))]}
        W3=''${WORD_ARRAY[$((RANDOM % COUNT))]}
        DIGIT=$((RANDOM % 10))
        FREE_PASS="$W1-$W2-$W3-$DIGIT"
        echo "free:$FREE_PASS" | chpasswd
        echo "$FREE_PASS" > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
      fi
    '';
  };

}
