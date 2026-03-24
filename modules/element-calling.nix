{ config, pkgs, lib, ... }:

let
  personalization = import ./personalization.nix;
in

lib.mkIf config.sovran_systemsOS.features.element-calling {

  ####### SYSTEMD TMPFILES: create directories automatically #######
  systemd.tmpfiles.rules = [
    # Ensure parent directories exist
    "d /var/lib/domains/element-calling 0750 - - -"
  ];

  ####### CADDY CONFIGS #######
  "${personalization.matrix_url}" = lib.mkForce {
    extraConfig = ''
      reverse_proxy /_matrix/* http://localhost:8008
      reverse_proxy /_synapse/client/* http://localhost:8008
      header /.well-known/matrix/* Content-Type "application/json"
      header /.well-known/matrix/* Access-Control-Allow-Origin "*"
      header /.well-known/matrix/* Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS"
      header /.well-known/matrix/* Access-Control-Allow-Headers "X-Requested-With, Content-Type, Authorization"
      respond /.well-known/matrix/client `{ "m.homeserver": {"base_url": "https://${personalization.matrix_url}" }, "org.matrix.msc4143.rtc_foci": [{ "type":"livekit", "livekit_service_url":"https://${personalization.element-calling_url}/livekit/jwt" }] }`
    '';
  };

  "${personalization.element-calling_url}" = lib.mkForce {
    extraConfig = ''
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
    '';
  };

  ####### LIVEKIT SERVICE #######
  services.livekit = {
    enable = true;
    openFirewall = true;
    settings = {
      rtc.use_external_ip = true;
      rtc.udp_port = "7882-7894";
      room.auto_create = false;
      turn = {
        enabled = true;
        domain = "${personalization.matrix_url}";
        tls_port = 5349;
        udp_port = 3478;
        cert_file = "/var/lib/livekit/${personalization.matrix_url}.crt";
        key_file = "/var/lib/livekit/${personalization.matrix_url}.key";
      };
    };
    keyFile = "/var/lib/livekit/livekit_keyFile";
  };

  networking.firewall.allowedTCPPorts = [ 7881 ];
  networking.firewall.allowedUDPPortRanges = [
    { from = 7882; to = 7894; }
  ];

  ####### JWT SERVICE #######
  services.lk-jwt-service = {
    enable = true;
    port = 8073;
    livekitUrl = "wss://${personalization.element-calling_url}";
    keyFile = "/var/lib/livekit/livekit_keyFile";
  };

  ####### MATRIX-SYNAPSE SETTINGS #######
  services.matrix-synapse = {
    settings = lib.mkForce {
      serve_server_wellknown = true;
      public_baseurl = "${personalization.matrix_url}";

      experimental_features = {
        msc3266_enabled = true;
        msc4222_enabled = true;
      };

      max_event_delay_duration = "24h";

      rc_message = { per_second = 0.5; burst_count = 30; };
      rc_delayed_event_mgmt = { per_second = 1; burst_count = 20; };

      push.include_content = false;
      server_name = personalization.matrix_url;
      url_preview_enabled = true;
      group_unread_count_by_room = false;
      encryption_enabled_by_default_for_room_type = "invite";
      allow_profile_lookup_over_federation = false;
      allow_device_name_lookup_over_federation = false;

      url_preview_ip_range_blacklist = [
        "10.0.0.0/8" "100.64.0.0/10" "169.254.0.0/16" "172.16.0.0/12"
        "192.0.0.0/24" "192.0.2.0/24" "192.168.0.0/16" "192.88.99.0/24"
        "198.18.0.0/15" "198.51.100.0/24" "2001:db8::/32" "203.0.113.0/24"
        "224.0.0.0/4" "::1/128" "fc00::/7" "fe80::/10" "fec0::/10" "ff00::/8"
      ];

      url_preview_ip_ranger_whitelist = [ "127.0.0.1" ];
      presence.enabled = true;
      enable_registration = false;
      registration_shared_secret = config.age.secrets.matrix_reg_secret.path;

      listeners = [
        {
          port = 8008;
          bind_addresses = [ "::1" ];
          type = "http";
          tls = false;
          x_forwarded = true;
          resources = [
            { names = [ "client" ]; compress = true; }
            { names = [ "federation" ]; compress = false; }
          ];
        }
      ];
    };
  };
}
