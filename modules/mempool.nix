{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features.mempool {

  services.mempool = {
      enable = true;
      frontend.enable = true;
  };

  services.mysql.package = lib.mkForce pkgs.mariadb;

  nix-bitcoin.onionServices.mempool-frontend.enable = true;

}
