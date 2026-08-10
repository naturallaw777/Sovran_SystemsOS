{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features.bitcoin-core {
  # Vendored nix-bitcoin now uses nixpkgs directly; no nix-bitcoin.pkgs indirection.
  # Use standard bitcoind from nixpkgs (override to knots if desired via pkgs.bitcoind-knots)
  services.bitcoind.package = lib.mkForce pkgs.bitcoind;
}
