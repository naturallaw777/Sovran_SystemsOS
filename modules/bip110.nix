{ config, lib, pkgs, ... }:

let
  cfg = config.sovran_systemsOS;
in
{
  options.sovran_systemsOS.packages.bip110 = lib.mkOption {
    type = lib.types.nullOr lib.types.package;
    default = null;
    description = "BIP110 Bitcoin package";
  };

  config = lib.mkIf (
    cfg.features.bip110 &&
    cfg.packages.bip110 != null
  ) {
    services.bitcoind.package = lib.mkForce cfg.packages.bip110;

    environment.systemPackages = [
      cfg.packages.bip110
    ];
  };
}
