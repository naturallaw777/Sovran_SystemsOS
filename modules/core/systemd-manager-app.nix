{ config, lib, pkgs, ... }:

let
  cfg = config.sovran_systemsOS;

  monitoredServices =
    # ── Always-on core services ─────────────────────────────────
    [
      { name = "Caddy";    unit = "caddy.service";    type = "system"; }
      { name = "Tor";      unit = "tor.service";      type = "system"; }
      { name = "PostgreSQL"; unit = "postgresql.service"; type = "system"; }
      { name = "Fail2Ban"; unit = "fail2ban.service"; type = "system"; }
      { name = "SSH";      unit = "sshd.service";     type = "system"; }
    ]
    # ── cfg.services.bitcoin ────────────────────────────────────
    ++ lib.optionals cfg.services.bitcoin [
      { name = "Bitcoind";        unit = "bitcoind.service";     type = "system"; }
      { name = "Electrs";         unit = "electrs.service";      type = "system"; }
      { name = "LND";             unit = "lnd.service";          type = "system"; }
      { name = "Ride The Lightning"; unit = "rtl.service";       type = "system"; }
      { name = "BTCPayserver";    unit = "btcpayserver.service"; type = "system"; }
    ]
    # ── cfg.services.synapse ────────────────────────────────────
    ++ lib.optionals cfg.services.synapse [
      { name = "Matrix-Synapse"; unit = "matrix-synapse.service"; type = "system"; }
      { name = "Coturn";         unit = "coturn.service";         type = "system"; }
    ]
    # ── cfg.services.vaultwarden ────────────────────────────────
    ++ lib.optionals cfg.services.vaultwarden [
      { name = "VaultWarden"; unit = "vaultwarden.service"; type = "system"; }
    ]
    # ── cfg.services.nextcloud ──────────────────────────────────
    ++ lib.optionals cfg.services.nextcloud [
      { name = "Nextcloud"; unit = "phpfpm-nextcloud.service"; type = "system"; }
    ]
    # ── cfg.services.wordpress ──────────────────────────────────
    ++ lib.optionals cfg.services.wordpress [
      { name = "WordPress"; unit = "phpfpm-wordpress.service"; type = "system"; }
    ]
    # ── cfg.features.haven ──────────────────────────────────────
    ++ lib.optionals cfg.features.haven [
      { name = "Haven Relay"; unit = "haven-relay.service"; type = "system"; }
    ]
    # ── cfg.features.mempool ────────────────────────────────────
    ++ lib.optionals cfg.features.mempool [
      { name = "Mempool"; unit = "mempool.service"; type = "system"; }
    ]
    # ── cfg.features.element-calling ────────────────────────────
    ++ lib.optionals cfg.features.element-calling [
      { name = "LiveKit"; unit = "livekit.service"; type = "system"; }
    ];

  appConfig = pkgs.writeText "systemd-manager-config.json" (builtins.toJSON {
    refresh_interval = 5;
    command_method   = "systemctl";
    services         = monitoredServices;
  });

  systemdManagerApp = pkgs.python3Packages.buildPythonApplication {
    pname   = "systemd-manager-gtk";
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
    ];

    propagatedBuildInputs = with pkgs.python3Packages; [
      pygobject3
    ];

    dontBuild = true;

    installPhase = ''
      runHook preInstall

      # ── Python source ──────────────────────────────────────────
      install -d $out/lib/systemd-manager-gtk
      cp -r systemd_manager $out/lib/systemd-manager-gtk/

      # ── Generated config ───────────────────────────────────────
      cp ${appConfig} $out/lib/systemd-manager-gtk/config.json

      # ── Launcher script ────────────────────────────────────────
      install -d $out/bin
      cat > $out/bin/systemd-manager-gtk <<'EOF'
      #!${pkgs.python3}/bin/python3
      import os, sys
      os.environ.setdefault(
          "SYSTEMD_MANAGER_CONFIG",
          os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       "../lib/systemd-manager-gtk/config.json"),
      )
      sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                      "../lib/systemd-manager-gtk"))
      from systemd_manager.application import SystemdManagerApp
      app = SystemdManagerApp()
      sys.exit(app.run(sys.argv))
      EOF
      chmod +x $out/bin/systemd-manager-gtk

      # ── .desktop file ──────────────────────────────────────────
      install -d $out/share/applications
      cat > $out/share/applications/systemd-manager-gtk.desktop <<EOF
      [Desktop Entry]
      Name=Systemd Manager
      Comment=Manage systemd services
      Exec=systemd-manager-gtk
      Icon=system-run
      Terminal=false
      Type=Application
      Categories=System;Settings;
      EOF

      runHook postInstall
    '';
  };

in

{
  environment.systemPackages = [ systemdManagerApp ];
}
