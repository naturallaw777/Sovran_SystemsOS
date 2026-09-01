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
    path = [ pkgs.coreutils pkgs.findutils pkgs.iproute2 pkgs.gawk pkgs.python3 ];
    script = ''
      MATRIX=$(cat /var/lib/domains/matrix)
      ELEMENT_CALLING=$(cat /var/lib/domains/element-calling)

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

      # Derive the LAN subnet this box sits on so the embedded TURN relay
      # is allowed to hand media to LiveKit's LAN host candidate (see the
      # allow_restricted_peer_cidrs block below). Computed from the primary
      # interface's own address, so it always matches the subnet the LAN
      # clients (phones on Wi-Fi) actually live on.
      LAN_CIDR=$(ip -4 -o addr show dev "$IFACE" | awk '{print $4}' | grep -vE '^(127\.|169\.254\.)' | head -n1 | python3 -c 'import sys, ipaddress; s = sys.stdin.read().strip(); print(str(ipaddress.ip_network(s, strict=False)) if s else "")' 2>/dev/null)
      if [ -n "$LAN_CIDR" ]; then echo "Derived LAN CIDR for TURN relay: $LAN_CIDR"; else echo "Derived LAN CIDR for TURN relay: <none>"; fi

      # Generate the full LiveKit config the daemon will load. turn.domain and
      # rtc.interfaces.includes are only known at runtime, so they are
      # substituted here. The cert/key paths point at the LoadCredential-staged
      # copies under /run/credentials.
      #
      # Determine the public IPv4 to advertise in LiveKit ICE candidates.
      # Remote peers must be able to reach this address, so it must be the
      # server's public IP — or the router's WAN IP when the server is behind
      # NAT with port-forwarding. It does not need to be assigned to this box,
      # and it may be dynamic.
      #
      # Reuse the shared detector (/var/lib/sovran/public-ip.py — see
      # modules/core/public-ip.nix) instead of running our own: one script,
      # one cache, privacy-first (STUN -> DNS -> opt-in HTTPS echo). Priority:
      #   1. sovran_systemsOS.elementCalling.externalIP (explicit pin, if set)
      #   2. /var/lib/secrets/external-ip (the shared cache)
      #   3. run the detector now (it refreshes the cache)
      #   4. STUN auto-detection (use_external_ip) as the fallback, with a
      #      warning — this is where broken installs used to silently end up
      #      advertising a private IP, causing "call connects but no video".
      EXTERNAL_IP='${if config.sovran_systemsOS.elementCalling.externalIP != null then config.sovran_systemsOS.elementCalling.externalIP else ""}'

      PUBLIC_IP="$EXTERNAL_IP"
      if [ -z "$PUBLIC_IP" ] && [ -f /var/lib/secrets/external-ip ]; then
        PUBLIC_IP=$(tr -d '[:space:]' < /var/lib/secrets/external-ip 2>/dev/null)
      fi
      if [ -z "$PUBLIC_IP" ] && [ -x /var/lib/sovran/public-ip.py ]; then
        PUBLIC_IP=$(python3 /var/lib/sovran/public-ip.py check 2>/dev/null | head -n1)
      fi

      # Reject non-routable addresses (loopback, private, link-local, CGNAT).
      # A detected/pinned address like this must never be advertised.
      if [ -n "$PUBLIC_IP" ] && printf '%s' "$PUBLIC_IP" | grep -qE \
        '^(0\.|127\.|10\.|100\.64\.|169\.254\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)'; then
        echo "WARNING: external IP '$PUBLIC_IP' is not routable; falling back to STUN auto-detection." >&2
        PUBLIC_IP=""
      fi

      if [ -n "$PUBLIC_IP" ]; then
        cat > /run/livekit/livekit.yaml <<EOF
port: 7880
rtc:
  use_external_ip: false
  node_ip: $PUBLIC_IP
  advertise_internal_ip: true
  tcp_port: 7881
  udp_port: 7882
  interfaces:
    includes:
      - $IFACE
EOF
        echo "LiveKit will advertise public IP: $PUBLIC_IP"
      else
        cat > /run/livekit/livekit.yaml <<EOF
port: 7880
rtc:
  use_external_ip: true
  skip_external_ip_validation: true
  advertise_internal_ip: true
  tcp_port: 7881
  udp_port: 7882
  interfaces:
    includes:
      - $IFACE
