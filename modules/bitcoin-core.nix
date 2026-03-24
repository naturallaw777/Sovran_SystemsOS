{ config, pkgs, lib, ... }:

{

  services.bitcoind.package = lib.mkForce config.nix-bitcoin.pkgs.bitcoind;

}
