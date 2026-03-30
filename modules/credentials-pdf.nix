{ config, pkgs, lib, ... }:

{
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
      set -euo pipefail
      
      SECRET_FILE="/var/lib/secrets/root-password"
      
      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p /var/lib/secrets
        ROOT_PASS=$(pwgen -s 20 1)
        
        # Apply the password to the root user
        echo "root:$ROOT_PASS" | chpasswd
        
        # Save it for the PDF generator to read
        echo "$ROOT_PASS" > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
      fi
    '';
  };

  # ── 2. The Path Watcher (The Magic Trigger!) ───────────────
  # This tells NixOS: "If any files inside these folders change, 
  # instantly run the generate-credentials-pdf service."
  systemd.paths.generate-credentials-pdf-trigger = {
    description = "Watch for new secret files to regenerate Magic Keys PDF";
    wantedBy = [ "multi-user.target" ];
    pathConfig = {
      # Watch these directories for new passwords
      PathChanged = [
        "/var/lib/secrets"
        "/var/lib/gnome-remote-desktop"
        "/var/lib/domains"
        "/etc/nix-bitcoin-secrets"
      ];
      # Watch for these specific Tor links to be generated
      PathExists = [
        "/var/lib/tor/onion/rtl/hostname"
        "/var/lib/tor/onion/electrs/hostname"
        "/var/lib/tor/onion/bitcoind/hostname"
      ];
      Unit = "generate-credentials-pdf.service";
    };
  };

  # ── 3. Generate the Magic Keys PDF ─────────────────────────
  systemd.services.generate-credentials-pdf = {
    description = "Generate Magic Keys PDF for Sovran_SystemsOS";
    serviceConfig = {
      Type = "oneshot";
      # Prevent rapid re-triggering
      RateLimitIntervalSec = 30;
      RateLimitBurstSec = 1;
    };
    
    path = [ pkgs.pandoc pkgs.typst pkgs.coreutils pkgs.liberation_ttf ];
    
    environment = {    
      TYPST_FONT_PATHS = "${pkgs.liberation_ttf}/share/fonts";
    };
    
    script = ''
      set -euo pipefail

      # Give it a tiny delay so multiple files being created at once don't trigger it 10 times in a row
      sleep 3

      # ── Deduplication: only rebuild if inputs actually changed ──
      HASH_FILE="/var/lib/secrets/.credentials-pdf-hash"

      # Collect the content of all possible input files into one hash
      CURRENT_HASH=$(cat \
        /var/lib/secrets/root-password \
        /etc/nix-bitcoin-secrets/rtl-password \
        /var/lib/tor/onion/rtl/hostname \
        /var/lib/tor/onion/electrs/hostname \
        /var/lib/tor/onion/bitcoind/hostname \
        /var/lib/secrets/matrix-users \
        /var/lib/gnome-remote-desktop/rdp-credentials \
        /var/lib/secrets/nextcloud-admin \
        /var/lib/secrets/wordpress-admin \
        /var/lib/domains/vaultwarden \
        /var/lib/domains/btcpayserver \
        2>/dev/null | sha256sum | cut -d' ' -f1)

      if [ -f "$HASH_FILE" ] && [ "$(cat "$HASH_FILE")" = "$CURRENT_HASH" ]; then
        echo "No input changes detected, skipping PDF regeneration."
        exit 0
      fi

      DOC_DIR="/home/free/Documents"
      mkdir -p "$DOC_DIR"
      FILE="/tmp/magic_keys.md"
      
      ROOT_PASS="Generating..."
      if [ -f "/var/lib/secrets/root-password" ]; then
        ROOT_PASS=$(cat /var/lib/secrets/root-password)
      fi
      
      cat << 'EOF' > "$FILE"
---
---
# Your Sovran SystemsOS Magic Keys! 🗝️

Welcome to your new computer! We have built a lot of cool secret forts (services) for you. To get into your forts, you need your magic keys (passwords). 

Here are all of your keys in one place. **Keep this document safe and do not share it with strangers!**

## 🖥️ Your Computer
These are the master keys to the actual machine.

### 1. Main Screen Unlock (The 'free' account)
When you turn the computer on, it usually logs you in automatically. However, if the screen goes to sleep, or **if you enable Remote Desktop (RDP)**, you will need this to log in:
- **Username:** `free`
- **Password:** `free`

🚨 **VERY IMPORTANT:** You MUST write this password down and keep it safe! If you lose it, you will be locked out of your computer!
EOF

      cat << EOF >> "$FILE"

### 2. The Big Boss (Root)
Sometimes a pop-up box might ask for an Administrator (Root) password to change a setting. We created a super-secret password just for this!
- **Root Password:** \`$ROOT_PASS\`
EOF

      cat << 'EOF' >> "$FILE"

### 3. The Hacker Terminal (`ssh root@localhost`)
Because your main account is so safe, you cannot just type normal commands to become the boss. If you open a black terminal box and want to make big changes, you must use your special factory key! 

Type this exact command into the terminal:
`ssh root@localhost`

When it asks for a passphrase, type:
- **Terminal Password:** `gosovransystems`

***
EOF

      # --- BITCOIN ECOSYSTEM ---
      if [ -f "/etc/nix-bitcoin-secrets/rtl-password" ] || [ -f "/var/lib/tor/onion/rtl/hostname" ]; then
        echo "## ⚡ Your Bitcoin & Lightning Node" >> "$FILE"
        echo "Your computer is a real Bitcoin node! It talks to the network secretly using Tor. Here is how to connect your wallet apps to it:" >> "$FILE"
        
        RTL_ONION="Not generated yet"
        if [ -f "/var/lib/tor/onion/rtl/hostname" ]; then
          RTL_ONION=$(cat /var/lib/tor/onion/rtl/hostname)
        fi
        RTL_PASS="Not found"
        if [ -f "/etc/nix-bitcoin-secrets/rtl-password" ]; then
          RTL_PASS=$(cat /etc/nix-bitcoin-secrets/rtl-password)
        fi

        ELECTRS_ONION="Not generated yet"
        if [ -f "/var/lib/tor/onion/electrs/hostname" ]; then
          ELECTRS_ONION=$(cat /var/lib/tor/onion/electrs/hostname)
        fi

        BITCOIN_ONION="Not generated yet"
        if [ -f "/var/lib/tor/onion/bitcoind/hostname" ]; then
          BITCOIN_ONION=$(cat /var/lib/tor/onion/bitcoind/hostname)
        fi

        cat << BITCOIN >> "$FILE"
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

***
BITCOIN
      fi

      # --- MATRIX / ELEMENT ---
      if [ -f "/var/lib/secrets/matrix-users" ]; then
        echo "## 💬 Your Private Chat (Matrix / Element)" >> "$FILE"
        echo "This is your very own private messaging app! We created an Admin account for you, and a Test account you can give to a friend to try it out. Log in using an app like Element with these details:" >> "$FILE"
        echo '```text' >> "$FILE"
        cat /var/lib/secrets/matrix-users >> "$FILE"
        echo '```' >> "$FILE"
        echo "***" >> "$FILE"
      fi
      
      # --- GNOME RDP ---
      if [ -f "/var/lib/gnome-remote-desktop/rdp-credentials" ]; then
        echo "## 🌎 Connect from Far Away (Remote Desktop)" >> "$FILE"
        echo "This lets you control your computer screen from another device! Open your Remote Desktop app and type in these keys:" >> "$FILE"
        echo '```text' >> "$FILE"
        cat /var/lib/gnome-remote-desktop/rdp-credentials >> "$FILE"
        echo '```' >> "$FILE"
        echo "***" >> "$FILE"
      fi
      
      # --- NEXTCLOUD ---
      if [ -f "/var/lib/secrets/nextcloud-admin" ]; then
        echo "## ☁️ Your Personal Cloud (Nextcloud)" >> "$FILE"
        echo "This is like your own private Google Drive! You can save photos and files here. Go to the URL below and use these keys:" >> "$FILE"
        echo '```text' >> "$FILE"
        cat /var/lib/secrets/nextcloud-admin >> "$FILE"
        echo '```' >> "$FILE"
        echo "***" >> "$FILE"
      fi
      
      # --- WORDPRESS ---
      if [ -f "/var/lib/secrets/wordpress-admin" ]; then
        echo "## 📝 Your Website (WordPress)" >> "$FILE"
        echo "This is your very own website where you can write blogs or make pages. Go to the URL below to log in:" >> "$FILE"
        echo '```text' >> "$FILE"
        cat /var/lib/secrets/wordpress-admin >> "$FILE"
        echo '```' >> "$FILE"
        echo "***" >> "$FILE"
      fi
      
      # --- VAULTWARDEN ---
      if [ -f "/var/lib/domains/vaultwarden" ]; then
        DOMAIN=$(cat /var/lib/domains/vaultwarden)
        echo "## 🔐 Your Password Manager (Vaultwarden)" >> "$FILE"
        echo "This keeps all your other passwords safe! Go to this website to use it:" >> "$FILE"
        echo "- **Website:** https://$DOMAIN" >> "$FILE"
        echo "*(Note: You get to make up your own Master Password the very first time you visit this website!)*" >> "$FILE"
        echo "***" >> "$FILE"
      fi

      # --- BTCPAY SERVER ---
      if [ -f "/var/lib/domains/btcpayserver" ]; then
        DOMAIN=$(cat /var/lib/domains/btcpayserver)
        echo "## ₿ Your Bitcoin Store (BTCPay Server)" >> "$FILE"
        echo "This lets you accept Bitcoin like a real shop! Go to this website to set it up:" >> "$FILE"
        echo "- **Website:** https://$DOMAIN" >> "$FILE"
        echo "*(Note: You get to make up your own Admin Password the very first time you visit this website!)*" >> "$FILE"
        echo "***" >> "$FILE"
      fi
      
      # Convert the Markdown text into a beautiful PDF!
      pandoc "$FILE" -o "$DOC_DIR/Sovran_SystemsOS_Magic_Keys.pdf" --pdf-engine=typst \
        -V mainfont="Liberation Sans" \
        -V monofont="Liberation Mono"

      # Save the hash so we don't rebuild again for the same inputs
      echo "$CURRENT_HASH" > "$HASH_FILE"
      
      # Make sure the 'free' user owns the file so they can open it
      chown -R free:users "$DOC_DIR"
      
      # Secure the markdown file
      chmod 600 "$FILE"
    '';
  };
}
