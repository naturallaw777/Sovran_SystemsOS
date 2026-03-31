# modules/core/sovran-hub.nix
#
# Declarative NixOS module that:
#   1. Builds the Sovran_SystemsOS_Hub GTK4 app as a Nix derivation
#   2. Generates its config.json from existing sovran_systemsOS options
#   3. Installs a .desktop file so it appears in GNOME Activities

{ config, pkgs, lib, ... }:

let
  cfg = config.sovran_systemsOS;

  # ── Build the list of monitored units from NixOS option state ──
  #
  # The JSON config is computed at NixOS evaluation time from the
  # SAME options that control whether the services actually run.
  # No separate config file to maintain.

  monitoredServices =
    (lib.optional cfg.services.bitcoin
      { name = "Bitcoind";           unit = "bitcoind.service";         type = "system"; })
    ++ (lib.optional cfg.services.bitcoin
      { name = "Electrs";            unit = "electrs.service";          type = "system"; })
    ++ (lib.optional cfg.services.bitcoin
      { name = "LND";                unit = "lnd.service";              type = "system"; })
    ++ (lib.optional cfg.services.bitcoin
      { name = "Ride The Lightning"; unit = "rtl.service";              type = "system"; })
    ++ (lib.optional cfg.services.bitcoin
      { name = "BTCPayserver";       unit = "btcpayserver.service";     type = "system"; })
    ++ (lib.optional cfg.services.synapse
      { name = "Matrix-Synapse";     unit = "matrix-synapse.service";   type = "system"; })
    ++ (lib.optional cfg.services.synapse
      { name = "Coturn";             unit = "coturn.service";           type = "system"; })
    ++ (lib.optional cfg.services.vaultwarden
      { name = "VaultWarden";        unit = "vaultwarden.service";      type = "system"; })
    ++ (lib.optional cfg.services.nextcloud
      { name = "Nextcloud";          unit = "phpfpm-nextcloud.service"; type = "system"; })
    ++ (lib.optional cfg.services.wordpress
      { name = "WordPress";          unit = "phpfpm-wordpress.service"; type = "system"; })
    ++ (lib.optional cfg.features.haven
      { name = "Haven Relay";        unit = "haven-relay.service";      type = "system"; })
    ++ (lib.optional cfg.features.mempool
      { name = "Mempool";            unit = "mempool.service";          type = "system"; })
    ++ (lib.optional cfg.features.element-calling
      { name = "LiveKit";            unit = "livekit.service";          type = "system"; })
    # Always-on infrastructure
    ++ [
      { name = "Caddy";      unit = "caddy.service";       type = "system"; }
      { name = "Tor";         unit = "tor.service";         type = "system"; }
      { name = "PostgreSQL";  unit = "postgresql.service";  type = "system"; }
      { name = "Fail2Ban";   unit = "fail2ban.service";     type = "system"; }
      { name = "SSH";         unit = "sshd.service";        type = "system"; }
    ];

  # ── Generate the config.json at build time ──
  generatedConfig = pkgs.writeText "sovran-hub-config.json"
    (builtins.toJSON {
      refresh_interval = 5;
      command_method   = "systemctl";
      services         = monitoredServices;
    });

  # ── Package the Python GTK4 app ──
  sovran-hub = pkgs.python3Packages.buildPythonApplication {
    pname   = "sovran-systemsos-hub";
    version = "1.0.0";
    format  = "other";

    src = ../../app;

    nativeBuildInputs = [ pkgs.wrapGAppsHook4 ];

    buildInputs = [
      pkgs.gtk4
      pkgs.libadwaita
      pkgs.gobject-introspection
    ];

    propagatedBuildInputs = [
      pkgs.python3Packages.pygobject3
    ];

    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/lib/sovran-hub $out/share/applications

      # Copy Python source
      cp -r sovran_systemsos_hub $out/lib/sovran-hub/

      # Install the generated config (from Nix options, not a static file)
      cp ${generatedConfig} $out/lib/sovran-hub/config.json

      # Create the launcher script
      cat > $out/bin/sovran-hub <<'LAUNCHER'
#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.join("@out@", "lib", "sovran-hub"))
os.environ["SOVRAN_HUB_CONFIG"] = os.path.join("@out@", "lib", "sovran-hub", "config.json")
from sovran_systemsos_hub.application import SovranHubApp
sys.exit(SovranHubApp().run(sys.argv))
LAUNCHER

      substituteInPlace $out/bin/sovran-hub --replace "@out@" "$out"
      chmod +x $out/bin/sovran-hub

      # Desktop file
      cat > $out/share/applications/Sovran_SystemsOS_Hub.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Sovran_SystemsOS Hub
Comment=Manage Sovran_SystemsOS systemd services
Exec=$out/bin/sovran-hub
Icon=system-run-symbolic
Terminal=false
Categories=System;Monitor;
StartupWMClass=com.sovransystems.hub
EOF
    '';

    meta = {
      description = "Sovran_SystemsOS Hub — GTK4 app to manage systemd services";
      mainProgram = "sovran-hub";
    };
  };

in
{
  config = {
    environment.systemPackages = [ sovran-hub ];
  };
}