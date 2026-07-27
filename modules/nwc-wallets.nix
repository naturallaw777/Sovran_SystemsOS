{ config, pkgs, lib, ... }:

lib.mkIf config.sovran_systemsOS.features."nwc-wallets" {
  assertions = [
    {
      assertion = config.services.lnd.enable;
      message = "Wallet Connections requires services.lnd.enable = true.";
    }
  ];

  users.groups.nwc-wallets = {};
  users.users.nwc-wallets = {
    isSystemUser = true;
    group = "nwc-wallets";
    home = "/var/lib/nwc-wallets";
    createHome = true;
  };

  systemd.tmpfiles.rules = [
    "d /var/lib/nwc-wallets 0750 nwc-wallets nwc-wallets -"
    "f /var/lib/nwc-wallets/state.json 0640 nwc-wallets nwc-wallets -"
  ];

  systemd.services.nwc-wallets = {
    description = "Wallet Connections state initializer";
    wantedBy = [ "multi-user.target" ];
    after = [ "lnd.service" "sovran-hub-web.service" ];
    requires = [ "lnd.service" "sovran-hub-web.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      User = "nwc-wallets";
      Group = "nwc-wallets";
      UMask = "0027";
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectHome = true;
      ProtectSystem = "strict";
      ReadWritePaths = [ "/var/lib/nwc-wallets" ];
      ExecStart = pkgs.writeShellScript "nwc-wallets-init" ''
        set -euo pipefail
        install -d -m 0750 -o nwc-wallets -g nwc-wallets /var/lib/nwc-wallets
        if [ ! -s /var/lib/nwc-wallets/state.json ]; then
          cat > /var/lib/nwc-wallets/state.json <<'EOF'
{"wallets":[]}
EOF
          chown nwc-wallets:nwc-wallets /var/lib/nwc-wallets/state.json
          chmod 0640 /var/lib/nwc-wallets/state.json
        fi
      '';
    };
  };

  sovran_systemsOS.domainRequirements = [
    {
      name = "lightning";
      label = "Lightning Address Domain";
      example = "pay.yourdomain.com";
      needsDDNS = true;
    }
  ];
}
