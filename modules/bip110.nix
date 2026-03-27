{ config, lib, pkgs, ... }:

let
  cfg = config.sovran_systemsOS;
in
{
<<<<<<< HEAD
=======
  # ✅ Option definition
>>>>>>> 5bee5ad99bb7890df011d88e9928b6944c3565f8
  options.sovran_systemsOS.packages.bip110 = lib.mkOption {
    type = lib.types.nullOr lib.types.package;
    default = null;
    description = "BIP110 Bitcoin package";
  };

<<<<<<< HEAD
=======
  # ✅ Implementation
>>>>>>> 5bee5ad99bb7890df011d88e9928b6944c3565f8
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
