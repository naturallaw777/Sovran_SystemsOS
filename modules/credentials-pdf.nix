{ config, pkgs, lib, ... }:

let
  fonts = pkgs.liberation_ttf;

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
        echo "║  The Hub and Magic Keys PDF will NOT be updated.     ║"
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
        echo "║  The Hub and Magic Keys PDF will NOT be updated.     ║"
        echo "╚════════════════════════════════════════��═════════════╝"
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

  # ── 1b. Save 'free' password on first boot ─────────────────
  systemd.services.free-password-setup = {
    description = "Save the initial 'free' user password";
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.coreutils ];
    script = ''
      SECRET_FILE="/var/lib/secrets/free-password"
      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p /var/lib/secrets
        echo "free" > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
      fi
    '';
  };

  # ── 2. Timer: Check every 5 minutes ────────────────────────
  systemd.timers.generate-credentials-pdf = {
    description = "Periodically check if Magic Keys PDF needs regenerating";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "30s";
      OnUnitActiveSec = "5min";
      Unit = "generate-credentials-pdf.service";
    };
  };

  # ── 3. Generate the Magic Keys PDF ─────────────────────────
  systemd.services.generate-credentials-pdf = {
    description = "Generate Magic Keys PDF for Sovran_SystemsOS";
    serviceConfig = {
      Type = "oneshot";
    };

    path = [
      pkgs.pandoc
      pkgs.typst
      pkgs.coreutils
      pkgs.qrencode
      pkgs.gnugrep
      fonts
      "/run/current-system/sw"
    ];

    environment = {
      TYPST_FONT_PATHS = "${fonts}/share/fonts";
    };

    script = ''
      DOC_DIR="/home/free/Documents"
      OUTPUT="$DOC_DIR/Sovran_SystemsOS_Magic_Keys.pdf"
      WORK_DIR="/tmp/magic_keys_build"
      FILE="$WORK_DIR/magic_keys.md"
      HASH_FILE="/var/lib/secrets/.magic-keys-hash"

      FENCE='```'

      # ── Collect all secret sources into a single hash ──
      SECRET_SOURCES=""
      for f in \
        /var/lib/secrets/root-password \
        /var/lib/secrets/free-password \
        /etc/nix-bitcoin-secrets/rtl-password \
        /var/lib/tor/onion/rtl/hostname \
        /var/lib/tor/onion/electrs/hostname \
        /var/lib/tor/onion/bitcoind/hostname \
        /var/lib/secrets/matrix-users \
        /var/lib/gnome-remote-desktop/rdp-credentials \
        /var/lib/secrets/nextcloud-admin \
        /var/lib/secrets/wordpress-admin \
        /var/lib/secrets/vaultwarden/vaultwarden.env \
        /var/lib/domains/vaultwarden \
        /var/lib/domains/btcpayserver; do
        if [ -f "$f" ]; then
          SECRET_SOURCES="$SECRET_SOURCES$(cat "$f")"
        fi
      done

      # Add lndconnect URL to hash sources (changes if certs/macaroons rotate)
      if command -v lndconnect >/dev/null 2>&1; then
        SECRET_SOURCES="$SECRET_SOURCES$(lndconnect --url 2>/dev/null || true)"
      elif command -v lnconnect-clnrest >/dev/null 2>&1; then
        SECRET_SOURCES="$SECRET_SOURCES$(lnconnect-clnrest --url 2>/dev/null || true)"
      fi

      CURRENT_HASH=$(echo -n "$SECRET_SOURCES" | sha256sum | cut -d' ' -f1)
      OLD_HASH=""
      if [ -f "$HASH_FILE" ]; then
        OLD_HASH=$(cat "$HASH_FILE")
      fi

      # ── Skip if PDF exists and nothing changed ──
      if [ -f "$OUTPUT" ] && [ "$CURRENT_HASH" = "$OLD_HASH" ]; then
        echo "No changes detected, skipping PDF regeneration."
        exit 0
      fi

      echo "Changes detected (or PDF missing), regenerating..."
      mkdir -p "$DOC_DIR" "$WORK_DIR"

      # ── Read secrets (default to placeholder if missing) ──
      read_secret() { if [ -f "$1" ]; then cat "$1"; else echo "$2"; fi; }

      ROOT_PASS=$(read_secret /var/lib/secrets/root-password "Generating...")
      FREE_PASS=$(read_secret /var/lib/secrets/free-password "free")
      RTL_PASS=$(read_secret /etc/nix-bitcoin-secrets/rtl-password "Not found")
      RTL_ONION=$(read_secret /var/lib/tor/onion/rtl/hostname "Not generated yet")
      ELECTRS_ONION=$(read_secret /var/lib/tor/onion/electrs/hostname "Not generated yet")
      BITCOIN_ONION=$(read_secret /var/lib/tor/onion/bitcoind/hostname "Not generated yet")

      # ── Generate Zeus QR code PNG if lndconnect URL is available ──
      ZEUS_URL=""
      HAS_ZEUS_QR=""
      if command -v lndconnect >/dev/null 2>&1; then
        ZEUS_URL=$(lndconnect --url 2>/dev/null || true)
      elif command -v lnconnect-clnrest >/dev/null 2>&1; then
        ZEUS_URL=$(lnconnect-clnrest --url 2>/dev/null || true)
      fi

      if [ -n "$ZEUS_URL" ]; then
        qrencode -o "$WORK_DIR/zeus-qr.png" -s 4 -m 1 -l H "$ZEUS_URL" 2>/dev/null && HAS_ZEUS_QR="1"
      fi

      # ── Build the Markdown document ──
      cat > "$FILE" << ENDOFFILE
---
title: "Sovran SystemsOS Magic Keys"
---

# Your Sovran SystemsOS Magic Keys! 🗝️

Welcome to your new computer! We have built a lot of cool secret forts (services) for you. To get into your forts, you need your magic keys (passwords).

Here are all of your keys in one place. **Keep this document safe and do not share it with strangers!**

> **How this document works:** This PDF is automatically generated by your computer. If any of your passwords, services, or connection details change, this document will automatically update itself within a few minutes. You can always find the latest version right here in your Documents folder. If you accidentally delete it, don't worry — your computer will recreate it for you!

## 🖥️ Your Computer
These are the master keys to the actual machine.

### 1. Main Screen Unlock (The 'free' account)
When you turn the computer on, it usually logs you in automatically. However, if the screen goes to sleep, or **if you enable Remote Desktop (RDP)**, you will need this to log in:
- **Username:** \`free\`
- **Password:** \`$FREE_PASS\`

🚨 **VERY IMPORTANT:** You MUST write this password down and keep it safe! If you lose it, you will be locked out of your computer!

### 2. The Big Boss (Root)
Sometimes a pop-up box might ask for an Administrator (Root) password to change a setting. We created a super-secret password just for this!
- **Root Password:** \`$ROOT_PASS\`

### 3. The Hacker Terminal (\`ssh root@localhost\`)
Because your main account is so safe, you cannot just type normal commands to become the boss. If you open a black terminal box and want to make big changes, you must use your special factory key!

Type this exact command into the terminal:
\`ssh root@localhost\`

When it asks for a passphrase, type:
- **Terminal Password:** \`gosovransystems\`
ENDOFFILE

      # --- BITCOIN ECOSYSTEM ---
      if [ -f "/etc/nix-bitcoin-secrets/rtl-password" ] || [ -f "/var/lib/tor/onion/rtl/hostname" ]; then
        cat >> "$FILE" << BITCOIN

## ⚡ Your Bitcoin & Lightning Node
Your computer is a real Bitcoin node! It talks to the network secretly using Tor. Here is how to connect your wallet apps to it:

### 1. Ride The Lightning (RTL)
*This is the control panel for your Lightning Node.*
Open the **Tor Browser** and go to this website. Use this password to log in:
- **Website:** \`http://$RTL_ONION\`
- **Password:** \`$RTL_PASS\`

### 2. Electrs (Your Private Bank Teller)
*If you use a wallet app on your phone or computer (like Sparrow or BlueWallet), tell it to connect here so nobody can spy on your money!*
- **Tor Address:** \`$ELECTRS_ONION\`
- **Port:** \`50001\`

### 3. Bitcoin Core
*This is the heartbeat of your node. It uses this address to talk to other Bitcoiners securely.*
- **Tor Address:** \`$BITCOIN_ONION\`
BITCOIN
      fi

      # --- ZEUS MOBILE WALLET QR CODE ---
      if [ "$HAS_ZEUS_QR" = "1" ]; then
        echo "" >> "$FILE"
        echo "## 📱 Connect Zeus Mobile Wallet" >> "$FILE"
        echo "" >> "$FILE"
        echo "Take your Bitcoin Lightning node anywhere in the world! Scan this QR code with the **Zeus** app on your phone to instantly connect your mobile wallet to your Lightning node." >> "$FILE"
        echo "" >> "$FILE"
        echo "1. Download **Zeus** from the App Store or Google Play" >> "$FILE"
        echo "2. Open Zeus and tap **\"Scan Node Config\"**" >> "$FILE"
        echo "3. Point your phone's camera at this QR code:" >> "$FILE"
        echo "" >> "$FILE"
        echo "![Zeus Connection QR Code](zeus-qr.png){ width=200px }" >> "$FILE"
        echo "" >> "$FILE"
        echo "That's it! You're now mobile. Send and receive Bitcoin anywhere in the world, powered by your very own node! ⚡" >> "$FILE"
      elif [ -n "$ZEUS_URL" ]; then
        echo "" >> "$FILE"
        echo "## 📱 Connect Zeus Mobile Wallet" >> "$FILE"
        echo "" >> "$FILE"
        echo "Take your Bitcoin Lightning node anywhere in the world! Paste this connection URL into the **Zeus** app on your phone:" >> "$FILE"
        echo "" >> "$FILE"
        echo "1. Download **Zeus** from the App Store or Google Play" >> "$FILE"
        echo "2. Open Zeus and tap **\"Scan Node Config\"** then **\"Paste Node Config\"**" >> "$FILE"
        echo "3. Paste this URL:" >> "$FILE"
        echo "" >> "$FILE"
        echo "$FENCE" >> "$FILE"
        echo "$ZEUS_URL" >> "$FILE"
        echo "$FENCE" >> "$FILE"
        echo "" >> "$FILE"
        echo "That's it! You're now mobile. Send and receive Bitcoin anywhere in the world, powered by your very own node! ⚡" >> "$FILE"
      fi

      # --- MATRIX / ELEMENT ---
      if [ -f "/var/lib/secrets/matrix-users" ]; then
        echo "" >> "$FILE"
        echo "## 💬 Your Private Chat (Matrix / Element)" >> "$FILE"
        echo "This is your very own private messaging app! Log in using an app like Element with these details:" >> "$FILE"
        echo "$FENCE" >> "$FILE"
        cat /var/lib/secrets/matrix-users >> "$FILE"
        echo "$FENCE" >> "$FILE"
      fi

      # --- GNOME RDP ---
      if [ -f "/var/lib/gnome-remote-desktop/rdp-credentials" ]; then
        echo "" >> "$FILE"
        echo "## 🌎 Connect from Far Away (Remote Desktop)" >> "$FILE"
        echo "This lets you control your computer screen from another device!" >> "$FILE"
        echo "$FENCE" >> "$FILE"
        cat /var/lib/gnome-remote-desktop/rdp-credentials >> "$FILE"
        echo "$FENCE" >> "$FILE"
      fi

      # --- NEXTCLOUD ---
      if [ -f "/var/lib/secrets/nextcloud-admin" ]; then
        echo "" >> "$FILE"
        echo "## ☁️ Your Personal Cloud (Nextcloud)" >> "$FILE"
        echo "This is like your own private Google Drive!" >> "$FILE"
        echo "$FENCE" >> "$FILE"
        cat /var/lib/secrets/nextcloud-admin >> "$FILE"
        echo "$FENCE" >> "$FILE"
      fi

      # --- WORDPRESS ---
      if [ -f "/var/lib/secrets/wordpress-admin" ]; then
        echo "" >> "$FILE"
        echo "## 📝 Your Website (WordPress)" >> "$FILE"
        echo "This is your very own website where you can write blogs or make pages." >> "$FILE"
        echo "$FENCE" >> "$FILE"
        cat /var/lib/secrets/wordpress-admin >> "$FILE"
        echo "$FENCE" >> "$FILE"
      fi

      # --- VAULTWARDEN ---
      if [ -f "/var/lib/domains/vaultwarden" ]; then
        DOMAIN=$(cat /var/lib/domains/vaultwarden)
        VW_ADMIN_TOKEN="Not found"
        if [ -f "/var/lib/secrets/vaultwarden/vaultwarden.env" ]; then
          VW_ADMIN_TOKEN=$(grep -oP 'ADMIN_TOKEN=\K.*' /var/lib/secrets/vaultwarden/vaultwarden.env || echo "Not found")
        fi
        echo "" >> "$FILE"
        echo "## 🔐 Your Password Manager (Vaultwarden)" >> "$FILE"
        echo "This keeps all your other passwords safe! Go to this website to use it:" >> "$FILE"
        echo "- **Website:** https://$DOMAIN" >> "$FILE"
        echo "- **Admin Panel:** https://$DOMAIN/admin" >> "$FILE"
        echo "- **Admin Token:** \`$VW_ADMIN_TOKEN\`" >> "$FILE"
        echo "" >> "$FILE"
        echo "*(Create your own account on the main page. Use the Admin Token to access the admin panel and manage your server.)*" >> "$FILE"
      fi

      # --- BTCPAY SERVER ---
      if [ -f "/var/lib/domains/btcpayserver" ]; then
        DOMAIN=$(cat /var/lib/domains/btcpayserver)
        echo "" >> "$FILE"
        echo "## ₿ Your Bitcoin Store (BTCPay Server)" >> "$FILE"
        echo "This lets you accept Bitcoin like a real shop!" >> "$FILE"
        echo "- **Website:** https://$DOMAIN" >> "$FILE"
        echo "*(You make up your own Admin Password the first time you visit!)*" >> "$FILE"
      fi

      # ── Generate PDF (cd into work dir so Typst finds images) ──
      cd "$WORK_DIR"
      pandoc magic_keys.md -o "$OUTPUT" --pdf-engine=typst \
        -V mainfont="Liberation Sans" \
        -V monofont="Liberation Mono"

      chown free:users "$OUTPUT"

      # ── Save hash so we skip next time if nothing changed ──
      mkdir -p "$(dirname "$HASH_FILE")"
      echo "$CURRENT_HASH" > "$HASH_FILE"

      rm -rf "$WORK_DIR"
      echo "PDF generated successfully."
    '';
  };
}