{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features.bitcoin-core {
  
  services.bitcoind.package = lib.mkForce config.nix-bitcoin.pkgs.bitcoind;

}
