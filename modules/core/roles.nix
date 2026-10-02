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

    # ── Hub ───────────────────────────────────────────────────
    hub = {
      lanOnly = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = ''
          Refuse Hub requests from clients that are not on this computer or on
          the local network: loopback, private (10.0.0.0/8, 172.16.0.0/12,
          192.168.0.0/16), VPN/CGNAT (100.64.0.0/10) and link-local addresses,
          plus anything listed in sovran_systemsOS.hub.extraLanNetworks.

          The Hub runs as root and can display stored credentials and reboot
          the machine. Whether a packet may reach its port is up to the
          firewall and your router; this check is the second lock, so that a
          port forward or a firewall mistake does not put the Hub's login page
          in front of the internet.

          Set it to false only if this computer sits on a network that hands
          out public addresses to your own devices and you would rather not
          list them.
        '';
      };

      directPort = lib.mkOption {
        type = lib.types.bool;
        default = !config.sovran_systemsOS.roles.desktop;
        defaultText = lib.literalExpression "!config.sovran_systemsOS.roles.desktop";
        description = ''
          Open port 8937 on the firewall, so that other devices on the local
          network can reach the Hub at http://sovransystemsos.local:8937.

          On by default for Server + Desktop and Bitcoin Node Only. Off on
          Desktop Only, the role most likely to be used away from home: there
          nothing is published, and the Hub is reachable only from this
          computer, through the desktop application window on localhost. Set it
          to true in custom.nix if you do want to reach a Desktop Only Hub from
          another device.

          The Hub runs as root, so it checks every client itself (see
          sovran_systemsOS.hub.lanOnly); the firewall opening only decides
          whether a packet may reach it at all.
        '';
      };

      extraLanNetworks = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ ];
        example = [ "203.0.113.0/28" ];
        description = ''
          Extra networks, in CIDR notation, that the Hub should treat as local
          in addition to the built-in ranges. Needed only if devices on your
          local network use addresses outside the private ranges, for example a
          public IPv4 block your provider routes onto your LAN.

          Keep each entry as narrow as you can: every address inside it is let
          through. To let everything through, set sovran_systemsOS.hub.lanOnly
          to false instead; 0.0.0.0/0 and ::/0 are not accepted here.
        '';
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
          address is the one Njal.la reports for the DDNS update (set up in
          the Hub's Domains page), and nothing on this system looks it up
          anywhere else. Set it for a fixed public address with no Njal.la
          DDNS entry, or to override the reported one (e.g. multi-WAN/VPN
          setups).
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
