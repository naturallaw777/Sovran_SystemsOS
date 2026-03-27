{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features.mempool {

  services.mempool = {
      enable = true;
      frontend.enable = true;
  };

  services.mysql.package = lib.mkForce pkgs.mariadb;

  nix-bitcoin.onionServices.mempool-frontend.enable = true;

  services.caddy = {
      virtualHosts = {
          ":60847" = {
              extraConfig = ''
                  reverse_proxy :60845
                  encode gzip zstd
              '';
          };
      };
  };

}
