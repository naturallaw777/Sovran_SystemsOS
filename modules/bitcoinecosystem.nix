{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.services.bitcoin {

  services.bitcoind = {
    enable = true;
    package = config.nix-bitcoin.pkgs.bitcoind-knots;
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
    enable = true;
  };

  services.btcpayserver.lightningBackend = "lnd";

  nix-bitcoin.generateSecrets = true;
  nix-bitcoin.nodeinfo.enable = true;

  nix-bitcoin.operator = {
    enable = true;
    name = "free";
  };

  nix-bitcoin.useVersionLockedPkgs = false;
  
   sovran_systemsOS.domainRequirements = [
    { name = "btcpayserver"; label = "BTCPay Server"; example = "pay.yourdomain.com"; }
  ];
}
