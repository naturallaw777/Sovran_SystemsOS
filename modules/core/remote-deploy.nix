{ config, lib, pkgs, ... }:

let
  cfg = config.sovran_systemsOS.deploy;
in

{
  options.sovran_systemsOS.deploy = {
    enable = lib.mkEnableOption "Remote deploy mode";

    relayHost = lib.mkOption {
      type = lib.types.str;
      default = "";
      description = "SSH relay server hostname or IP for the reverse tunnel";
    };

    relayPort = lib.mkOption {
      type = lib.types.port;
      default = 22;
      description = "SSH port on the relay server";
    };

    relayUser = lib.mkOption {
      type = lib.types.str;
      default = "deploy";
      description = "Username on the relay server";
    };

    reverseTunnelPort = lib.mkOption {
      type = lib.types.port;
      default = 2222;
      description = "Port on the relay that maps back to this machine's SSH (port 22)";
    };

    authorizedKey = lib.mkOption {
      type = lib.types.str;
      default = "";
      description = "Deployer's SSH public key for root access";
    };
  };

  config = lib.mkIf cfg.enable {

    # ── Force SSH open on all interfaces ────────────────────────────────────
    services.openssh = {
      enable = true;
      listenAddresses = lib.mkForce [
        { addr = "0.0.0.0"; port = 22; }
        { addr = "127.0.0.1"; port = 22; }
      ];
      settings = {
        PermitRootLogin = lib.mkForce "prohibit-password";
        PasswordAuthentication = lib.mkForce false;
      };
    };

    networking.firewall.allowedTCPPorts = [ 22 ];

    # ── Inject deployer's SSH public key into root's authorized keys ─────────
    users.users.root.openssh.authorizedKeys.keys =
      lib.mkIf (cfg.authorizedKey != "") [ cfg.authorizedKey ];

    # ── Force RDP on ─────────────────────────────────────────────────────────
    sovran_systemsOS.features.rdp = lib.mkForce true;

    # ── Enable Fail2Ban for SSH protection ───────────────────────────────────
    services.fail2ban = {
      enable = true;
      ignoreIP = [ "127.0.0.0/8" ];
    };

    # ── Reverse tunnel service (only when relayHost is configured) ───────────
    systemd.services.deploy-reverse-tunnel = lib.mkIf (cfg.relayHost != "") {
      description = "Deploy reverse SSH tunnel to ${cfg.relayHost}";
      wantedBy = [ "multi-user.target" ];
      after = [ "network-online.target" "sshd.service" ];
      wants = [ "network-online.target" ];
      serviceConfig = {
        Restart = "always";
        RestartSec = "10s";
        ExecStart = "${pkgs.openssh}/bin/ssh"
          + " -o StrictHostKeyChecking=accept-new"
          + " -o ServerAliveInterval=30"
          + " -o ServerAliveCountMax=3"
          + " -o ExitOnForwardFailure=yes"
          + " -i /var/lib/secrets/deploy-relay-key"
          + " -N"
          + " -R ${toString cfg.reverseTunnelPort}:localhost:22"
          + " -p ${toString cfg.relayPort}"
          + " ${cfg.relayUser}@${cfg.relayHost}";
      };
      path = [ pkgs.openssh ];
    };

    # ── Safety auto-expiry service ────────────────────────────────────────────
    systemd.services.deploy-auto-expire = {
      description = "Auto-expire remote deploy mode after 48 hours";
      wantedBy = [ "multi-user.target" ];
      after = [ "multi-user.target" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = false;
      };
      script = ''
        # 48 hours = 172800 seconds
        sleep $((48 * 60 * 60))
        systemctl stop deploy-reverse-tunnel || true
        mkdir -p /etc/sovran
        echo "expired" > /etc/sovran/deploy-mode
      '';
      path = [ pkgs.coreutils ];
    };

    # ── Deploy-mode indicator file ────────────────────────────────────────────
    environment.etc."sovran/deploy-mode".text = "active";
  };
}