EOF
        echo "WARNING: could not determine a public IP for LiveKit; using STUN auto-detection. If calls connect without media, check STUN egress or set sovran_systemsOS.elementCalling.externalIP." >&2
      fi

      # Webhooks → lk-jwt-service. The JWT service validates the HMAC
      # signature against the same key file it issues tokens with, and uses
      # the events (participant_left / room_finished) to detect abruptly
      # disconnected participants instead of waiting for the delayed-event
      # timeout. The URL hits local Caddy via the /etc/hosts loopback
      # override and is routed to the JWT service by the element-calling
      # vhost (/livekit/jwt/sfu_webhook → 8073).
      LK_KEY=$(cut -d: -f1 < ${livekitKeyFile} | tr -d '[:space:]')

      # TURN/TLS is intentionally not configured (no tls_port): LiveKit
      # advertises turns:<domain>:443 to clients regardless of tls_port, so
      # a 5349 TURN/TLS listener would be unreachable and only adds attack
      # surface. The staged cert/key stay for a future TURN/TLS-on-443
      # (Caddy layer4 SNI) setup.
      cat >> /run/livekit/livekit.yaml <<EOF
room:
  auto_create: false
turn:
  enabled: true
  domain: $MATRIX
  udp_port: 3478
  relay_range_start: 40000
  relay_range_end: 40099
  cert_file: /run/credentials/livekit.service/turn-cert
  key_file: /run/credentials/livekit.service/turn-key
EOF

      # By default the embedded TURN relay refuses to send media to
      # private/loopback peers. That would force its final hop to the
      # public/WAN IP (hairpin NAT) — exactly what breaks calls on routers
      # without NAT loopback. Allow the LAN subnet so the relay can deliver
      # directly to LiveKit's LAN host candidate instead.
      if [ -n "$LAN_CIDR" ]; then
        cat >> /run/livekit/livekit.yaml <<EOF
  allow_restricted_peer_cidrs:
    - $LAN_CIDR
EOF
      fi

      cat >> /run/livekit/livekit.yaml <<EOF
webhook:
  api_key: $LK_KEY
  urls:
    - https://$ELEMENT_CALLING/livekit/jwt/sfu_webhook
