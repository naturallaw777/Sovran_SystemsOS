{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features.vaultwarden {

  # ── Caddy vhost is now handled centrally in caddy.nix ─────

  # ── Generate Vaultwarden runtime config from domain files ──
  systemd.services.vaultwarden-runtime-config = {
    description = "Generate Vaultwarden runtime config from domain files";
    before = [ "vaultwarden.service" ];
    requiredBy = [ "vaultwarden.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.coreutils ];
    script = ''
      VAULTWARDEN=$(cat /var/lib/domains/vaultwarden)

      mkdir -p /run/vaultwarden

      cat > /run/vaultwarden/runtime.env <<EOF
      DOMAIN=https://$VAULTWARDEN
      EOF

      chmod 640 /run/vaultwarden/runtime.env
    '';
  };

  services.vaultwarden = {
    enable = true;
    config = {
      # DOMAIN injected at runtime via EnvironmentFile
      SIGNUPS_ALLOWED = false;
      ROCKET_ADDRESS = "127.0.0.1";
      ROCKET_PORT = 8777;
      ROCKET_LOG = "critical";
    };
    dbBackend = "sqlite";
    environmentFile = "/var/lib/secrets/vaultwarden/vaultwarden.env";
  };

  systemd.services.vaultwarden.serviceConfig.EnvironmentFile = lib.mkAfter [
    "/run/vaultwarden/runtime.env"
  ];
}
