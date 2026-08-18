{ config, pkgs, lib, ... }:

let
  livekitKeyFile = "/var/lib/livekit/livekit_keyFile";
in

lib.mkIf config.sovran_systemsOS.features.element-calling {

  ####### LIVEKIT KEY GENERATION #######
  systemd.tmpfiles.rules = [
    "d /var/lib/livekit 0750 root root -"
  ];

  systemd.services.livekit-key-setup = {
    description = "Generate LiveKit key file if missing";
    wantedBy = [ "multi-user.target" ];
    before = [ "livekit.service" "lk-jwt-service.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.openssl ];
    script = ''
      if [ ! -f ${livekitKeyFile} ]; then
        API_KEY="devkey_$(openssl rand -hex 16)"
        API_SECRET="$(openssl rand -base64 36 | tr -d '\n')"
        echo "$API_KEY: $API_SECRET" > ${livekitKeyFile}
        chmod 600 ${livekitKeyFile}
        echo "LiveKit key file generated at ${livekitKeyFile}"
      else
        echo "LiveKit key file already exists, skipping generation"
      fi
    '';
  };

  ####### ENSURE SERVICES START AFTER KEY & NETWORK EXIST #######
  # Ordering against network-online.target matters: livekit-turn-setup detects
  # the primary interface from the IPv4 default route. If it runs before the
  # network is up (no default route yet) it exits 1 and, being a hard
  # dependency of livekit.service, takes livekit down with it — the Hub then
  # shows a "failed" red dot until livekit is restarted manually. See the
  # livekit-turn-setup block for the matching network-online ordering.
  systemd.services.livekit.after = [ "network-online.target" "livekit-key-setup.service" "livekit-turn-setup.service" ];
  systemd.services.livekit.wants = [ "network-online.target" "livekit-key-setup.service" "livekit-turn-setup.service" ];
  systemd.services.lk-jwt-service.after = [ "livekit-key-setup.service" ];
  systemd.services.lk-jwt-service.wants = [ "livekit-key-setup.service" ];

  ####### CADDY SNIPPET #######
  systemd.services.element-calling-caddy-config = {
    description = "Generate Element Calling Caddy config snippet";
    before = [ "caddy-generate-config.service" ];
    requiredBy = [ "caddy-generate-config.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    unitConfig = {
      ConditionPathExists = "/var/lib/domains/element-calling";
    };
    path = [ pkgs.coreutils ];
    script = ''
      MATRIX=$(cat /var/lib/domains/matrix)
      ELEMENT_CALLING=$(cat /var/lib/domains/element-calling)

      mkdir -p /run/caddy

      cat > /run/caddy/element-calling.snippet <<EOF
$MATRIX {
  reverse_proxy /_matrix/* http://localhost:8008
  reverse_proxy /_synapse/client/* http://localhost:8008
  header /.well-known/matrix/* Content-Type "application/json"
  header /.well-known/matrix/* Access-Control-Allow-Origin "*"
  header /.well-known/matrix/* Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS"
  header /.well-known/matrix/* Access-Control-Allow-Headers "X-Requested-With, Content-Type, Authorization"
  respond /.well-known/matrix/client \`{ "m.homeserver": {"base_url": "https://$MATRIX" }, "org.matrix.msc4143.rtc_foci": [{ "type":"livekit", "livekit_service_url":"https://$ELEMENT_CALLING/livekit/jwt" }] }\`
  respond /.well-known/matrix/server \`{"m.server":"$MATRIX:443"}\`
}

$ELEMENT_CALLING {
  # Route all current lk-jwt-service authorization endpoints to port 8073,
  # stripping the /livekit/jwt prefix that Caddy adds on the public URL.
  @lk_jwt path /livekit/jwt/sfu/get* /livekit/jwt/get_token* /livekit/jwt/healthz* /livekit/jwt/sfu_webhook* /livekit/jwt/delegate_delayed_leave*
  handle @lk_jwt {
    uri strip_prefix /livekit/jwt
    reverse_proxy [::1]:8073 {
      header_up Host {host}
      header_up X-Forwarded-Server {host}
      header_up X-Real-IP {remote_host}
      header_up X-Forwarded-For {remote_host}
      header_up X-Forwarded-Proto {scheme}
    }
  }
  handle {
    reverse_proxy localhost:7880 {
      header_up Host {host}
      header_up X-Forwarded-Proto {scheme}
      header_up X-Forwarded-For {remote_host}
      header_up X-Real-IP {remote_host}
      transport http {
        read_timeout 300s
        write_timeout 300s
      }
    }
  }
}
EOF
    '';
  };

  ####### LIVEKIT TURN SETUP (runtime cert + config) #######
  # Replaces the old dead livekit-runtime-config.service. At runtime this:
  #   * reads the matrix domain from /var/lib/domains/matrix (never hardcoded)
  #   * copies Caddy's already-issued matrix cert/key into /var/lib/livekit
  #     so LoadCredential can stage them for the (DynamicUser) livekit unit
  #   * detects the primary network interface from the IPv4 default route so
  #     LiveKit only advertises real ICE candidates — not VPN/container/private
  #     addresses from interfaces like Tailscale or Docker bridges
  #   * writes a complete LiveKit config (with turn.domain and interface
  #     substituted) that the overridden ExecStart loads.
  systemd.services.livekit-turn-setup = {
    description = "Stage TURN cert and generate LiveKit runtime config from domain files";
    # Wait for a default IPv4 route before detecting the interface, and for
    # Caddy to have started (cert generation is async, so also see the retry
    # loop below). Otherwise on a cold boot this unit can fail / produce empty
    # certs, which breaks livekit.service (requiredBy) and shows a red dot.
    after = [ "network-online.target" "caddy.service" "livekit-key-setup.service" ];
    wants = [ "network-online.target" ];
    before = [ "livekit.service" ];
    requiredBy = [ "livekit.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    unitConfig = {
      ConditionPathExists = "/var/lib/domains/element-calling";
    };
    path = [ pkgs.coreutils pkgs.findutils pkgs.iproute2 pkgs.gawk ];
    script = ''
      MATRIX=$(cat /var/lib/domains/matrix)

      mkdir -p /run/livekit

      # Copy Caddy's already-issued matrix cert/key into LiveKit's state dir.
      # The ACME CA hostname directory can vary, so glob for the domain dir.
      # Caddy issues ACME certs asynchronously, so on a fresh boot the cert may
      # not exist yet. Retry (bounded) so we never write an empty turn.crt/key;
      # otherwise embedded TURN silently breaks until the next livekit restart.
      CRT=""
      KEY=""
      for _ in $(seq 1 30); do
        CRT=$(find /var/lib/caddy -path "*/$MATRIX/$MATRIX.crt" | head -n1)
        KEY=$(find /var/lib/caddy -path "*/$MATRIX/$MATRIX.key" | head -n1)
        if [ -n "$CRT" ] && [ -n "$KEY" ] \
           && [ -s "$CRT" ] && [ -s "$KEY" ]; then
          break
        fi
        CRT=""
        KEY=""
        echo "Waiting for Caddy to issue the $MATRIX ACME certificate..."
        sleep 2
      done
      if [ -z "$CRT" ] || [ -z "$KEY" ]; then
        echo "ERROR: Caddy ACME certificate for $MATRIX not available after retries; TURN will not be enabled for LiveKit." >&2
      else
        cp "$CRT" /var/lib/livekit/turn.crt
        cp "$KEY" /var/lib/livekit/turn.key
        chmod 640 /var/lib/livekit/turn.crt /var/lib/livekit/turn.key
      fi

      # Detect the primary network interface from the IPv4 default route.
      # Restricting LiveKit to this single interface prevents it from
      # advertising VPN/container/private ICE candidates (e.g. Tailscale,
      # Docker bridges) that remote peers cannot reach, which causes all
      # ICE negotiation attempts to fail with responsesReceived: 0.
      IFACE=$(ip -4 route show default | awk '/^default/ { for(i=1;i<=NF;i++) if($i=="dev" && (i+1)<=NF) { print $(i+1); exit } }')
      if [ -z "$IFACE" ]; then
        echo "ERROR: Could not detect a default-route network interface from 'ip -4 route show default'." >&2
        echo "ERROR: Cannot generate a valid LiveKit config without a real interface to bind ICE candidates to." >&2
        echo "ERROR: Ensure a default IPv4 route is configured, e.g.: ip route add default via <gateway> dev <interface>" >&2
        echo "ERROR: Inspect the current routing table with: ip -4 route show" >&2
        exit 1
      fi
      echo "Detected primary network interface: $IFACE"

      # Generate the full LiveKit config the daemon will load. turn.domain and
      # rtc.interfaces.includes are only known at runtime, so they are
      # substituted here. The cert/key paths point at the LoadCredential-staged
      # copies under /run/credentials.
      cat > /run/livekit/livekit.yaml <<EOF
port: 7880
rtc:
  use_external_ip: true
  skip_external_ip_validation: true
  tcp_port: 7881
  udp_port: 7882
  port_range_start: 30000
  port_range_end: 40000
  interfaces:
    includes:
      - $IFACE
room:
  auto_create: false
turn:
  enabled: true
  domain: $MATRIX
  tls_port: 5349
  udp_port: 3478
  cert_file: /run/credentials/livekit.service/turn-cert
  key_file: /run/credentials/livekit.service/turn-key
EOF

      chmod 644 /run/livekit/livekit.yaml
    '';
  };

  ####### LIVEKIT SERVICE #######
  services.livekit = {
    enable = true;
    openFirewall = true;
    keyFile = livekitKeyFile;
    settings = {
      rtc.use_external_ip = true;
      rtc.skip_external_ip_validation = true;
      rtc.tcp_port = 7881;
      rtc.udp_port = 7882;
      rtc.port_range_start = 30000;
      rtc.port_range_end = 40000;
      room.auto_create = false;
      turn = {
        enabled = true;
        tls_port = 5349;
        udp_port = 3478;
      };
    };
  };

  # Override ExecStart to load the runtime-generated config (which carries the
  # runtime-only turn.domain), mirroring the Caddy ExecStart override pattern in
  # modules/core/caddy.nix. Deliver the TURN cert/key via LoadCredential so they
  # are readable under the upstream unit's DynamicUser=true sandbox without
  # weakening it. Everything else about the standard unit is left intact.
  systemd.services.livekit.serviceConfig.ExecStart = lib.mkForce [
    ""
    "${pkgs.livekit}/bin/livekit-server --config /run/credentials/livekit.service/livekit-config --key-file /run/credentials/livekit.service/livekit-secrets"
  ];

  systemd.services.livekit.serviceConfig.LoadCredential = [
    "livekit-config:/run/livekit/livekit.yaml"
    "livekit-secrets:${livekitKeyFile}"
    "turn-cert:/var/lib/livekit/turn.crt"
    "turn-key:/var/lib/livekit/turn.key"
  ];

  networking.firewall.allowedTCPPorts = [ 5349 7881 ];
  networking.firewall.allowedUDPPorts = [ 3478 7882 ];
  networking.firewall.allowedUDPPortRanges = [
    { from = 30000; to = 40000; } # LiveKit internal TURN relay range
  ];

  ####### JWT SERVICE RUNTIME CONFIG #######
  systemd.services.lk-jwt-service-runtime-config = {
    description = "Generate lk-jwt-service runtime config from domain files";
    before = [ "lk-jwt-service.service" ];
    after = [ "livekit-key-setup.service" ];
    requiredBy = [ "lk-jwt-service.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    unitConfig = {
      ConditionPathExists = "/var/lib/domains/element-calling";
    };
    path = [ pkgs.coreutils ];
    script = ''
      ELEMENT_CALLING=$(cat /var/lib/domains/element-calling)
      MATRIX=$(cat /var/lib/domains/matrix)

      mkdir -p /run/lk-jwt-service

      cat > /run/lk-jwt-service/env <<EOF
LIVEKIT_URL=wss://$ELEMENT_CALLING
LIVEKIT_FULL_ACCESS_HOMESERVERS=$MATRIX
EOF

      chmod 640 /run/lk-jwt-service/env
    '';
  };

  ####### JWT SERVICE #######
  services.lk-jwt-service = {
    enable = true;
    port = 8073;
    keyFile = livekitKeyFile;
    livekitUrl = "wss://placeholder.local";
  };

  systemd.services.lk-jwt-service.serviceConfig.EnvironmentFile = [
    "/run/lk-jwt-service/env"
  ];

  ####### SYNAPSE RUNTIME CONFIG (element-calling additions) #######
  systemd.services.element-calling-synapse-config = {
    description = "Generate Synapse runtime config for Element Calling";
    before = [ "matrix-synapse.service" ];
    requiredBy = [ "matrix-synapse.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    unitConfig = {
      ConditionPathExists = "/var/lib/domains/element-calling";
    };
    path = [ pkgs.coreutils ];
    script = ''
      MATRIX=$(cat /var/lib/domains/matrix)

      mkdir -p /run/matrix-synapse

      cat > /run/matrix-synapse/element-calling-config.yaml <<EOF
server_name: "$MATRIX"
public_baseurl: "https://$MATRIX"
serve_server_wellknown: true
experimental_features:
  msc3266_enabled: true
  msc4222_enabled: true
max_event_delay_duration: "24h"
rc_message:
  per_second: 0.5
  burst_count: 30
rc_delayed_event_mgmt:
  per_second: 1
  burst_count: 20
EOF

      chown matrix-synapse:matrix-synapse /run/matrix-synapse/element-calling-config.yaml
      chmod 640 /run/matrix-synapse/element-calling-config.yaml
    '';
  };

  ####### SYNAPSE OVERRIDES (element-calling needs) #######
  services.matrix-synapse.extraConfigFiles = [
    "/run/matrix-synapse/element-calling-config.yaml"
  ];

  sovran_systemsOS.domainRequirements = [
    { name = "element-calling"; label = "Element Calling (LiveKit)"; example = "call.yourdomain.com"; }
  ];
}
