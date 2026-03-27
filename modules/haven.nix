{ config, pkgs, lib, ... }:

let
  npub = config.sovran_systemsOS.nostr_npub;
in

lib.mkIf (config.sovran_systemsOS.features.haven && npub != "") {

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
PRIVATE_RELAY_DESCRIPTION=The Relay From Sovran Systems
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

  services.haven = {
    enable = true;
    settings = {
      OWNER_NPUB = npub;
      # RELAY_URL injected at runtime via EnvironmentFile

      RELAY_PORT = 3355;
      RELAY_BIND_ADDRESS = "0.0.0.0";
      DB_ENGINE = "badger";
      LMDB_MAPSIZE = 3000000000;
      BLOSSOM_PATH = "blossom/";

      # Relay names/descriptions injected at runtime via EnvironmentFile
      PRIVATE_RELAY_NPUB = npub;
      CHAT_RELAY_NPUB = npub;
      OUTBOX_RELAY_NPUB = npub;

      INBOX_PULL_INTERVAL_SECONDS = 600;

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

  systemd.services.haven.serviceConfig.EnvironmentFile = [
    "/run/haven/runtime.env"
  ];

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

  systemd.services.haven.after = [ "haven-whitelist-setup.service" "haven-runtime-config.service" ];
  systemd.services.haven.wants = [ "haven-whitelist-setup.service" "haven-runtime-config.service" ];
}
