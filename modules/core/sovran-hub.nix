{ config, lib, pkgs, ... }:

let
  cfg = config.sovran_systemsOS;

  monitoredServices =
    # ── Infrastructure (always present) ────────────────────────
    [
      { name = "Caddy"; unit = "caddy.service"; type = "system"; icon = "caddy"; enabled = true;  category = "infrastructure"; credentials = []; }
      { name = "Tor";   unit = "tor.service";   type = "system"; icon = "tor";   enabled = true;  category = "infrastructure"; credentials = []; }
      { name = "System Passwords"; unit = "root-password-setup.service"; type = "system"; icon = "system"; enabled = true; category = "infrastructure"; credentials = [
        { label = "Free Account — Username"; value = "free"; }
        { label = "Free Account — Password"; file = "/var/lib/secrets/free-password"; }
        { label = "Root Password"; file = "/var/lib/secrets/root-password"; }
        { label = "SSH Local Access"; value = "ssh root@localhost  /  Passphrase: gosovransystems"; }
      ]; }
      { name = "Remote Desktop"; unit = "gnome-remote-desktop.service"; type = "system"; icon = "rdp"; enabled = cfg.features.rdp; category = "infrastructure"; credentials = [
        { label = "Username"; file = "/var/lib/gnome-remote-desktop/rdp-username"; }
        { label = "Password"; file = "/var/lib/gnome-remote-desktop/rdp-password"; }
        { label = "Address";  file = "/var/lib/secrets/internal-ip"; suffix = ":3389"; }
        { label = "How to Connect"; value = "1. Install an RDP client (e.g. Remmina, Microsoft Remote Desktop)\n2. Create a new RDP connection\n3. Enter the Address above as the host\n4. Enter the Username and Password above\n5. Connect — you will see your desktop remotely"; }
      ]; }
    ]
    # ── Bitcoin Base (node implementations) ────────────────────
    ++ [
      { name = "Bitcoin Knots + BIP110"; unit = "bitcoind.service"; type = "system"; icon = "bip110";        enabled = cfg.features.bip110;        category = "bitcoin-base"; credentials = [
        { label = "Tor Address"; file = "/var/lib/tor/onion/bitcoind/hostname"; prefix = "http://"; }
      ]; }
      { name = "Bitcoin Knots";          unit = "bitcoind.service"; type = "system"; icon = "bitcoind";      enabled = cfg.services.bitcoin && !cfg.features.bitcoin-core && !cfg.features.bip110; category = "bitcoin-base"; credentials = [
        { label = "Tor Address"; file = "/var/lib/tor/onion/bitcoind/hostname"; prefix = "http://"; }
      ]; }
      { name = "Bitcoin Core";           unit = "bitcoind.service"; type = "system"; icon = "bitcoin-core";  enabled = cfg.features.bitcoin-core;  category = "bitcoin-base"; credentials = [
        { label = "Tor Address"; file = "/var/lib/tor/onion/bitcoind/hostname"; prefix = "http://"; }
      ]; }
    ]
    # ── Bitcoin Apps (services on top of the node) ─────────────
    ++ [
      { name = "Electrs";            unit = "electrs.service";      type = "system"; icon = "electrs";      enabled = cfg.services.bitcoin;  category = "bitcoin-apps"; credentials = [
        { label = "Tor Address"; file = "/var/lib/tor/onion/electrs/hostname"; prefix = "http://"; }
        { label = "Port"; value = "50001"; }
      ]; }
      { name = "LND";                unit = "lnd.service";          type = "system"; icon = "lnd";          enabled = cfg.services.bitcoin;  category = "bitcoin-apps"; credentials = []; }
      { name = "Ride The Lightning"; unit = "rtl.service";          type = "system"; icon = "rtl";          enabled = cfg.services.bitcoin;  category = "bitcoin-apps"; credentials = [
        { label = "Tor Access"; file = "/var/lib/tor/onion/rtl/hostname"; prefix = "http://"; }
        { label = "Local Network"; file = "/var/lib/secrets/internal-ip"; prefix = "http://"; suffix = ":3050"; }
        { label = "Password"; file = "/etc/nix-bitcoin-secrets/rtl-password"; }
      ]; }
      { name = "BTCPayserver";       unit = "btcpayserver.service"; type = "system"; icon = "btcpayserver"; enabled = cfg.services.bitcoin;  category = "bitcoin-apps"; credentials = [
        { label = "URL"; file = "/var/lib/domains/btcpayserver"; prefix = "https://"; }
        { label = "Note"; value = "Create your admin account on first visit"; }
      ]; }
      { name = "Zeus Connect";       unit = "zeus-connect-setup.service"; type = "system"; icon = "zeus";   enabled = cfg.services.bitcoin;  category = "bitcoin-apps"; credentials = [
        { label = "Connection URL"; file = "/var/lib/secrets/zeus-connect-url"; qrcode = true; }
        { label = "How to Connect"; value = "1. Download Zeus from App Store or Google Play\n2. Open Zeus �� Scan Node Config\n3. Scan the QR code above or paste the Connection URL"; }
      ]; }
      { name = "Mempool";            unit = "mempool.service";      type = "system"; icon = "mempool";      enabled = cfg.features.mempool;  category = "bitcoin-apps"; credentials = [
        { label = "Tor Access"; file = "/var/lib/tor/onion/mempool-frontend/hostname"; prefix = "http://"; }
        { label = "Local Network"; file = "/var/lib/secrets/internal-ip"; prefix = "http://"; suffix = ":60847"; }
      ]; }
    ]
    # ── Communication ──────────────────────────────────────────
    ++ [
      { name = "Matrix-Synapse"; unit = "matrix-synapse.service"; type = "system"; icon = "synapse"; enabled = cfg.services.synapse;          category = "communication"; credentials = [
        { label = "Users"; file = "/var/lib/secrets/matrix-users"; multiline = true; }
      ]; }
      { name = "Element-Call";   unit = "livekit.service";        type = "system"; icon = "livekit"; enabled = cfg.features.element-calling;  category = "communication"; credentials = []; }
    ]
    # ── Self-Hosted Apps ───────────────────────────────────────
    ++ [
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
    # ── Nostr / Relay ──────────────────────────────────────────
    ++ [
      { name = "Haven Relay"; unit = "haven-relay.service"; type = "system"; icon = "haven"; enabled = cfg.features.haven; category = "nostr"; credentials = []; }
    ]
    # ── Support ────────────────────────────────────────────────
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
    if ! nix flake update --flake /etc/nixos --print-build-logs 2>&1; then
      echo "[ERROR] nix flake update failed"
      RC=1
    fi
    echo ""

    if [ "$RC" -eq 0 ]; then
      echo "── Step 2/3: nixos-rebuild switch ──────────────────"
      if ! nixos-rebuild switch --flake /etc/nixos --print-build-logs 2>&1; then
        echo "[ERROR] nixos-rebuild switch failed"
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
      echo "  ✓ Update completed successfully"
      echo "══════════════════════════════════════════════════"
      echo "SUCCESS" > "$STATUS"
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
    if nixos-rebuild switch --flake /etc/nixos --print-build-logs 2>&1; then
      echo ""
      echo "══════════════════════════════════════════════════"
      echo "  ✓ Rebuild completed successfully"
      echo "══════════════════════════════════════════════════"
      echo "SUCCESS" > "$STATUS"
    else
      echo ""
      echo "══════════════════════════════════════════════════"
      echo "  ✗ Rebuild failed — see errors above"
      echo "══════════════════════════════════════════════════"
      echo "FAILED" > "$STATUS"
      exit 1
    fi
  '';

  sovran-hub-web = pkgs.python3Packages.buildPythonApplication {
    pname   = "sovran-systemsos-hub-web";
    version = "1.0.0";
    format  = "other";

    src = ../../app;

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

      serviceConfig = {
        ExecStart      = "${sovran-hub-web}/bin/sovran-hub-web";
        Restart        = "on-failure";
        RestartSec     = "5s";
        User           = "root";
        StandardOutput = "journal";
        StandardError  = "journal";
      };

      path = [ pkgs.qrencode ];
    };

    systemd.services.sovran-hub-update = {
      description = "Sovran_SystemsOS System Update";
      serviceConfig = {
        Type       = "oneshot";
        ExecStart  = "${update-script}";
      };
    };

    systemd.services.sovran-hub-rebuild = {
      description = "Sovran_SystemsOS System Rebuild";
      serviceConfig = {
        Type      = "oneshot";
        ExecStart = "${rebuild-script}";
      };
    };

    systemd.services.hub-overrides-init = {
      description = "Initialize hub-overrides.nix if missing";
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        Type            = "oneshot";
        RemainAfterExit = true;
      };
      unitConfig.ConditionPathExists = "!/etc/nixos/hub-overrides.nix";
      script = ''
        cat > /etc/nixos/hub-overrides.nix <<'EOF'
# Auto-generated by Sovran Hub — do not edit manually
{ ... }:
{
}
EOF
      '';
    };

    networking.firewall.allowedTCPPorts = [ 8937 ];
  };
}