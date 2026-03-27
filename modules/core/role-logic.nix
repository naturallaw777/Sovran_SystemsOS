{ config, lib, ... }:

{
  config = lib.mkMerge [

    # ── Server-Desktop Role (default) ─────────────────────────
    (lib.mkIf config.sovran_systemsOS.roles.server-desktop {
    })

    # ── Desktop Only Role ─────────────────────────────────────
    (lib.mkIf config.sovran_systemsOS.roles.desktop {
      services.xserver.enable = true;
      services.desktopManager.gnome.enable = true;

      sovran_systemsOS.services = {
        synapse = lib.mkDefault false;
        bitcoin = lib.mkDefault false;
        vaultwarden = lib.mkDefault false;
        wordpress = lib.mkDefault false;
        nextcloud = lib.mkDefault false;
      };

      sovran_systemsOS.web.btcpayserver = lib.mkDefault false;
    })

    # ── Bitcoin Node Only Role ────────────────────────────────
    # Bitcoin ecosystem + mempool, BTCPay runs but not exposed via Caddy
    (lib.mkIf config.sovran_systemsOS.roles.node {
      sovran_systemsOS.services = {
        bitcoin = lib.mkDefault true;
        synapse = lib.mkDefault false;
        vaultwarden = lib.mkDefault false;
        wordpress = lib.mkDefault false;
        nextcloud = lib.mkDefault false;
      };

      sovran_systemsOS.features.mempool = lib.mkDefault true;

      sovran_systemsOS.web.btcpayserver = lib.mkDefault false;
    })

  ];
}
