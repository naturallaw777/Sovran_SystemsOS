{ config, lib, ... }:

{
  options.sovran_systemsOS = {
    roles = {
      server_plus_desktop = lib.mkOption {
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
      mempool = lib.mkEnableOption "Bitcoin Mempool Explorer";
      element-calling = lib.mkEnableOption "Element Video and Audio Calling";
      bitcoin-core = lib.mkEnableOption "Bitcoin Core";
      "nwc-wallets" = lib.mkEnableOption "Wallet Connections";
      rdp = lib.mkEnableOption "Gnome Remote Desktop";
      sshd = lib.mkEnableOption "SSH remote access";

      # Deprecated: BIP-110 is now built into mainline Bitcoin Knots and is the
      # default node. This option is retained ONLY so that existing machines with
      # `sovran_systemsOS.features.bip110 = lib.mkForce true;` left in their local
      # custom.nix continue to evaluate. It has no effect and will be removed in a
      # future release once the Hub has cleaned up old custom.nix files.
      bip110 = lib.mkOption {
        type = lib.types.nullOr lib.types.bool;
        default = null;
        internal = true;
        visible = false;
        description = "(Deprecated, no-op) BIP-110 is now built into Bitcoin Knots.";
      };
    };

    # ── Web exposure (controls Caddy vhosts) ──────────────────
    web = {
      btcpayserver = lib.mkOption {
        type = lib.types.bool;
        default = false;
        description = "Expose BTCPay Server via Caddy";
      };
    };

    # ── Caddy customisation ───────────────────────────────────
    caddy = {
      extraVirtualHosts = lib.mkOption {
        type = lib.types.lines;
        default = "";
        description = "Additional raw Caddyfile blocks appended to the generated Caddy config. Use this in custom.nix to add custom domains and reverse proxies.";
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

  config = lib.mkIf (config.sovran_systemsOS.features.bip110 != null) {
    warnings = [
      ''
        sovran_systemsOS.features.bip110 is deprecated and has no effect:
        BIP-110 is now built into mainline Bitcoin Knots, which is the default node.
        You can safely remove the `sovran_systemsOS.features.bip110` line from
        /etc/nixos/custom.nix. The Sovran Hub will also remove it automatically.
      ''
    ];
  };
}
