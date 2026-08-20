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
      bitcoin-tor-gossip = lib.mkEnableOption "Advertise the Bitcoin Core onion service through Bitcoin peer gossip";
      # Compatibility shim for Hub-managed settings from releases where Core
      # was an optional replacement for the default node. Core is now always
      # selected when the Bitcoin service is enabled.
      bitcoin-core = lib.mkOption {
        type = lib.types.nullOr lib.types.bool;
        default = null;
        internal = true;
        visible = false;
        description = "Deprecated no-op: Bitcoin Core is the default node implementation.";
      };
      "nwc-wallets" = lib.mkEnableOption "Lightning Wallet Connections";
      rdp = lib.mkEnableOption "Gnome Remote Desktop";
      sshd = lib.mkEnableOption "SSH remote access";
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

    # ── Element Calling (video/audio) tuning ──────────────────
    elementCalling = {
      fullAccessHomeservers = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ ];
        example = [ "matrix.peer.example.com" ];
        description = ''
          Additional Matrix server_names (beyond this server itself) that may
          trigger LiveKit room creation on this server's SFU via lk-jwt-service.

          Not needed for the common federated setup: each participant's client
          always obtains its token from its own homeserver's JWT service and
          publishes to its own SFU, and the participant who starts a call
          creates the room on their own SFU — the remote user merely joins
          (joining does not require full access).

          Only set this for asymmetric cases: e.g. a peer homeserver that has
          no focus of its own, or calls whose first participant lands on this
          server's SFU but belongs to the peer.
        '';
      };
      externalIP = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        example = "203.0.113.10";
        description = ''
          Optional pin: force LiveKit to advertise this public IPv4 in its
          host/TURN ICE candidates. Not required in normal operation — the
          module auto-detects the public IP at runtime (HTTPS egress
          detection, falling back to STUN). Set it only to override a
          mis-detected address (e.g. multi-WAN/VPN setups).
        '';
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
