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
    # Delete the old GNOME Keyring databases so a fresh one is created on next GDM login.
    rm -f /home/free/.local/share/keyrings/*.keyring
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
      set -euo pipefail
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
        echo "$ROOT_PASS" > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
      fi
      # If the file contains a scrypt hash (salt:hash), skip chpasswd — the
      # password was already set via the Hub security reset endpoint and this
      # service is only re-running as a manual recovery step.
      CONTENT="$(cat "$SECRET_FILE")"
      if echo "$CONTENT" | grep -qE '^[0-9a-f]{32}:[0-9a-f]{64,}$'; then
        echo "root-password-setup: stored value is already hashed — skipping chpasswd" >&2
      else
        echo "root:$CONTENT" | chpasswd
      fi
    '';
  };

  # ── 1b. Generate random 'free' password on first boot ──────
  systemd.services.free-password-setup = {
    description = "Generate and set a random 'free' user password";
    wantedBy = [ "multi-user.target" ];
    before = [ "display-manager.service" ];
    after = [ "systemd-user-sessions.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.shadow pkgs.coreutils ];
    script = ''
      set -euo pipefail
      SECRET_FILE="/var/lib/secrets/free-password"
      PENDING_FILE="/var/lib/secrets/free-password-migration-pending"

      if [ -f "$SECRET_FILE" ]; then
        echo "free:$(cat "$SECRET_FILE")" | chpasswd
        exit 0
      fi

      SHADOW_HASH=""
      while IFS=: read -r user hash _; do
        if [ "$user" = "free" ]; then
          SHADOW_HASH="$hash"
          break
        fi
      done < /etc/shadow

      HAS_REAL_HASH=0
      case "$SHADOW_HASH" in
        ""|"!"|"*"|"!!"|"!"*|"*"*)
          HAS_REAL_HASH=0
          ;;
        *)
          HAS_REAL_HASH=1
          ;;
      esac

      if [ "$HAS_REAL_HASH" -eq 1 ]; then
        mkdir -p /var/lib/secrets
        touch "$PENDING_FILE"
        chmod 600 "$PENDING_FILE"
        exit 0
      fi

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
      echo "$FREE_PASS" > "$SECRET_FILE"
      chmod 600 "$SECRET_FILE"
      echo "free:$FREE_PASS" | chpasswd
    '';
  };

  systemd.services.free-password-migration = {
    description = "Generate and set 'free' password for migrated machines";
    wantedBy = [ "multi-user.target" ];
    before = [ "display-manager.service" ];
    after = [ "systemd-user-sessions.service" "free-password-setup.service" ];
    requires = [ "free-password-setup.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.shadow pkgs.coreutils ];
    script = ''
      set -euo pipefail

      PENDING_FILE="/var/lib/secrets/free-password-migration-pending"
      SECRET_FILE="/var/lib/secrets/free-password"
      NEWPASS_FILE="/var/lib/secrets/free-password-migration-newpass"

      [ -f "$PENDING_FILE" ] || exit 0

      mkdir -p /var/lib/secrets

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

      printf '%s\n' "$FREE_PASS" > "$SECRET_FILE"
      chmod 600 "$SECRET_FILE"

      printf '%s\n' "$FREE_PASS" > "$NEWPASS_FILE"
      chmod 600 "$NEWPASS_FILE"
      rm -f "$PENDING_FILE"
    '';
  };

}
