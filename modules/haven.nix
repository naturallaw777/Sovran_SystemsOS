{config, pkgs, lib, ...}:

let

personalization = import ./personalization.nix;

in

{

	services.haven = {
		enable = true;
		settings = {
			OWNER_NPUB="";
			RELAY_URL="*name*";

			RELAY_PORT=3355;
			RELAY_BIND_ADDRESS="0.0.0.0"; # Can be set to a specific IP4 or IP6 address ("" for all interfaces)
			DB_ENGINE="badger"; # badger, lmdb (lmdb works best with an nvme, otherwise you might have stability issues)
			LMDB_MAPSIZE=3000000000; # 0 for default (currently ~273GB), or set to a different size in bytes, e.g. 10737418240 for 10GB
			BLOSSOM_PATH="blossom/";

## Private Relay Settings
			PRIVATE_RELAY_NAME="*name* private relay";
			PRIVATE_RELAY_NPUB="";
			PRIVATE_RELAY_DESCRIPTION="The Relay From Sovran Systems";
#PRIVATE_RELAY_ICON="https://i.nostr.build/6G6wW.gif"

## Private Relay Rate Limiters
			PRIVATE_RELAY_EVENT_IP_LIMITER_TOKENS_PER_INTERVAL=50;
			PRIVATE_RELAY_EVENT_IP_LIMITER_INTERVAL=1;
			PRIVATE_RELAY_EVENT_IP_LIMITER_MAX_TOKENS=100;
			PRIVATE_RELAY_ALLOW_EMPTY_FILTERS=true;
			PRIVATE_RELAY_ALLOW_COMPLEX_FILTERS=true;
			PRIVATE_RELAY_CONNECTION_RATE_LIMITER_TOKENS_PER_INTERVAL=3;
			PRIVATE_RELAY_CONNECTION_RATE_LIMITER_INTERVAL=5;
			PRIVATE_RELAY_CONNECTION_RATE_LIMITER_MAX_TOKENS=9;

## Chat Relay Settings
			CHAT_RELAY_NAME="*name* chat relay";
			CHAT_RELAY_NPUB="";
			CHAT_RELAY_DESCRIPTION="a relay for private chats";
#CHAT_RELAY_ICON="https://i.nostr.build/6G6wW.gif"
			CHAT_RELAY_WOT_DEPTH=3;
			CHAT_RELAY_WOT_REFRESH_INTERVAL_HOURS=24;
			CHAT_RELAY_MINIMUM_FOLLOWERS=3;

## Chat Relay Rate Limiters
			CHAT_RELAY_EVENT_IP_LIMITER_TOKENS_PER_INTERVAL=50;
			CHAT_RELAY_EVENT_IP_LIMITER_INTERVAL=1;
			CHAT_RELAY_EVENT_IP_LIMITER_MAX_TOKENS=100;
			CHAT_RELAY_ALLOW_EMPTY_FILTERS=false;
			CHAT_RELAY_ALLOW_COMPLEX_FILTERS=false;
			CHAT_RELAY_CONNECTION_RATE_LIMITER_TOKENS_PER_INTERVAL=3;
			CHAT_RELAY_CONNECTION_RATE_LIMITER_INTERVAL=3;
			CHAT_RELAY_CONNECTION_RATE_LIMITER_MAX_TOKENS=9;

## Outbox Relay Settings
			OUTBOX_RELAY_NAME="*name* outbox relay";
			OUTBOX_RELAY_NPUB="";
			OUTBOX_RELAY_DESCRIPTION="a relay and Blossom server for public messages and media";
#OUTBOX_RELAY_ICON="https://i.nostr.build/6G6wW.gif"

## Outbox Relay Rate Limiters
			OUTBOX_RELAY_EVENT_IP_LIMITER_TOKENS_PER_INTERVAL=100;
			OUTBOX_RELAY_EVENT_IP_LIMITER_INTERVAL=600;
			OUTBOX_RELAY_EVENT_IP_LIMITER_MAX_TOKENS=1000;
			OUTBOX_RELAY_ALLOW_EMPTY_FILTERS=true;
			OUTBOX_RELAY_ALLOW_COMPLEX_FILTERS=true;
			OUTBOX_RELAY_CONNECTION_RATE_LIMITER_TOKENS_PER_INTERVAL=30;
			OUTBOX_RELAY_CONNECTION_RATE_LIMITER_INTERVAL=10;
			OUTBOX_RELAY_CONNECTION_RATE_LIMITER_MAX_TOKENS=90;

## Inbox Relay Settings
			INBOX_RELAY_NAME="*name* inbox relay";
			INBOX_RELAY_NPUB="";
			INBOX_RELAY_DESCRIPTION="send your interactions with my notes here";
#INBOX_RELAY_ICON="https://i.nostr.build/6G6wW.gif"
			INBOX_PULL_INTERVAL_SECONDS=600;

## Inbox Relay Rate Limiters
			INBOX_RELAY_EVENT_IP_LIMITER_TOKENS_PER_INTERVAL=10;
			INBOX_RELAY_EVENT_IP_LIMITER_INTERVAL=1;
			INBOX_RELAY_EVENT_IP_LIMITER_MAX_TOKENS=20;
			INBOX_RELAY_ALLOW_EMPTY_FILTERS=false;
			INBOX_RELAY_ALLOW_COMPLEX_FILTERS=false;
			INBOX_RELAY_CONNECTION_RATE_LIMITER_TOKENS_PER_INTERVAL=3;
			INBOX_RELAY_CONNECTION_RATE_LIMITER_INTERVAL=1;
			INBOX_RELAY_CONNECTION_RATE_LIMITER_MAX_TOKENS=9;

## WOT Settings
			WOT_FETCH_TIMEOUT_SECONDS=60;
			
			WHITELISTED_NPUBS_FILE="/var/lib/haven/whitelisted_npubs.json";
			
			BLACKLISTED_NPUBS_FILE="";


## LOGGING
			HAVEN_LOG_LEVEL="INFO"; # DEBUG, INFO, WARNING or ERROR
		};
		
		blastrRelays  = [
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

  systemd.tmpfiles.rules = [
    "d /var/lib/haven 0750 haven haven -"
    "f /var/lib/haven/whitelisted_npubs.json 0770 haven haven -"
  ];

	services.caddy = {
		virtualHosts = {
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
	};
}	


