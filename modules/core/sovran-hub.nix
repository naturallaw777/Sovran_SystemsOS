# modules/core/sovran-hub.nix
#
# Declarative NixOS module that:
#   1. Fetches high-quality PNG logos for each service
#   2. Builds the Sovran_SystemsOS_Hub GTK4 app as a Nix derivation
#   3. Generates its config.json from existing sovran_systemsOS options
#   4. Installs a .desktop file so it appears in GNOME Activities

{ config, pkgs, lib, ... }:

let
  cfg = config.sovran_systemsOS;

  # ── Fetch service logos ──────────────────────────────────────
  #
  # Each logo is fetched once at build time and placed in a
  # single directory as <icon-key>.png so the Python app can
  # load them by name.

  logos = {
    bitcoind = pkgs.fetchurl {
      url = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/Bitcoin.svg/240px-Bitcoin.svg.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";  # replace after first build
      name = "bitcoind.png";
    };
    electrs = pkgs.fetchurl {
      url = "https://raw.githubusercontent.com/nicehash/electrumx-client/master/electrum-logo.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "electrs.png";
    };
    lnd = pkgs.fetchurl {
      url = "https://raw.githubusercontent.com/lightningnetwork/lnd/master/logo.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "lnd.png";
    };
    rtl = pkgs.fetchurl {
      url = "https://raw.githubusercontent.com/Ride-The-Lightning/RTL/master/src/assets/images/rtl-logo.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "rtl.png";
    };
    btcpayserver = pkgs.fetchurl {
      url = "https://raw.githubusercontent.com/btcpayserver/btcpayserver/master/BTCPayServer/wwwroot/img/logo.png";
      sha256 = "sha256-5yKCvEZ7df61fSQWYx2WqVx4F3v+VxqAsMSUZ2sheeI=";
      name = "btcpayserver.png";
    };
    synapse = pkgs.fetchurl {
      url = "https://raw.githubusercontent.com/nicehash/element-web/develop/res/themes/element/img/logos/element-logo.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "synapse.png";
    };
    vaultwarden = pkgs.fetchurl {
      url = "https://raw.githubusercontent.com/dani-garcia/vaultwarden/main/resources/vaultwarden-icon.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "vaultwarden.png";
    };
    nextcloud = pkgs.fetchurl {
      url = "https://upload.wikimedia.org/wikipedia/commons/thumb/6/60/Nextcloud_Logo.svg/240px-Nextcloud_Logo.svg.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "nextcloud.png";
    };
    wordpress = pkgs.fetchurl {
      url = "https://s.w.org/style/images/about/WordPress-logotype-wmark.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "wordpress.png";
    };
    haven = pkgs.fetchurl {
      url = "https://raw.githubusercontent.com/nicehash/nostr-rs-relay/master/logo.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "haven.png";
    };
    mempool = pkgs.fetchurl {
      url = "https://raw.githubusercontent.com/nicehash/mempool/master/frontend/src/resources/mempool-space-logo.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "mempool.png";
    };
    livekit = pkgs.fetchurl {
      url = "https://avatars.githubusercontent.com/u/70location?s=200";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "livekit.png";
    };
    caddy = pkgs.fetchurl {
      url = "https://caddyserver.com/resources/images/caddy-logo.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "caddy.png";
    };
    tor = pkgs.fetchurl {
      url = "https://upload.wikimedia.org/wikipedia/commons/thumb/1/15/Tor-logo-2011-flat.svg/240px-Tor-logo-2011-flat.svg.png";
      sha256 = "0000000000000000000000000000000000000000000000000000";
      name = "tor.png";
    };
  };

  # Bundle all logos into a single derivation directory
  logoDir = pkgs.runCommand "sovran-hub-icons" {} ''
    mkdir -p $out
    ${lib.concatStringsSep "\n" (lib.mapAttrsToList (key: src:
      "cp ${src} $out/${key}.png"
    ) logos)}
  '';

  # ── Build the list of monitored units from NixOS option state ──
  #
  # Each entry now includes an "icon" key that matches a filename
  # in the logoDir (without extension).

  monitoredServices =
    (lib.optional cfg.services.bitcoin
      { name = "Bitcoind";           unit = "bitcoind.service";         type = "system"; icon = "bitcoind"; })
    ++ (lib.optional cfg.services.bitcoin
      { name = "Electrs";            unit = "electrs.service";          type = "system"; icon = "electrs"; })
    ++ (lib.optional cfg.services.bitcoin
      { name = "LND";                unit = "lnd.service";              type = "system"; icon = "lnd"; })
    ++ (lib.optional cfg.services.bitcoin
      { name = "Ride The Lightning"; unit = "rtl.service";              type = "system"; icon = "rtl"; })
    ++ (lib.optional cfg.services.bitcoin
      { name = "BTCPayserver";       unit = "btcpayserver.service";     type = "system"; icon = "btcpayserver"; })
    ++ (lib.optional cfg.services.synapse
      { name = "Matrix-Synapse";     unit = "matrix-synapse.service";   type = "system"; icon = "synapse"; })
    ++ (lib.optional cfg.services.vaultwarden
      { name = "VaultWarden";        unit = "vaultwarden.service";      type = "system"; icon = "vaultwarden"; })
    ++ (lib.optional cfg.services.nextcloud
      { name = "Nextcloud";          unit = "phpfpm-nextcloud.service"; type = "system"; icon = "nextcloud"; })
    ++ (lib.optional cfg.services.wordpress
      { name = "WordPress";          unit = "phpfpm-wordpress.service"; type = "system"; icon = "wordpress"; })
    ++ (lib.optional cfg.features.haven
      { name = "Haven Relay";        unit = "haven-relay.service";      type = "system"; icon = "haven"; })
    ++ (lib.optional cfg.features.mempool
      { name = "Mempool";            unit = "mempool.service";          type = "system"; icon = "mempool"; })
    ++ (lib.optional cfg.features.element-calling
      { name = "LiveKit";            unit = "livekit.service";          type = "system"; icon = "livekit"; })
    # Always-on infrastructure
    ++ [
      { name = "Caddy"; unit = "caddy.service"; type = "system"; icon = "caddy"; }
      { name = "Tor";   unit = "tor.service";   type = "system"; icon = "tor";   }
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
      pkgs.gdk-pixbuf
    ];

    propagatedBuildInputs = [
      pkgs.python3Packages.pygobject3
    ];

    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/lib/sovran-hub $out/share/applications $out/share/sovran-hub/icons

      # Copy Python source
      cp -r sovran_systemsos_hub $out/lib/sovran-hub/

      # Copy CSS
      cp style.css $out/lib/sovran-hub/style.css

      # Install the generated config
      cp ${generatedConfig} $out/lib/sovran-hub/config.json

      # Install logos
      cp -r ${logoDir}/* $out/share/sovran-hub/icons/

      # Create the launcher script
      cat > $out/bin/sovran-hub <<'LAUNCHER'
#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.join("@out@", "lib", "sovran-hub"))
os.environ["SOVRAN_HUB_CONFIG"] = os.path.join("@out@", "lib", "sovran-hub", "config.json")
os.environ["SOVRAN_HUB_ICONS"]  = os.path.join("@out@", "share", "sovran-hub", "icons")
os.environ["SOVRAN_HUB_CSS"]    = os.path.join("@out@", "lib", "sovran-hub", "style.css")
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
