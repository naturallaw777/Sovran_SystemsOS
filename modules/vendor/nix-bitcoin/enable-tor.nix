{ lib, config, ... }:
let
  defaultTrue = lib.mkDefault true;
  defaultEnableTorProxy = {
    tor.proxy = defaultTrue;
    tor.enforce = defaultTrue;
  };
  defaultEnforceTor = {
    tor.enforce = defaultTrue;
  };
in {
  services.tor = {
    enable = true;
    client.enable = true;
  };

  services = {
    # Use Tor as a proxy for outgoing connections
    # and restrict all connections to Tor
    #
    bitcoind = defaultEnableTorProxy;
    # clightning = defaultEnableTorProxy; # vendored: not needed (Sovran uses lnd)
    lnd = defaultEnableTorProxy;
    # lightning-loop = defaultEnableTorProxy; # vendored: not used
    # liquidd = defaultEnableTorProxy; # vendored: not used
    # TODO-EXTERNAL:
    # disable Tor enforcement until btcpayserver can fetch rates over Tor
    # btcpayserver = defaultEnableTorProxy;
    # lightning-pool = defaultEnableTorProxy; # vendored: not used
    mempool = defaultEnableTorProxy;

    # These services don't make outgoing connections
    # (or use Tor by default in case of joinmarket)
    # but we restrict them to Tor just to be safe.
    #
    electrs = defaultEnforceTor;
    # fulcrum = defaultEnforceTor; # vendored: not used
    nbxplorer = defaultEnforceTor;
    rtl = defaultEnforceTor;
    # joinmarket = defaultEnforceTor; # vendored: not used
    # joinmarket-ob-watcher = defaultEnforceTor; # vendored: not used
    # clightning-rest = defaultEnforceTor; # vendored: not used
  };

  # Add onion services for incoming connections
  nix-bitcoin.onionServices = {
    bitcoind.enable = defaultTrue;
    # liquidd.enable = defaultTrue; # stub
    electrs.enable = defaultTrue;
    # fulcrum.enable = defaultTrue; # stub
    # joinmarket-ob-watcher.enable = defaultTrue; # stub
    rtl.enable = defaultTrue;
  };
}
