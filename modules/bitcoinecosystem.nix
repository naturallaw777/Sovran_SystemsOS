{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.services.bitcoin {

  services.bitcoind = {
    enable = true;
    # Keep the normal loopback P2P socket available for local clients such as
    # Bisq. Because `address` defaults to 127.0.0.1 this does not expose a
    # clearnet or LAN listener. When the existing bitcoind onion service is
    # enabled, this also creates its Tor-tagged loopback target on port 8334.
    listen = true;
    package = pkgs.bitcoind;
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

  nix-bitcoin.onionServices.bitcoind = {
    enable = true;
    # This is a locally vendored option namespace, not an upstream dependency.
    # The onion listener remains available to peers that already know it;
    # advertising its address through Bitcoin peer gossip is opt-in in the Hub.
    public = config.sovran_systemsOS.features.bitcoin-tor-gossip;
  };
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

  # vendored: now no-op (always uses nixpkgs)
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
