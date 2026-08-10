{ config, lib, ... }:

{
  config = lib.mkMerge [

    # Vendored nix-bitcoin is always imported via modules/vendor/nix-bitcoin/modules.nix.
    # This default satisfies the secrets assertion so Desktop-Only systems evaluate
    # without enabling any Bitcoin services.
    {
      nix-bitcoin.generateSecrets = lib.mkDefault true;
    }

    # ── Server+Desktop Role (default) ─────────────────────────
    (lib.mkIf config.sovran_systemsOS.roles.server_plus_desktop {
      sovran_systemsOS.web.btcpayserver = lib.mkDefault true;
    })

    # ── Desktop Only Role ─────────────────────────────────────
    (lib.mkIf config.sovran_systemsOS.roles.desktop {
      services.desktopManager.gnome.enable = true;

      # Force all server/node services and features off so they cannot be
      # accidentally enabled via custom.nix or option defaults on Desktop Only.
      sovran_systemsOS.services = {
        synapse = lib.mkForce false;
        bitcoin = lib.mkForce false;
        vaultwarden = lib.mkForce false;
        wordpress = lib.mkForce false;
        nextcloud = lib.mkForce false;
      };

      sovran_systemsOS.features = {
        haven = lib.mkForce false;
        mempool = lib.mkForce false;
        element-calling = lib.mkForce false;
        bitcoin-core = lib.mkForce false;
        "nwc-wallets" = lib.mkForce false;
      };

      sovran_systemsOS.web.btcpayserver = lib.mkForce false;
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

      sovran_systemsOS.features = {
        mempool = lib.mkDefault true;
      };

      sovran_systemsOS.web.btcpayserver = lib.mkDefault false;
    })

  ];
}
