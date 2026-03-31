{ config, lib, pkgs, ... }:

let
  cfg = config.sovran_systemsOS;

  monitoredServices =
    # ── Always-on infrastructure ───────────────────────────────
    [
      { name = "Caddy"; unit = "caddy.service"; type = "system"; icon = "caddy"; enabled = true; }
      { name = "Tor";   unit = "tor.service";   type = "system"; icon = "tor";   enabled = true; }
    ]
    # ── Bitcoin ecosystem ──────────────────────────────────────
    ++ [
      { name = "Bitcoind";           unit = "bitcoind.service";     type = "system"; icon = "bitcoind";      enabled = cfg.services.bitcoin; }
      { name = "Electrs";            unit = "electrs.service";      type = "system"; icon = "electrs";       enabled = cfg.services.bitcoin; }
      { name = "LND";                unit = "lnd.service";          type = "system"; icon = "lnd";           enabled = cfg.services.bitcoin; }
      { name = "Ride The Lightning"; unit = "rtl.service";          type = "system"; icon = "rtl";           enabled = cfg.services.bitcoin; }
      { name = "BTCPayserver";       unit = "btcpayserver.service"; type = "system"; icon = "btcpayserver";  enabled = cfg.services.bitcoin; }
    ]
    # ── Other services ─────────────────────────────────────────
    ++ [
      { name = "Matrix-Synapse"; unit = "matrix-synapse.service";   type = "system"; icon = "synapse";      enabled = cfg.services.synapse; }
      { name = "VaultWarden";    unit = "vaultwarden.service";      type = "system"; icon = "vaultwarden";  enabled = cfg.services.vaultwarden; }
      { name = "Nextcloud";      unit = "phpfpm-nextcloud.service"; type = "system"; icon = "nextcloud";    enabled = cfg.services.nextcloud; }
      { name = "WordPress";      unit = "phpfpm-wordpress.service"; type = "system"; icon = "wordpress";    enabled = cfg.services.wordpress; }
    ]
    # ── Optional features ──────────────────────────────────────
    ++ [
      { name = "Haven Relay";  unit = "haven-relay.service"; type = "system"; icon = "haven";   enabled = cfg.features.haven; }
      { name = "Mempool";      unit = "mempool.service";     type = "system"; icon = "mempool"; enabled = cfg.features.mempool; }
      { name = "Element-Call"; unit = "livekit.service";     type = "system"; icon = "livekit"; enabled = cfg.features.element-calling; }
    ];

  generatedConfig = pkgs.writeText "sovran-hub-config.json"
    (builtins.toJSON {
      refresh_interval = 5;
      command_method   = "systemctl";
      services         = monitoredServices;
    });

  sovran-hub = pkgs.python3Packages.buildPythonApplication {
    pname   = "sovran-systemsos-hub";
    version = "1.0.0";
    format  = "other";

    src = ../../app;

    nativeBuildInputs = with pkgs; [
      wrapGAppsHook4
      gobject-introspection
    ];

    buildInputs = with pkgs; [
      gtk4
      libadwaita
      gdk-pixbuf
      librsvg
    ];

    propagatedBuildInputs = with pkgs.python3Packages; [
      pygobject3
    ];

    dontBuild = true;

    installPhase = ''
      runHook preInstall

      # ── Python source ───────────────────────────────���─────────
      install -d $out/lib/sovran-hub
      cp -r sovran_systemsos_hub $out/lib/sovran-hub/

      # ── CSS ────────────────────────────────────────────────────
      cp style.css $out/lib/sovran-hub/style.css

      # ── Generated config ───────────────────────────────────────
      cp ${generatedConfig} $out/lib/sovran-hub/config.json

      # ── Icons (SVG + PNG) ──────────────────────────────────────
      install -d $out/share/sovran-hub/icons
      cp icons/* $out/share/sovran-hub/icons/ 2>/dev/null || true

      # ── Launcher script ────────────────────────────────────────
      install -d $out/bin
      cat > $out/bin/sovran-hub <<LAUNCHER
#!${pkgs.python3}/bin/python3
import os, sys
base = os.path.join("$out", "lib", "sovran-hub")
sys.path.insert(0, base)
os.environ["SOVRAN_HUB_CONFIG"] = os.path.join(base, "config.json")
os.environ["SOVRAN_HUB_ICONS"]  = os.path.join("$out", "share", "sovran-hub", "icons")
os.environ["SOVRAN_HUB_CSS"]    = os.path.join(base, "style.css")
from sovran_systemsos_hub.application import SovranHubApp
sys.exit(SovranHubApp().run(sys.argv))
LAUNCHER
      chmod +x $out/bin/sovran-hub

      # ── Desktop file ───────────────────────────────────────────
      install -d $out/share/applications
      cat > $out/share/applications/Sovran_SystemsOS_Hub.desktop <<DESKTOP
[Desktop Entry]
Type=Application
Name=Sovran_SystemsOS Hub
Comment=Manage Sovran_SystemsOS systemd services
Exec=$out/bin/sovran-hub
Icon=system-run-symbolic
Terminal=false
Categories=System;Monitor;
StartupWMClass=com.sovransystems.hub
DESKTOP

      runHook postInstall
    '';

    meta = {
      description = "Sovran_SystemsOS Hub — GTK4 systemd service manager";
      mainProgram = "sovran-hub";
    };
  };

in
{
  config = {
    environment.systemPackages = [ sovran-hub ];
  };
}