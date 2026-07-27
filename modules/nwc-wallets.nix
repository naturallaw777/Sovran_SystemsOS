{ config, pkgs, lib, ... }:

let
  albyHubPort = 18080;
  albyHubApiBase = "http://127.0.0.1:${toString albyHubPort}";
  patchedAlbyHub = pkgs.albyhub.overrideAttrs (old: {
    patches = (old.patches or []) ++ [
      ../packages/albyhub/0001-private-route-hints.patch
      ../packages/albyhub/0002-isolated-invoice-app-id.patch
      ../packages/albyhub/0003-loopback-bind-host.patch
    ];
  });

  lndRpcAddress = lib.attrByPath [ "services" "lnd" "rpcAddress" ] "127.0.0.1" config;
  lndRpcPort = toString (lib.attrByPath [ "services" "lnd" "rpcPort" ] 10009 config);
  lndCertPath = lib.attrByPath [ "services" "lnd" "certPath" ] "/var/lib/lnd/tls.cert" config;

  albyhubWrapper = pkgs.writeShellScript "albyhub-wrapper" ''
    set -euo pipefail
    password_file="/var/lib/albyhub/unlock-password"
    if [ ! -s "$password_file" ]; then
      umask 077
      ${pkgs.openssl}/bin/openssl rand -hex 32 > "$password_file"
    fi
    export AUTO_UNLOCK_PASSWORD="$(cat "$password_file")"
    exec ${lib.getExe patchedAlbyHub}
  '';
in
lib.mkIf config.sovran_systemsOS.features."nwc-wallets" {
  assertions = [
    {
      assertion = config.services.lnd.enable;
      message = "Wallet Connections requires services.lnd.enable = true.";
    }
    {
      assertion = !(lib.attrByPath [ "nix-bitcoin" "netns-isolation" "enable" ] false config);
      message = "Wallet Connections requires nix-bitcoin.netns-isolation.enable = false.";
    }
    {
      assertion = albyHubPort != config.services.lnd.restPort;
      message = "Alby Hub and LND REST must use different ports.";
    }
    {
      assertion = albyHubPort != 8181;
      message = "Alby Hub and the public LNURL service must use different ports.";
    }
    {
      assertion = !(lib.elem albyHubPort config.networking.firewall.allowedTCPPorts);
      message = "Alby Hub management port must not be opened on the public TCP firewall.";
    }
  ];

  users.groups.albyhub = { };
  users.users.albyhub = {
    isSystemUser = true;
    group = "albyhub";
    home = "/var/lib/albyhub";
    createHome = false;
    extraGroups = [ ];
  };

  systemd.tmpfiles.rules = [
    "d /var/lib/albyhub       0700 albyhub albyhub -"
  ];

  services.lnd.macaroons.albyhub = {
    user = "albyhub";
    permissions = lib.concatStringsSep "," [
      ''{"entity":"info","action":"read"}''
      ''{"entity":"offchain","action":"read"}''
      ''{"entity":"offchain","action":"write"}''
      ''{"entity":"invoices","action":"read"}''
      ''{"entity":"invoices","action":"write"}''
      ''{"entity":"onchain","action":"read"}''
      ''{"entity":"address","action":"read"}''
      ''{"entity":"message","action":"read"}''
      ''{"entity":"message","action":"write"}''
    ];
  };

  systemd.services.albyhub = {
    description = "Alby Hub — NWC wallet server";
    wantedBy = [ "multi-user.target" ];
    after = [ "network.target" "lnd.service" ];
    requires = [ "lnd.service" ];

    environment = {
      HOME = "/var/lib/albyhub";
      HOST = "127.0.0.1";
      LN_BACKEND_TYPE = "LND";
      ENABLE_ADVANCED_SETUP = "false";
      LND_ADDRESS = "${lndRpcAddress}:${lndRpcPort}";
      LND_CERT_FILE = lndCertPath;
      LND_MACAROON_FILE = "/run/lnd/albyhub.macaroon";
      WORK_DIR = "/var/lib/albyhub";
      DATABASE_URI = "/var/lib/albyhub/nwc.db";
      PORT = toString albyHubPort;
      RELAY = "wss://relay.getalby.com,wss://relay2.getalby.com";
      AUTO_LINK_ALBY_ACCOUNT = "false";
      SEND_EVENTS_TO_ALBY = "false";
      LOG_TO_FILE = "false";
      HIDE_UPDATE_BANNER = "true";
    };

    serviceConfig = {
      Type = "simple";
      User = "albyhub";
      Group = "albyhub";
      WorkingDirectory = "/var/lib/albyhub";
      ExecStart = albyhubWrapper;
      Restart = "on-failure";
      RestartSec = "10s";
      UMask = "0077";
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectHome = true;
      ProtectSystem = "strict";
      ReadWritePaths = [ "/var/lib/albyhub" ];
      ReadOnlyPaths = [ lndCertPath "/run/lnd" ];
    };
  };

  systemd.services.nwc-lnurl = {
    description = "Wallet Connections public LNURL service";
    wantedBy = [ "multi-user.target" ];
    after = [ "albyhub.service" "sovran-hub-web.service" ];
    wants = [ "albyhub.service" ];
    environment.NWC_ALBY_HUB_API_BASE = albyHubApiBase;

    serviceConfig = {
      Type = "simple";
      User = "albyhub";
      Group = "albyhub";
      ExecStart = "${config.services.sovranHub.webPackage}/bin/nwc-lnurl";
      Restart = "on-failure";
      RestartSec = "10s";
      UMask = "0027";
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectHome = true;
      ProtectSystem = "strict";
      ReadOnlyPaths = [
        "/var/lib/domains/lightning"
        "/var/lib/albyhub/unlock-password"
      ];
    };
  };

  systemd.services.sovran-hub-web.environment = {
    NWC_ALBY_HUB_API_BASE = albyHubApiBase;
    NWC_LND_ADDRESS = "${lndRpcAddress}:${lndRpcPort}";
    NWC_LND_CERT_FILE = lndCertPath;
    NWC_LND_MACAROON_FILE = "/run/lnd/albyhub.macaroon";
  };

  sovran_systemsOS.domainRequirements = [
    {
      name = "lightning";
      label = "Lightning Address Domain";
      example = "pay.yourdomain.com";
      needsDDNS = true;
    }
  ];
}
