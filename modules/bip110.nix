{ config, lib, pkgs, ... }:

let
  cfg = config.sovran_systemsOS;
in
{
  options.sovran_systemsOS = {
    features.bip110 = lib.mkEnableOption "Enable BIP110 bitcoind";

    bip110.package = lib.mkOption {
      type = lib.types.nullOr lib.types.package;
      default = null;
      description = "Custom bitcoind package for BIP110";
    };
  };

  config = lib.mkIf (cfg.features.bip110 && cfg.bip110.package != null) {
    services.bitcoind.package = cfg.bip110.package;
  };
}
