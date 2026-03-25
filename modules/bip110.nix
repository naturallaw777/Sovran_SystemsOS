{ config, lib, pkgs, ... }:

let
  cfg = config.sovran_systemsOS;
in
{
  config = lib.mkIf (cfg.features.bip110 && cfg.bip110.package != null) {

    services.bitcoind.package = cfg.bip110.package;

    # Optional: also expose it in system packages if desired
    environment.systemPackages = [
      cfg.bip110.package
    ];
  };
}
