{ config, pkgs, lib, ... }:

{
  # ── Ensure njalla directory and base script exist on every build ──
  systemd.tmpfiles.rules = [
    "d /var/lib/njalla 0750 root root -"
  ];

  # ── Create base njalla.sh if it doesn't exist yet ────────────
  systemd.services.njalla-init = {
    description = "Initialize Njal.la DDNS script if missing";
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    unitConfig = {
      ConditionPathExists = "!/var/lib/njalla/njalla.sh";
    };
    script = ''
      cat > /var/lib/njalla/njalla.sh <<'SCRIPT'
#!/usr/bin/env bash
IP=$(dig @resolver4.opendns.com myip.opendns.com +short -4)

## Add DDNS entries below — one curl per line
## Run 'sudo sovran-setup-domains' to configure automatically
SCRIPT

      chmod 700 /var/lib/njalla/njalla.sh
    '';
  };
}