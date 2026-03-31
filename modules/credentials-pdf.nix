{ config, pkgs, lib, ... }:

let
  fonts = pkgs.liberation_ttf;
in
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

  # ── 2. Timer: Rebuild PDF every 5 minutes ──────────────────
  systemd.timers.generate-credentials-pdf = {
    description = "Periodically regenerate Magic Keys PDF";
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

    path = [ pkgs.pandoc pkgs.typst pkgs.coreutils pkgs.qrencode fonts ];

    environment = {
      TYPST_FONT_PATHS = "${fonts}/share/fonts";
    };

    script = ''
      DOC_DIR="/home/free/Documents"
      OUTPUT="$DOC_DIR/Sovran_SystemsOS_Magic_Keys.pdf"
      FILE="/tmp/magic_keys.md"
      mkdir -p "$DOC_DIR"

      # ── Read secrets (default to placeholder if missing) ──
      read_secret() { if [ -f "$1" ]; then cat "$1"; else echo "$2"; fi; }

      ROOT_PASS=$(read_secret /var/lib/secrets/root-password "Generating...")
      RTL_PASS=$(read_secret /etc/nix-bitcoin-secrets/rtl-password "Not found")
      RTL_ONION=$(read_secret /var/lib/tor/onion/rtl/hostname "Not generated yet")
      ELECTRS_ONION=$(read_secret /var/lib/tor/onion/electrs/hostname "Not generated yet")
      BITCOIN_ONION=$(read_secret /var/lib/tor/onion/bitcoind/hostname "Not generated yet")

      # ── Generate Zeus QR code as text if lndconnect URL is available ──
      ZEUS_QR_TEXT=""
      ZEUS_URL=""
      if command -v lndconnect >/dev/null 2>&1; then
        ZEUS_URL=$(lndconnect --url 2>/dev/null || true)
      elif command -v lnconnect-clnrest >/dev/null 2>&1; then
        ZEUS_URL=$(lnconnect-clnrest --url 2>/dev/null || true)
      fi

      if [ -n "$ZEUS_URL" ]; then
        ZEUS_QR_TEXT=$(qrencode -t ANSIUTF8 "$ZEUS_URL" 2>/dev/null || true)
      fi

      # ── Build the Markdown document ──
      cat > "$FILE" << ENDOFFILE
---
title: "Sovran SystemsOS Magic Keys"
---

# Your Sovran SystemsOS Magic Keys! 🗝️

Welcome to your new computer! We have built a lot of cool secret forts (services) for you. To get into your forts, you need your magic keys (passwords).

Here are all of your keys in one place. **Keep this document safe and do not share it with strangers!**

## 🖥️ Your Computer
These are the master keys to the actual machine.

### 1. Main Screen Unlock (The 'free' account)
When you turn the computer on, it usually logs you in automatically. However, if the screen goes to sleep, or **if you enable Remote Desktop (RDP)**, you will need this to log in:
- **Username:** \`free\`
- **Password:** \`free\`

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
      if [ -n "$ZEUS_QR_TEXT" ]; then
        cat >> "$FILE" << 'ZEUSHEADER'

## 📱 Connect Zeus Mobile Wallet

Take your Bitcoin Lightning node anywhere in the world! Scan this QR code with the **Zeus** app on your phone to instantly connect your mobile wallet to your Lightning node.

1. Download **Zeus** from the App Store or Google Play
2. Open Zeus and tap **"Scan Node Config"**
3. Point your phone's camera at this QR code:

```text
ZEUSHEADER
        echo "$ZEUS_QR_TEXT" >> "$FILE"
        cat >> "$FILE" << 'ZEUSFOOTER'