EOF

      chmod 644 /run/livekit/livekit.yaml
    '';
  };

  ####### LIVEKIT SERVICE #######
  # NOTE: the runtime config (rtc ports, TURN, webhook, node_ip) is generated
  # by livekit-turn-setup and delivered via LoadCredential; the upstream
  # module's `settings` block is therefore intentionally NOT used (it would
  # be dead config that silently diverges from what LiveKit actually loads).
  # The firewall ports are opened explicitly below; openFirewall is left off
  # so the upstream module does not also open 7880/tcp publicly (Caddy fronts
  # the SFU on this host).
  services.livekit = {
    enable = true;
    openFirewall = false;
    keyFile = livekitKeyFile;
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

  # 5349/TCP (TURN/TLS) is deliberately absent — see livekit-turn-setup. RTC
  # media uses the single UDP mux (7882); the 30000-40000 range is gone so
  # media is no longer spread across 10000 ports. The TURN relay allocation
  # range (40000-40099) is kept separate from the media mux.
  networking.firewall.allowedTCPPorts = [ 7881 ];
  networking.firewall.allowedUDPPorts = [ 3478 7882 ];
  networking.firewall.allowedUDPPortRanges = [
    { from = 40000; to = 40099; } # LiveKit embedded TURN relay allocation range
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
      FULL_ACCESS_HOMESERVERS="$MATRIX"

      # Federated peers may also be granted LiveKit room-creation (full access)
      # on this SFU via sovran_systemsOS.elementCalling.fullAccessHomeservers.
      # Without this, remote users can join existing calls but cannot be the
      # first to start one on your SFU.
      EXTRA_HS='${lib.concatStringsSep "," config.sovran_systemsOS.elementCalling.fullAccessHomeservers}'
      if [ -n "$EXTRA_HS" ]; then
        FULL_ACCESS_HOMESERVERS="$FULL_ACCESS_HOMESERVERS,$EXTRA_HS"
      fi

      mkdir -p /run/lk-jwt-service

      cat > /run/lk-jwt-service/env <<EOF
LIVEKIT_URL=wss://$ELEMENT_CALLING
LIVEKIT_FULL_ACCESS_HOMESERVERS=$FULL_ACCESS_HOMESERVERS
# Re-check, every 60s, that connected participants are still on the SFU;
# guards against missed SFU webhooks (e.g. an SFU restart) leaving stale
# call members in Matrix rooms.
LIVEKIT_SANITY_CHECK_INTERVAL_SECONDS=60
EOF

      chmod 640 /run/lk-jwt-service/env
    '';
  };

  ####### JWT SERVICE #######
  services.lk-jwt-service = {
    enable = true;
    port = 8073;
    keyFile = livekitKeyFile;
    # Required by the upstream module's option type, but overridden at runtime
    # by EnvironmentFile (/run/lk-jwt-service/env, generated above from the
    # element-calling domain). Kept as a harmless placeholder.
    livekitUrl = "wss://placeholder.local";
  };

  systemd.services.lk-jwt-service.serviceConfig.EnvironmentFile = [
    "/run/lk-jwt-service/env"
  ];

  # Restart LiveKit / lk-jwt-service when a rebuild regenerates their runtime
  # configs (new domains, externalIP, full-access list), mirroring the domain
  # change flow.
  # Re-run the config generator and restart LiveKit when a rebuild regenerates
  # the runtime config, or when the Hub persists a new external IP (dynamic
  # WAN IPs), so the advertised ICE candidate stays current without a manual
  # restart. The trigger chain: external-ip change → livekit-turn-setup
  # re-runs → rewrites livekit.yaml → livekit restarts with the new config.
  systemd.services.livekit-turn-setup.restartTriggers = [ "/var/lib/secrets/external-ip" ];
  systemd.services.livekit.restartTriggers = [ "/run/livekit/livekit.yaml" ];
  systemd.services.lk-jwt-service.restartTriggers = [ "/run/lk-jwt-service/env" ];

  ####### PUBLIC REACHABILITY SELF-CHECK #######
  # Diagnostic only — never a hard dependency of livekit/caddy. Catches the
  # classic "call connects but no media" setup errors at boot instead of at
  # call time:
  #   * the element-calling domain having no public records (or resolving to
  #     loopback/link-local/CGNAT for remote peers),
  #   * the lk-jwt-service being unreachable through Caddy,
  #   * the MatrixRTC transports endpoint being absent (Element X cannot
  #     discover calling and shows MISSING_MATRIX_RTC_TRANSPORT).
  # The check queries only the operator's own DNS provider (the domain's
  # authoritative nameservers, resolved via the local resolver) plus the
  # server's own Caddy and public IP — no third-party resolver or service is
  # contacted. dig queries resolvers directly, so the /etc/hosts loopback
  # overrides (modules/core/local-domain-loopback.nix) do not influence the
  # result.
  systemd.services.element-calling-public-check = {
    description = "Verify Element Calling domain, JWT service and MatrixRTC transports endpoint are publicly reachable";
    after = [ "network-online.target" "caddy.service" "livekit.service" "lk-jwt-service.service" ];
    wants = [ "network-online.target" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    unitConfig = {
      ConditionPathExists = "/var/lib/domains/element-calling";
    };
    path = [ pkgs.coreutils pkgs.gawk pkgs.dnsutils pkgs.curl ];
    script = ''
      ELEMENT_CALLING=$(cat /var/lib/domains/element-calling)
      MATRIX=$(cat /var/lib/domains/matrix)
      FAIL=0

      echo "── Element Calling public reachability self-check ──"

      # 1) Authoritative DNS view (bypassing the /etc/hosts loopback
      #    overrides). Resolve the domain's own nameservers via the local
      #    resolver, then query those nameservers directly — the only party
      #    that sees the query is the DNS provider the operator already uses
      #    for the domain.
      NS_LIST=$(dig +short NS "$ELEMENT_CALLING" 2>/dev/null | tr '\n' ' ')
      if [ -n "$NS_LIST" ]; then
        IPS=""
        for NSRV in $NS_LIST; do
          IPS=$( { dig +short A "$ELEMENT_CALLING" "@$NSRV" 2>/dev/null; dig +short AAAA "$ELEMENT_CALLING" "@$NSRV" 2>/dev/null; } | tr '\n' ' ' )
          [ -n "$IPS" ] && break
        done
        echo "Authoritative nameservers for $ELEMENT_CALLING: $NS_LIST"
      else
        echo "WARNING: could not resolve nameservers for $ELEMENT_CALLING via the local resolver; using the local resolver's answer instead." >&2
        IPS=$( { dig +short A "$ELEMENT_CALLING" 2>/dev/null; dig +short AAAA "$ELEMENT_CALLING" 2>/dev/null; } | tr '\n' ' ' )
      fi

      if [ -z "$IPS" ]; then
        echo "ERROR: no A/AAAA records for $ELEMENT_CALLING at its authoritative nameservers. Remote peers cannot reach this LiveKit; calls will connect without media." >&2
        FAIL=1
      else
        echo "Public DNS for $ELEMENT_CALLING: $IPS"
        for IP in $IPS; do
          case "$IP" in
            0.*|127.*|169.254.*|100.64.*|::1|fe80:*|fc*:*|fd*:*)
              echo "ERROR: $ELEMENT_CALLING resolves to $IP (loopback/link-local/CGNAT). Remote peers cannot reach it." >&2
              FAIL=1 ;;
          esac
        done
      fi

      # 2) lk-jwt-service healthz through Caddy (validates the proxy chain).
      if curl -fsS --max-time 10 "https://$ELEMENT_CALLING/livekit/jwt/healthz" >/dev/null 2>&1; then
        echo "OK: https://$ELEMENT_CALLING/livekit/jwt/healthz responds"
      else
        echo "ERROR: https://$ELEMENT_CALLING/livekit/jwt/healthz not reachable through Caddy." >&2
        FAIL=1
      fi

      # 3) Same healthz via the first public IP (tests the full NAT path).
      #    NOTE: if this box is behind the same NAT you are testing through,
      #    routers without hairpin NAT will fail this step — the warning is
      #    then expected and harmless; verify from an external device instead.
      if [ -n "$IPS" ]; then
        PUBIP=$(echo "$IPS" | awk '{print $1}')
        if curl -fsS --max-time 15 --resolve "$ELEMENT_CALLING:443:$PUBIP" "https://$ELEMENT_CALLING/livekit/jwt/healthz" >/dev/null 2>&1; then
          echo "OK: healthz reachable via public IP $PUBIP (NAT path works)"
        else
          echo "WARNING: healthz NOT reachable via public IP $PUBIP — check router port-forwarding (443/TCP) and NAT hairpin. Expected if the router lacks hairpin NAT; verify from an external device." >&2
        fi
      fi

      # 4) MatrixRTC transports registry (MSC4519) — required by Element X.
      CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$MATRIX/_matrix/client/unstable/org.matrix.msc4143/rtc/transports")
      case "$CODE" in
        401|200)
          echo "OK: MatrixRTC transports endpoint present (HTTP $CODE; auth required is expected)" ;;
        404)
          echo "ERROR: /_matrix/client/unstable/org.matrix.msc4143/rtc/transports missing (HTTP 404) — Element X cannot discover calling. Enable msc4143_enabled and matrix_rtc.transports in Synapse." >&2
          FAIL=1 ;;
        *)
          echo "WARNING: transports endpoint returned HTTP $CODE" >&2 ;;
      esac

      if [ "$FAIL" -eq 1 ]; then
        echo "── Element Calling self-check FAILED — see errors above ──" >&2
        exit 1
      fi
      echo "── Element Calling self-check passed ──"
    '';
  };

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
      ELEMENT_CALLING=$(cat /var/lib/domains/element-calling)

      mkdir -p /run/matrix-synapse

      cat > /run/matrix-synapse/element-calling-config.yaml <<EOF
server_name: "$MATRIX"
public_baseurl: "https://$MATRIX"
serve_server_wellknown: true
experimental_features:
  msc3266_enabled: true
  # MSC4143: enables the MatrixRTC transports registry endpoint
  # (/_matrix/client/unstable/org.matrix.msc4143/rtc/transports, MSC4519).
  # Element X requires this endpoint to discover the LiveKit focus; without it
  # mobile clients fail with MISSING_MATRIX_RTC_TRANSPORT / cannot start calls.
  msc4143_enabled: true
  msc4222_enabled: true
# MSC4519: advertise this site's LiveKit focus via the transports registry.
matrix_rtc:
  transports:
    - type: livekit
      livekit_service_url: "https://$ELEMENT_CALLING/livekit/jwt"
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
