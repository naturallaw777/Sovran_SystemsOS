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

  ####### ENSURE SERVICES START AFTER KEY EXISTS #######
  systemd.services.livekit.after = [ "livekit-key-setup.service" ];
  systemd.services.livekit.wants = [ "livekit-key-setup.service" ];
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
}

$MATRIX:8448 {
  reverse_proxy http://localhost:8008
}

$ELEMENT_CALLING {
  handle /livekit/jwt/sfu/get {
    uri strip_prefix /livekit/jwt
    reverse_proxy [::1]:8073 {
      header_up Host {host}
      header_up X-Forwarded-Server {host}
      header_up X-Real-IP {remote_host}
      header_up X-Forwarded-For {remote_host}
    }
  }
  handle {
    reverse_proxy localhost:7880
  }
}
EOF
    '';
  };

  ####### LIVEKIT RUNTIME CONFIG #######
  systemd.services.livekit-runtime-config = {
    description = "Generate LiveKit runtime config from domain files";
    before = [ "livekit.service" ];
    after = [ "livekit-key-setup.service" ];
    requiredBy = [ "livekit.service" ];
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

      mkdir -p /run/livekit

      cat > /run/livekit/runtime-config.yaml <<EOF
turn:
  domain: $MATRIX
  cert_file: /var/lib/livekit/$MATRIX.crt
  key_file: /var/lib/livekit/$MATRIX.key
EOF

      chmod 640 /run/livekit/runtime-config.yaml
    '';
  };

  ####### LIVEKIT SERVICE #######
  services.livekit = {
    enable = true;
    openFirewall = true;
    keyFile = livekitKeyFile;
    settings = {
      rtc.use_external_ip = true;
      rtc.udp_port = "7882-7894";
      room.auto_create = false;
      turn = {
        enabled = true;
        tls_port = 5349;
        udp_port = 3478;
      };
    };
  };

  networking.firewall.allowedTCPPorts = [ 5349 7881 ];
  networking.firewall.allowedUDPPorts = [ 3478 ];
  networking.firewall.allowedUDPPortRanges = [
    { from = 7882; to = 7894; }
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

      mkdir -p /run/lk-jwt-service

      cat > /run/lk-jwt-service/env <<EOF
LIVEKIT_URL=wss://$ELEMENT_CALLING
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
