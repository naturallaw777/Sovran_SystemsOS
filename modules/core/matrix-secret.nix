{ config, pkgs, lib, ... }:

{
  # ── Generate Matrix registration secret at runtime ──────────
  systemd.services.matrix-synapse-secret-init = {
    description = "Generate Matrix Synapse registration secret if missing";
    wantedBy = [ "multi-user.target" ];
    before = [ "matrix-synapse.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [ pkgs.pwgen pkgs.coreutils ];
    script = ''
      SECRET_FILE="/var/lib/matrix-synapse/registration-secret"
      if [ ! -f "$SECRET_FILE" ]; then
        mkdir -p /var/lib/matrix-synapse
        pwgen -s 64 1 > "$SECRET_FILE"
        chown matrix-synapse:matrix-synapse "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
        echo "Generated Matrix registration secret"
      else
        echo "Matrix registration secret already exists, skipping"
      fi
    '';
  };
}