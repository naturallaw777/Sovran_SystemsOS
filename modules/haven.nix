{ config, pkgs, lib, ... }:

let
<<<<<<< HEAD
=======
  personalization = import ./personalization.nix;
>>>>>>> 5bee5ad99bb7890df011d88e9928b6944c3565f8
  npub = config.sovran_systemsOS.nostr_npub;
in

lib.mkIf (config.sovran_systemsOS.features.haven && npub != "") {

<<<<<<< HEAD
  # ── Caddy vhost is now handled centrally in caddy.nix ─────

  # ── Generate Haven runtime config from domain files ───────
  systemd.services.haven-runtime-config = {
    description = "Generate Haven runtime config from domain files";
    before = [ "haven.service" ];
    requiredBy = [ "haven.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.coreutils ];
    script = ''
      HAVEN=$(cat /var/lib/domains/haven)

      mkdir -p /run/haven

      cat > /run/haven/runtime.env <<EOF
      RELAY_URL=$HAVEN
      PRIVATE_RELAY_NAME=$HAVEN private relay
      PRIVATE_RELAY_DESCRIPTION=The Relay From 
      CHAT_RELAY_NAME=$HAVEN chat relay
      CHAT_RELAY_DESCRIPTION=a relay for private chats
      OUTBOX_RELAY_NAME=$HAVEN outbox relay
      OUTBOX_RELAY_DESCRIPTION=a relay and Blossom server for public messages and media
      INBOX_RELAY_NAME=$HAVEN inbox relay
      INBOX_RELAY_DESCRIPTION=send your interactions with my notes here
      EOF

      chmod 640 /run/haven/runtime.env
      chown haven:haven /run/haven/runtime.env
    '';
  };

=======
>>>>>>> 5bee5ad99bb7890df011d88e9928b6944c3565f8
  services.haven = {
    enable = true;
    settings = {
      OWNER_NPUB = npub;
<<<<<<< HEAD
      # RELAY_URL injected at runtime via EnvironmentFile
=======
      RELAY_URL = personalization.haven_url;
>>>>>>> 5bee5ad99bb7890df011d88e9928b6944c3565f8

      RELAY_PORT = 3355;
      RELAY_BIND_ADDRESS = "0.0.0.0";
      DB_ENGINE = "badger";
      LMDB_MAPSIZE = 3000000000;
      BLOSSOM_PATH = "blossom/";

<<<<<<< HEAD
      # Relay names/descriptions injected at runtime via EnvironmentFile
      PRIVATE_RELAY_NPUB = npub;
      CHAT_RELAY_NPUB = npub;
      OUTBOX_RELAY_NPUB = npub;

      INBOX_PULL_INTERVAL_SECONDS = 600;

=======
      PRIVATE_RELAY_NAME = "${personalization.haven_url} private relay";
      PRIVATE_RELAY_NPUB = npub;
      PRIVATE_RELAY_DESCRIPTION = "The Relay From Sovran Systems";

      CHAT_RELAY_NAME = "${personalization.haven_url} chat relay";
      CHAT_RELAY_NPUB = npub;
      CHAT_RELAY_DESCRIPTION = "a relay for private chats";

      OUTBOX_RELAY_NAME = "${personalization.haven_url} outbox relay";
      OUTBOX_RELAY_NPUB = npub;
      OUTBOX_RELAY_DESCRIPTION = "a relay and Blossom server for public messages and media";

      INBOX_RELAY_NAME = "${personalization.haven_url} inbox relay";
      INBOX_RELAY_NPUB = npub;
      INBOX_RELAY_DESCRIPTION = "send your interactions with my notes here";

      INBOX_PULL_INTERVAL_SECONDS = 600;

      # ... all your rate limiter and WOT settings unchanged ...
>>>>>>> 5bee5ad99bb7890df011d88e9928b6944c3565f8
      PRIVATE_RELAY_EVENT_IP_LIMITER_TOKENS_PER_INTERVAL = 50;
      PRIVATE_RELAY_EVENT_IP_LIMITER_INTERVAL = 1;
      PRIVATE_RELAY_EVENT_IP_LIMITER_MAX_TOKENS = 100;
      PRIVATE_RELAY_ALLOW_EMPTY_FILTERS = true;
      PRIVATE_RELAY_ALLOW_COMPLEX_FILTERS = true;
      PRIVATE_RELAY_CONNECTION_RATE_LIMITER_TOKENS_PER_INTERVAL = 3;
      PRIVATE_RELAY_CONNECTION_RATE_LIMITER_INTERVAL = 5;
      PRIVATE_RELAY_CONNECTION_RATE_LIMITER_MAX_TOKENS = 9;

      CHAT_RELAY_WOT_DEPTH = 3;
      CHAT_RELAY_WOT_REFRESH_INTERVAL_HOURS = 24;
      CHAT_RELAY_MINIMUM_FOLLOWERS = 3;
      CHAT_RELAY_EVENT_IP_LIMITER_TOKENS_PER_INTERVAL = 50;
      CHAT_RELAY_EVENT_IP_LIMITER_INTERVAL = 1;
      CHAT_RELAY_EVENT_IP_LIMITER_MAX_TOKENS = 100;
      CHAT_RELAY_ALLOW_EMPTY_FILTERS = false;
      CHAT_RELAY_ALLOW_COMPLEX_FILTERS = false;
      CHAT_RELAY_CONNECTION_RATE_LIMITER_TOKENS_PER_INTERVAL = 3;
      CHAT_RELAY_CONNECTION_RATE_LIMITER_INTERVAL = 3;
      CHAT_RELAY_CONNECTION_RATE_LIMITER_MAX_TOKENS = 9;

      OUTBOX_RELAY_EVENT_IP_LIMITER_TOKENS_PER_INTERVAL = 100;
      OUTBOX_RELAY_EVENT_IP_LIMITER_INTERVAL = 600;
      OUTBOX_RELAY_EVENT_IP_LIMITER_MAX_TOKENS = 1000;
      OUTBOX_RELAY_ALLOW_EMPTY_FILTERS = true;
      OUTBOX_RELAY_ALLOW_COMPLEX_FILTERS = true;
      OUTBOX_RELAY_CONNECTION_RATE_LIMITER_TOKENS_PER_INTERVAL = 30;
      OUTBOX_RELAY_CONNECTION_RATE_LIMITER_INTERVAL = 10;
      OUTBOX_RELAY_CONNECTION_RATE_LIMITER_MAX_TOKENS = 90;

      INBOX_RELAY_EVENT_IP_LIMITER_TOKENS_PER_INTERVAL = 10;
      INBOX_RELAY_EVENT_IP_LIMITER_INTERVAL = 1;
      INBOX_RELAY_EVENT_IP_LIMITER_MAX_TOKENS = 20;
      INBOX_RELAY_ALLOW_EMPTY_FILTERS = false;
      INBOX_RELAY_ALLOW_COMPLEX_FILTERS = false;
      INBOX_RELAY_CONNECTION_RATE_LIMITER_TOKENS_PER_INTERVAL = 3;
      INBOX_RELAY_CONNECTION_RATE_LIMITER_INTERVAL = 1;
      INBOX_RELAY_CONNECTION_RATE_LIMITER_MAX_TOKENS = 9;

      WOT_FETCH_TIMEOUT_SECONDS = 60;
      WHITELISTED_NPUBS_FILE = "/var/lib/haven/whitelisted_npubs.json";
      BLACKLISTED_NPUBS_FILE = "";
      HAVEN_LOG_LEVEL = "INFO";
    };

    blastrRelays = [
      "nos.lol"
      "relay.nostr.band"
      "relay.snort.social"
      "nostr.mom"
      "relay.primal.net"
      "no.str.cr"
      "nostr21.com"
      "nostrue.com"
      "wot.nostr.party"
      "wot.sovbit.host"
      "wot.girino.org"
      "relay.lexingtonbitcoin.org"
      "zap.watch"
      "satsage.xyz"
      "wons.calva.dev"
    ];
  };

<<<<<<< HEAD
  systemd.services.haven.serviceConfig.EnvironmentFile = [
    "/run/haven/runtime.env"
  ];

=======
>>>>>>> 5bee5ad99bb7890df011d88e9928b6944c3565f8
  systemd.tmpfiles.rules = [
    "d /var/lib/haven 0750 haven haven -"
  ];

  systemd.services.haven-whitelist-setup = {
    description = "Ensure Haven whitelisted_npubs.json is valid";
    wantedBy = [ "multi-user.target" ];
    before = [ "haven.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = ''
      FILE="/var/lib/haven/whitelisted_npubs.json"
      if [ ! -s "$FILE" ] || ! ${pkgs.jq}/bin/jq empty "$FILE" 2>/dev/null; then
        echo '[]' > "$FILE"
        chown haven:haven "$FILE"
        chmod 770 "$FILE"
        echo "Wrote valid empty JSON array to $FILE"
      else
        echo "$FILE already contains valid JSON, skipping"
      fi
    '';
  };

<<<<<<< HEAD
  systemd.services.haven.after = [ "haven-whitelist-setup.service" "haven-runtime-config.service" ];
  systemd.services.haven.wants = [ "haven-whitelist-setup.service" "haven-runtime-config.service" ];
=======
  systemd.services.haven.after = [ "haven-whitelist-setup.service" ];
  systemd.services.haven.wants = [ "haven-whitelist-setup.service" ];

  services.caddy.virtualHosts = {
    "${personalization.haven_url}" = {
      extraConfig = ''
        reverse_proxy localhost:3355 {
          header_up Host {host}
          header_up X-Real-IP {remote_host}
          header_up X-Forwarded-For {remote_host}
          header_up X-Forwarded-Proto {scheme}
          transport http {
            versions 1.1
          }
        }
        request_body {
          max_size 100MB
        }
      '';
    };
  };
>>>>>>> 5bee5ad99bb7890df011d88e9928b6944c3565f8
}
