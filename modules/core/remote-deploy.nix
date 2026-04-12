{ config, lib, pkgs, ... }:

let
  cfg = config.sovran_systemsOS.deploy;
in

{
  options.sovran_systemsOS.deploy = {
    enable = lib.mkEnableOption "Remote deploy mode";

    authorizedKey = lib.mkOption {
      type = lib.types.str;
      default = "";
      description = "Deployer's SSH public key for root access";
    };

    headscaleServer = lib.mkOption {
      type = lib.types.str;
      default = "";
      description = "Headscale login server URL (e.g. https://hs.sovransystems.com). If set, Tailscale is used for post-install connectivity.";
    };

    headscaleAuthKeyFile = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/secrets/headscale-authkey";
      description = "Path to file containing the Headscale pre-auth key for post-install enrollment";
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

    # ── Tailscale / Headscale VPN (only when headscaleServer is configured) ──
    services.tailscale = lib.mkIf (cfg.headscaleServer != "") {
      enable = true;
    };

    environment.systemPackages = lib.mkIf (cfg.headscaleServer != "") [ pkgs.tailscale ];

    systemd.services.deploy-tailscale-connect = lib.mkIf (cfg.headscaleServer != "") {
      description = "Connect to Headscale Tailnet for post-install remote access";
      wantedBy = [ "multi-user.target" ];
      after = [ "network-online.target" "tailscaled.service" ];
      wants = [ "network-online.target" "tailscaled.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        AUTH_KEY_FILE="${cfg.headscaleAuthKeyFile}"
        if [ ! -f "$AUTH_KEY_FILE" ]; then
          echo "Headscale auth key file not found: $AUTH_KEY_FILE — skipping Tailscale enrollment"
          exit 0
        fi
        AUTH_KEY=$(cat "$AUTH_KEY_FILE")
        [ -n "$AUTH_KEY" ] || { echo "Auth key file is empty, skipping"; exit 0; }

        HOSTNAME_SUFFIX=$(hostname | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')
        HOSTNAME="sovran-$HOSTNAME_SUFFIX"

        echo "Joining Tailnet via ${cfg.headscaleServer} as $HOSTNAME..."
        ${pkgs.tailscale}/bin/tailscale up \
          --login-server="${cfg.headscaleServer}" \
          --authkey="$AUTH_KEY" \
          --hostname="$HOSTNAME"

        echo "Tailscale IP: $(${pkgs.tailscale}/bin/tailscale ip -4 2>/dev/null || echo 'pending')"
      '';
      path = [ pkgs.tailscale pkgs.coreutils ];
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
        systemctl stop deploy-tailscale-connect || true
        mkdir -p /etc/sovran
        echo "expired" > /etc/sovran/deploy-mode
      '';
      path = [ pkgs.coreutils ];
    };

    # ── Deploy-mode indicator file ────────────────────────────────────────────
    environment.etc."sovran/deploy-mode".text = "active";
  };
}
