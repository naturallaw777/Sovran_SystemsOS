{ config, lib, pkgs, ... }:

lib.mkIf config.sovran_systemsOS.features.bip110 {

  services.bitcoind.packages = lib.mkForce bip110.packages.x86_64-linux.bitcoind-knots-bip-110;

}
