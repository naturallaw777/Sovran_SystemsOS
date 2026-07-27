{ config, lib, pkgs, ... }:

let
  cfg = config.sovran_systemsOS;

  monitoredServices =
    # ── Infrastructure — System Passwords (always present) ─────
    [
      { name = "System Passwords"; unit = "root-password-setup.service"; type = "system"; icon = "passwords"; enabled = true; category = "infrastructure"; credentials = [
        { label = "Free Account — Username"; value = "free"; }
        { label = "Free Account / Hub Login — Password"; file = "/var/lib/secrets/free-password"; }
        { label = "Administrator (root) Password"; file = "/var/lib/secrets/root-password"; }
        { label = "SSH Passphrase — use via: ssh root@localhost"; file = "/var/lib/secrets/ssh-passphrase"; }
      ]; }
    ]
    # ── Infrastructure — Caddy + Tor (NOT desktop-only) ────────
    ++ lib.optionals (!cfg.roles.desktop) [
      { name = "Caddy"; unit = "caddy.service"; type = "system"; icon = "caddy"; enabled = true;  category = "infrastructure"; credentials = []; }
      { name = "Tor";   unit = "tor.service";   type = "system"; icon = "tor";   enabled = true;  category = "infrastructure"; credentials = []; }
    ]
    # ── Infrastructure — Remote Desktop (all roles) ─────────────
    ++ [
      { name = "Remote Desktop"; unit = "gnome-remote-desktop.service"; type = "system"; icon = "rdp"; enabled = cfg.features.rdp; category = "infrastructure"; credentials = [
        { label = "Username"; file = "/var/lib/gnome-remote-desktop/rdp-username"; }
        { label = "Password"; file = "/var/lib/gnome-remote-desktop/rdp-password"; }
        { label = "Address";  file = "/var/lib/secrets/internal-ip"; suffix = ":3389"; }
        { label = "How to Connect"; value = "1. Install an RDP client (e.g. Remmina, Microsoft Remote Desktop)\n2. Create a new RDP connection\n3. Enter the Address above as the host\n4. Enter the Username and Password above"; }
      ]; }
    ]
    # ── Bitcoin Base (node implementations) ────────────────────
    ++ lib.optionals cfg.services.bitcoin [
      { name = "Bitcoin Knots + BIP110"; unit = "bitcoind.service"; type = "system"; icon = "bip110";        enabled = cfg.services.bitcoin && !cfg.features.bitcoin-core; category = "bitcoin-base"; credentials = [
        { label = "Tor Address — Access from anywhere via Tor Browser"; file = "/var/lib/tor/onion/bitcoind/hostname"; prefix = "http://"; }
      ]; }
      { name = "Bitcoin Core";           unit = "bitcoind.service"; type = "system"; icon = "bitcoin-core";  enabled = cfg.features.bitcoin-core;  category = "bitcoin-base"; credentials = [
        { label = "Tor Address — Access from anywhere via Tor Browser"; file = "/var/lib/tor/onion/bitcoind/hostname"; prefix = "http://"; }
      ]; }
    ]
    # ── Bitcoin Apps (services on top of the node) ─────────────
    ++ lib.optionals cfg.services.bitcoin [
      { name = "Electrs";            unit = "electrs.service";      type = "system"; icon = "electrs";      enabled = cfg.services.bitcoin;  category = "bitcoin-apps"; credentials = [
        { label = "Tor Address — Access from anywhere via Tor Browser"; file = "/var/lib/tor/onion/electrs/hostname"; prefix = "http://"; }
        { label = "Port"; value = "50001"; }
      ]; }
      { name = "LND";                unit = "lnd.service";          type = "system"; icon = "lnd";          enabled = cfg.services.bitcoin;  category = "bitcoin-apps"; credentials = []; }
      { name = "Ride The Lightning"; unit = "rtl.service";          type = "system"; icon = "rtl";          enabled = cfg.services.bitcoin;  category = "bitcoin-apps"; credentials = [
        { label = "Tor Address — Access from anywhere via Tor Browser"; file = "/var/lib/tor/onion/rtl/hostname"; prefix = "http://"; }
        { label = "Local Network — Access on your home network only"; file = "/var/lib/secrets/internal-ip"; prefix = "http://"; suffix = ":3051"; }
        { label = "Password"; file = "/etc/nix-bitcoin-secrets/rtl-password"; }
        { label = "How to Access"; value = "• Tor Address: Open in Tor Browser from any device, anywhere in the world\n• Local Network: Open in any browser, but only when connected to your home network"; }
      ]; }
      { name = "BTCPayserver";       unit = "btcpayserver.service"; type = "system"; icon = "btcpayserver"; enabled = cfg.web.btcpayserver;  category = "bitcoin-apps"; credentials = [
        { label = "URL"; file = "/var/lib/domains/btcpayserver"; prefix = "https://"; }
        { label = "Note"; value = "Create your admin account on first visit"; }
      ]; }
      { name = "Zeus Connect";       unit = "zeus-connect-setup.service"; type = "system"; icon = "zeus";   enabled = cfg.services.bitcoin;  category = "bitcoin-apps"; credentials = [
        { label = "QR Code"; file = "/var/lib/secrets/zeus-connect-url"; qrcode = true; qronly = true; }
        { label = "How to Connect"; value = "1. Download Zeus from App Store or Google Play\n2. Open Zeus → Scan Node Config\n3. Scan the QR code above"; }
      ]; }
      { name = "Sparrow Auto-Link"; unit = "sparrow-autoconnect.service"; type = "system"; icon = "sparrow"; enabled = cfg.services.bitcoin; category = "bitcoin-apps"; credentials = [
        { label = "Server"; value = "tcp://127.0.0.1:50001 (Electrs)"; }
        { label = "Status"; value = "Auto-configured on first boot"; }
      ]; }
      { name = "Wallet Connections"; unit = "albyhub.service"; type = "system"; icon = "zeus"; enabled = cfg.features."nwc-wallets"; category = "bitcoin-apps"; credentials = [
        { label = "Lightning Address Domain"; file = "/var/lib/domains/lightning"; }
      ]; }
      { name = "Mempool";            unit = "mempool.service";      type = "system"; icon = "mempool";      enabled = cfg.features.mempool;  category = "bitcoin-apps"; credentials = [
        { label = "Tor Address — Access from anywhere via Tor Browser"; file = "/var/lib/tor/onion/mempool-frontend/hostname"; prefix = "http://"; }
        { label = "Local Network — Access on your home network only"; file = "/var/lib/secrets/internal-ip"; prefix = "http://"; suffix = ":60847"; }
        { label = "How to Access"; value = "• Tor Address: Open in Tor Browser from any device, anywhere in the world\n• Local Network: Open in any browser, but only when connected to your home network"; }
      ]; }
    ]
    # ── Communication (server+desktop only) ────────────────────
    ++ lib.optionals cfg.roles.server_plus_desktop [
      { name = "Matrix-Synapse"; unit = "matrix-synapse.service"; type = "system"; icon = "synapse"; enabled = cfg.services.synapse;          category = "communication"; credentials = [
        { label = "Homeserver URL";   file = "/var/lib/secrets/matrix-homeserver-url"; }
        { label = "Admin Username";   file = "/var/lib/secrets/matrix-admin-username"; }
        { label = "Admin Password";   file = "/var/lib/secrets/matrix-admin-password"; }
        { label = "Test Username";    file = "/var/lib/secrets/matrix-test-username"; }
        { label = "Test Password";    file = "/var/lib/secrets/matrix-test-password"; }
      ]; }
      { name = "Element-Call";   unit = "livekit.service";        type = "system"; icon = "element-calling"; enabled = cfg.features.element-calling;  category = "communication"; credentials = []; }
    ]
    # ── Self-Hosted Apps (server+desktop only) ─────────────────
    ++ lib.optionals cfg.roles.server_plus_desktop [
      { name = "VaultWarden"; unit = "vaultwarden.service";      type = "system"; icon = "vaultwarden"; enabled = cfg.services.vaultwarden; category = "apps"; credentials = [
        { label = "URL"; file = "/var/lib/domains/vaultwarden"; prefix = "https://"; }
        { label = "Admin Panel"; file = "/var/lib/domains/vaultwarden"; prefix = "https://"; suffix = "/admin"; }
        { label = "Admin Token"; file = "/var/lib/secrets/vaultwarden/vaultwarden.env"; extract = "ADMIN_TOKEN"; }
      ]; }
      { name = "Nextcloud";   unit = "phpfpm-nextcloud.service"; type = "system"; icon = "nextcloud";   enabled = cfg.services.nextcloud;   category = "apps"; credentials = [
        { label = "Credentials"; file = "/var/lib/secrets/nextcloud-admin"; multiline = true; }
      ]; }
      { name = "WordPress";   unit = "phpfpm-wordpress.service"; type = "system"; icon = "wordpress";   enabled = cfg.services.wordpress;   category = "apps"; credentials = [
        { label = "Credentials"; file = "/var/lib/secrets/wordpress-admin"; multiline = true; }
      ]; }
    ]
    # ── Nostr / Relay (server+desktop only) ────────────────────
    ++ lib.optionals cfg.roles.server_plus_desktop [
      { name = "Haven Relay"; unit = "haven-relay.service"; type = "system"; icon = "haven"; enabled = cfg.features.haven; category = "nostr"; credentials = []; }
    ]
    # ── Support (always present) ────────────────────────────────
    ++ [
      { name = "Tech Support"; unit = "sovran-tech-support"; type = "support"; icon = "support"; enabled = true; category = "support"; credentials = []; }
    ];

  activeRole =
    if cfg.roles.desktop then "desktop"
    else if cfg.roles.node then "node"
    else "server_plus_desktop";

  generatedConfig = pkgs.writeText "sovran-hub-config.json"
    (builtins.toJSON {
      refresh_interval = 5;
      command_method   = "systemctl";
      role             = activeRole;
      services         = monitoredServices;
      feature_manager  = true;
    });

  # ── Update wrapper script ──────────────────────────────────────
  update-script = pkgs.writeShellScript "sovran-hub-update.sh" ''
    set -uo pipefail
    export PATH="${lib.makeBinPath [ pkgs.nix pkgs.nixos-rebuild pkgs.git pkgs.flatpak pkgs.coreutils ]}:$PATH"

    LOG="/var/log/sovran-hub-update.log"
    STATUS="/var/log/sovran-hub-update.status"

    echo "RUNNING" > "$STATUS"
    : > "$LOG"
    exec > >(tee -a "$LOG") 2>&1

    echo "══════════════════════════════════════════════════"
    echo "  Sovran_SystemsOS Update — $(date)"
    echo "══════════════════════════════════════════════════"
    echo ""

    RC=0

    echo "── Step 1/3: nix flake update ────────────────────"
    if ! nix flake update --flake /etc/nixos --print-build-logs \
          --option connect-timeout 10 \
          --option stalled-download-timeout 90 \
          --option download-attempts 7 \
          --option fallback true 2>&1; then
      echo "[ERROR] nix flake update failed"
      RC=1
    fi
    echo ""

    if [ "$RC" -eq 0 ]; then
      echo "── Step 2/3: nixos-rebuild boot (stage next reboot) ──"
      BOOT_OUT=$(nixos-rebuild boot --flake /etc/nixos --print-build-logs \
        --option connect-timeout 10 \
        --option stalled-download-timeout 90 \
        --option download-attempts 7 \
        --option fallback true 2>&1)
      BOOT_RC=$?
      echo "$BOOT_OUT"
      if [ "$BOOT_RC" -ne 0 ]; then
        echo "[ERROR] nixos-rebuild boot failed"
        RC=1
      fi
      echo ""
    fi

    if [ "$RC" -eq 0 ]; then
      echo "── Step 3/3: flatpak update ────────────────────────"
      if ! flatpak update -y 2>&1; then
        echo "[WARNING] flatpak update failed (non-fatal)"
      fi
      echo ""
    fi

    if [ "$RC" -eq 0 ]; then
      echo "══════════════════════════════════════════════════"
      echo "  ✓ Update staged successfully"
      echo "  Reboot required to activate the new system"
      echo "══════════════════════════════════════════════════"
      echo "REBOOT_REQUIRED" > "$STATUS"
    else
      echo "══════════════════════════════════════════════════"
      echo "  ✗ Update failed — see errors above"
      echo "══════════════════════════════════════════════════"
      echo "FAILED" > "$STATUS"
    fi

    exit "$RC"
  '';

  # ── Rebuild wrapper script ─────────────────────────────────────
  rebuild-script = pkgs.writeShellScript "sovran-hub-rebuild.sh" ''
    set -uo pipefail
    export PATH="${lib.makeBinPath [ pkgs.nix pkgs.nixos-rebuild pkgs.coreutils ]}:$PATH"

    LOG="/var/log/sovran-hub-rebuild.log"
    STATUS="/var/log/sovran-hub-rebuild.status"

    echo "RUNNING" > "$STATUS"
    : > "$LOG"
    exec > >(tee -a "$LOG") 2>&1

    echo "══════════════════════════════════════════════════"
    echo "  Sovran_SystemsOS Rebuild — $(date)"
    echo "══════════════════════════════════════════════════"
    echo ""
    echo "── Rebuilding system configuration ──────────────"
    SWITCH_OUT=$(nixos-rebuild switch --flake /etc/nixos --print-build-logs \
      --option connect-timeout 10 \
      --option stalled-download-timeout 90 \
      --option download-attempts 7 \
      --option fallback true 2>&1)
    SWITCH_RC=$?
    echo "$SWITCH_OUT"
    if [ "$SWITCH_RC" -eq 0 ]; then
      echo ""
      echo "══════════════════════════════════════════════════"
      echo "  ✓ Rebuild completed successfully"
      echo "══════════════════════════════════════════════════"
      echo "SUCCESS" > "$STATUS"
    elif echo "$SWITCH_OUT" | grep -q "switchInhibitors\|Pre-switch checks failed"; then
      echo ""
      echo "  ✓ Build succeeded — a reboot is required to apply this rebuild"
      echo "  (Critical system components changed; running nixos-rebuild boot instead)"
      if nixos-rebuild boot --flake /etc/nixos --print-build-logs \
           --option connect-timeout 10 \
           --option stalled-download-timeout 90 \
           --option download-attempts 7 \
           --option fallback true 2>&1; then
        echo "REBOOT_REQUIRED" > "$STATUS"
      else
        echo "[ERROR] nixos-rebuild boot also failed"
        echo "FAILED" > "$STATUS"
        exit 1
      fi
    else
      echo ""
      echo "══════════════════════════════════════════════════"
      echo "  ✗ Rebuild failed — see errors above"
      echo "══════════════════════════════════════════════════"
      echo "FAILED" > "$STATUS"
      exit 1
    fi
  '';

  # ── Brave launcher wrapper: stable profile dir so Wayland app_id is
  #    deterministic and GNOME Shell can match the window to the .desktop
  #    entry (fixes generic gear icon appearing in the dock).
  hub-brave-wrapper = pkgs.writeShellScript "sovran-hub-brave.sh" ''
    export PATH="${lib.makeBinPath [ pkgs.brave pkgs.coreutils ]}:$PATH"
    HUB_DATA="/tmp/sovran-hub-brave-$(id -u)"
    mkdir -p "$HUB_DATA"
    trap '[ -n "$HUB_DATA" ] && rm -rf "$HUB_DATA"' EXIT INT TERM
    export BAMF_DESKTOP_FILE_HINT="/run/current-system/sw/share/applications/sovran-hub.desktop"
    export GIO_LAUNCHED_DESKTOP_FILE="/run/current-system/sw/share/applications/sovran-hub.desktop"
    brave --app=http://localhost:8937/auto-login \
          --class=sovran-hub \
          --user-data-dir="$HUB_DATA" \
          --password-store=basic \
          --disable-gpu \
          --disable-features=WebRtcPipeWireCapturer \
          --ozone-platform=wayland
  '';

  # ── Hub auto-launch wrapper script ────────────────────────────────
  hub-autolaunch-script = pkgs.writeShellScript "sovran-hub-autolaunch.sh" ''
    export PATH="${lib.makeBinPath [ pkgs.curl pkgs.coreutils ]}:$PATH"

    DISABLE_FLAG="/var/lib/sovran/hub-autolaunch-disabled"
    BOOT_FLAG="/run/sovran-hub-autolaunch-done"

    # User disabled auto-launch via Hub toggle
    [ -f "$DISABLE_FLAG" ] && exit 0

    # Already launched this boot
    [ -f "$BOOT_FLAG" ] && exit 0

    touch "$BOOT_FLAG"

    # Wait for Hub server to become ready (max ~15 seconds)
    for i in $(seq 1 15); do
      curl -s -o /dev/null http://localhost:8937 && break
      sleep 1
    done

    ${hub-brave-wrapper}
  '';

  sovran-hub-web = pkgs.python3Packages.buildPythonApplication {
    pname   = "sovran-systemsos-hub-web";
    version = "1.0.0";
    format  = "other";

    src = ../../app;

    nativeBuildInputs = [ pkgs.librsvg ];

    propagatedBuildInputs = with pkgs.python3Packages; [
      fastapi
      uvicorn
      jinja2
      python-multipart
    ];

    dontBuild = true;

    installPhase = ''
      runHook preInstall

      install -d $out/lib/sovran-hub-web
      cp -r sovran_systemsos_web $out/lib/sovran-hub-web/

      cp ${generatedConfig} $out/lib/sovran-hub-web/config.json

      install -d $out/share/sovran-hub/icons
      cp icons/* $out/share/sovran-hub/icons/ 2>/dev/null || true

      install -d $out/share/icons/hicolor/scalable/apps
      cp sovran_systemsos_web/static/sovran-hub-icon.svg $out/share/icons/hicolor/scalable/apps/sovran-hub.svg

      for size in 48 128 256 512; do
        install -d $out/share/icons/hicolor/''${size}x''${size}/apps
        rsvg-convert -w ''${size} -h ''${size} sovran_systemsos_web/static/sovran-hub-icon.svg -o $out/share/icons/hicolor/''${size}x''${size}/apps/sovran-hub.png
      done

      install -d $out/share/applications
      cat > $out/share/applications/sovran-hub.desktop <<DESKTOP
[Desktop Entry]
Type=Application
Name=Sovran Hub
Comment=Open Sovran_SystemsOS Hub dashboard
Exec=${hub-brave-wrapper}
Icon=sovran-hub
Terminal=false
Categories=System;
StartupNotify=true
StartupWMClass=brave-localhost__auto-login-Default
X-GNOME-SingleWindow=true
DESKTOP

      install -d $out/bin
      cat > $out/bin/sovran-hub-web <<LAUNCHER
#!${pkgs.python3}/bin/python3
import os, sys
base = os.path.join("$out", "lib", "sovran-hub-web")
sys.path.insert(0, base)
os.environ["SOVRAN_HUB_CONFIG"] = os.path.join(base, "config.json")
os.environ["SOVRAN_HUB_ICONS"]  = os.path.join("$out", "share", "sovran-hub", "icons")
import uvicorn
uvicorn.run(
    "sovran_systemsos_web.server:app",
    host="0.0.0.0",
    port=8937,
    log_level="info",
)
LAUNCHER
      chmod +x $out/bin/sovran-hub-web

      cat > $out/bin/nwc-wallet <<LAUNCHER
#!${pkgs.python3}/bin/python3
import os, sys
base = os.path.join("$out", "lib", "sovran-hub-web")
sys.path.insert(0, base)
from sovran_systemsos_web.nwc_wallet_cli import main
sys.exit(main())
LAUNCHER
      chmod +x $out/bin/nwc-wallet

      runHook postInstall
    '';

    meta = {
      description = "Sovran_SystemsOS Hub — web-based systemd service manager";
      mainProgram = "sovran-hub-web";
    };
  };

in
{
  config = {
    systemd.services.sovran-hub-web = {
      description = "Sovran_SystemsOS Hub Web Interface";
      wantedBy    = [ "multi-user.target" ];
      after       = [ "network.target" ];
      conflicts   = [ "sovran-hub-reboot.service" ];

      serviceConfig = {
        ExecStart      = "${sovran-hub-web}/bin/sovran-hub-web";
        Restart        = "on-failure";
        RestartPreventExitStatus = "SIGTERM";
        RestartSec     = "5s";
        User           = "root";
        StandardOutput = "journal";
        StandardError  = "journal";
      };

      path = [
        pkgs.bash
        pkgs.gawk
        pkgs.qrencode
        pkgs.curl
        pkgs.iproute2
        pkgs.nftables
        pkgs.iptables
        pkgs.hostname
        pkgs.coreutils
        pkgs.findutils
        pkgs.gnugrep
        pkgs.rsync
        pkgs.acl
        pkgs.util-linux
      ]
      ++ lib.optional cfg.services.bitcoin config.services.bitcoind.package
      ++ lib.optionals cfg.services.bitcoin [ pkgs.lnd ]
      ++ lib.optionals (cfg.services.nextcloud || cfg.services.synapse) [ config.services.postgresql.package ]
      ++ lib.optionals config.services.mysql.enable [ config.services.mysql.package ];
    };

    systemd.services.sovran-hub-update = {
      description = "Sovran_SystemsOS System Update";
      restartIfChanged = false;   # Don't let nixos-rebuild kill an in-flight update
      stopIfChanged    = false;   # Don't stop it during activation either
      serviceConfig = {
        Type       = "oneshot";
        ExecStart  = "${update-script}";
      };
    };

    systemd.services.sovran-hub-rebuild = {
      description = "Sovran_SystemsOS System Rebuild";
      restartIfChanged = false;   # Don't let nixos-rebuild kill an in-flight rebuild
      stopIfChanged    = false;   # Don't stop it during activation either
      serviceConfig = {
        Type      = "oneshot";
        ExecStart = "${rebuild-script}";
      };
    };

    systemd.services.sovran-hub-reboot = {
      description = "Sovran_SystemsOS System Reboot";
      serviceConfig = {
        Type      = "oneshot";
        ExecStart = "/run/current-system/sw/bin/systemctl --force reboot";
      };
    };

    environment.systemPackages = [ sovran-hub-web ];

    networking.firewall.allowedTCPPorts = [ 8937 60847 ];

    # ── Auto-launch Hub in browser on login ───────────────────────
    environment.etc."xdg/autostart/sovran-hub-autolaunch.desktop".text = ''
[Desktop Entry]
Type=Application
Name=Sovran Hub Auto-Launch
Exec=${hub-autolaunch-script}
Terminal=false
X-GNOME-Autostart-enabled=true
NoDisplay=true
'';

  };
}
