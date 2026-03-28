{ config, lib, ... }:

{
  options.sovran_systemsOS = {
    roles = {
      server-desktop = lib.mkOption {
        type = lib.types.bool;
        default = !config.sovran_systemsOS.roles.desktop && !config.sovran_systemsOS.roles.node;
      };
      desktop = lib.mkEnableOption "Desktop Role";
      node = lib.mkEnableOption "Bitcoin Node Only Role";
    };

    # ── Services (default ON — user can disable in custom.nix) ──
    services = {
      synapse = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Matrix Synapse homeserver";
      };
      bitcoin = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Bitcoin Ecosystem (bitcoind, electrs, lnd, rtl, btcpay)";
      };
      vaultwarden = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Vaultwarden password manager";
      };
      wordpress = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "WordPress (raw PHP served by Caddy)";
      };
      nextcloud = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Nextcloud (raw PHP served by Caddy)";
      };
    };

    # ── Features (default OFF — user can enable in custom.nix) ──
    features = {
      haven = lib.mkEnableOption "Haven NOSTR relay";
      bip110 = lib.mkEnableOption "BIP-110 Bitcoin Better Money";
      mempool = lib.mkEnableOption "Bitcoin Mempool Explorer";
      element-calling = lib.mkEnableOption "Element Video and Audio Calling";
      bitcoin-core = lib.mkEnableOption "Bitcoin Core";
      rdp = lib.mkEnableOption "Gnome Remote Desktop";
    };

    # ── Web exposure (controls Caddy vhosts) ──────────────────
    web = {
      btcpayserver = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Expose BTCPay Server via Caddy";
      };
    };

    # ── Domain setup registry ─────────────────────────────────
    domainRequirements = lib.mkOption {
      type = lib.types.listOf (lib.types.submodule {
        options = {
          name = lib.mkOption { type = lib.types.str; };
          label = lib.mkOption { type = lib.types.str; };
          example = lib.mkOption { type = lib.types.str; };
          needsDDNS = lib.mkOption { type = lib.types.bool; default = true; };
        };
      });
      default = [];
      description = "Domain requirements registered by each module";
    };

    nostr_npub = lib.mkOption {
      type = lib.types.str;
      default = "";
      description = "Nostr public key (npub1...) for Haven relay";
    };
  };
}
