{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.services.vaultwarden {

  # ── Generate ADMIN_TOKEN if missing ─────────────────────────
  systemd.services.vaultwarden-secret-init = {
    description = "Generate Vaultwarden ADMIN_TOKEN if missing";
    wantedBy = [ "multi-user.target" ];
    before = [ "vaultwarden.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.openssl pkgs.coreutils ];
    script = ''
      SECRET_DIR="/var/lib/secrets/vaultwarden"
      SECRET_FILE="$SECRET_DIR/vaultwarden.env"

      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p "$SECRET_DIR"
        echo -n "ADMIN_TOKEN=$(openssl rand -base64 48)" > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
        echo "Generated Vaultwarden ADMIN_TOKEN"
      else
        echo "Vaultwarden ADMIN_TOKEN already exists, skipping"
      fi
    '';
  };

  # ── Generate runtime config from domain files ───────────────
  systemd.services.vaultwarden-runtime-config = {
    description = "Generate Vaultwarden runtime config from domain files";
    before = [ "vaultwarden.service" ];
    requiredBy = [ "vaultwarden.service" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    unitConfig = {
      ConditionPathExists = "/var/lib/domains/vaultwarden";
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

  sovran_systemsOS.domainRequirements = [
    { name = "vaultwarden"; label = "Vaultwarden"; example = "vault.yourdomain.com"; }
  ];
}
