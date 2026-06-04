{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.services.bitcoin {

  services.bitcoind = {
    enable = true;
    package = pkgs.bitcoind-knots;
    dataDir = "/run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node";
    txindex = true;
    tor.proxy = true;
    tor.enforce = true;
    disablewallet = true;
    extraConfig = ''
      peerbloomfilters=1
      server=1
    '';
  };

  nix-bitcoin.onionServices.bitcoind.enable = true;
  nix-bitcoin.onionServices.electrs.enable = true;
  nix-bitcoin.onionServices.rtl.enable = true;

  services.electrs = {
    enable = true;
    tor.enforce = true;
    dataDir = "/run/media/Second_Drive/BTCEcoandBackup/Electrs_Data";
  };

  services.lnd = {
    enable = true;
    tor.enforce = true;
    tor.proxy = true;
    extraConfig = ''
      protocol.option-scid-alias=true
    '';
  };

  nix-bitcoin.onionServices.lnd.public = true;

  services.lnd.lndconnect = {
    enable = true;
    onion = true;
  };

  services.rtl = {
    enable = true;
    tor.enforce = true;
    port = 3050;
    nightTheme = true;
    nodes = {
      lnd = {
        enable = true;
      };
    };
  };

  services.btcpayserver = {
    enable = config.sovran_systemsOS.web.btcpayserver;
  };

  services.btcpayserver.lightningBackend = "lnd";

  nix-bitcoin.generateSecrets = true;
  nix-bitcoin.nodeinfo.enable = true;

  nix-bitcoin.operator = {
    enable = true;
    name = "free";
  };

  nix-bitcoin.useVersionLockedPkgs = false;

  systemd.services.bitcoind = {
    requires = [ "run-media-Second_Drive.mount" ];
    after    = [ "run-media-Second_Drive.mount" ];
    serviceConfig.PrivateUsers = lib.mkForce false;
  };

  systemd.services.electrs = {
    requires = lib.mkForce [ "run-media-Second_Drive.mount" ];
    after    = [ "run-media-Second_Drive.mount" "bitcoind.service" ];
    wants    = [ "bitcoind.service" ];
  };

  systemd.services.lnd = {
    wants = [ "bitcoind.service" ];
    # requires for bitcoind set by nix-bitcoin; mkForce removes it
    requires = lib.mkForce [ ];
  };

  systemd.services.sovran-btc-permissions = {
    description = "Fix Bitcoin/Electrs data directory ownership on second drive";
    wantedBy = [ "multi-user.target" ];
    after = [ "run-media-Second_Drive.mount" ];
    before = [ "bitcoind.service" "electrs.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = ''
      if [ -d /run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node ]; then
        chown -R bitcoin:bitcoin /run/media/Second_Drive/BTCEcoandBackup/Bitcoin_Node
      fi
      if [ -d /run/media/Second_Drive/BTCEcoandBackup/Electrs_Data ]; then
        chown -R electrs:electrs /run/media/Second_Drive/BTCEcoandBackup/Electrs_Data
      fi
    '';
  };

  networking.firewall.allowedTCPPorts = [ 3051 ];
  networking.firewall.allowedUDPPorts = [ 3051 ];

  sovran_systemsOS.domainRequirements = [
    { name = "btcpayserver"; label = "BTCPay Server"; example = "pay.yourdomain.com"; }
  ];
}
