{ config, lib, pkgs, ... }:

let
  cfg = config.sovranProvisioner;

  # ── Python provisioning API ──────────────────────────────────────────────────
  provisionerScript = pkgs.writeTextFile {
    name = "sovran-provisioner-app.py";
    text = ''
      #!/usr/bin/env python3
      """Sovran Systems — Machine Provisioning Server"""
      import subprocess, secrets, json, time, os, fcntl, threading
      from datetime import datetime, timezone
      from flask import Flask, request, jsonify

      app = Flask(__name__)

      STATE_DIR       = os.environ.get("SOVRAN_STATE_DIR", "/var/lib/sovran-provisioner")
      TOKEN_FILE      = os.environ.get("SOVRAN_ENROLL_TOKEN_FILE", f"{STATE_DIR}/enroll-token")
      HEADSCALE_USER  = os.environ.get("HEADSCALE_USER", "sovran-deploy")
      KEY_EXPIRY      = os.environ.get("KEY_EXPIRY", "1h")
      HEADSCALE_DOMAIN = os.environ.get("HEADSCALE_DOMAIN", "localhost")
      RATE_LIMIT_MAX  = int(os.environ.get("RATE_LIMIT_MAX", "10"))
      RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))

      _rate_lock = threading.Lock()
      rate_state = {"count": 0, "window_start": time.time()}

      def get_enroll_token():
          try:
              with open(TOKEN_FILE, "r") as f:
                  return f.read().strip()
          except FileNotFoundError:
              return ""

      def check_rate_limit():
          now = time.time()
          with _rate_lock:
              if now - rate_state["window_start"] > RATE_LIMIT_WINDOW:
                  rate_state["count"] = 0
                  rate_state["window_start"] = now
              rate_state["count"] += 1
              return rate_state["count"] <= RATE_LIMIT_MAX

      def validate_token(req):
          token = req.headers.get("Authorization", "").replace("Bearer ", "")
          expected = get_enroll_token()
          if not expected:
              return False
          return secrets.compare_digest(token, expected)

      def create_headscale_key():
          result = subprocess.run(
              ["headscale", "preauthkeys", "create",
               "--user", HEADSCALE_USER,
               "--expiration", KEY_EXPIRY,
               "--ephemeral",
               "--output", "json"],
              capture_output=True, text=True
          )
          if result.returncode != 0:
              raise RuntimeError(f"headscale error: {result.stderr}")
          data = json.loads(result.stdout)
          return data.get("key", data.get("preAuthKey", {}).get("key", ""))

      _reg_lock = threading.Lock()

      def load_registrations():
          path = f"{STATE_DIR}/registrations.json"
          try:
              with open(path, "r") as f:
                  return json.load(f)
          except (FileNotFoundError, json.JSONDecodeError):
              return []

      def save_registration(entry):
          path = f"{STATE_DIR}/registrations.json"
          with _reg_lock:
              regs = load_registrations()
              regs.append(entry)
              # Keep last 1000 entries
              regs = regs[-1000:]
              with open(path, "w") as f:
                  fcntl.flock(f, fcntl.LOCK_EX)
                  json.dump(regs, f, indent=2)

      @app.route("/health", methods=["GET"])
      def health():
          return jsonify({"status": "ok"})

      @app.route("/register", methods=["POST"])
      def register():
          if not check_rate_limit():
              return jsonify({"error": "rate limited"}), 429
          if not validate_token(request):
              return jsonify({"error": "unauthorized"}), 401

          body = request.get_json(silent=True) or {}

          try:
              key = create_headscale_key()
          except RuntimeError as e:
              app.logger.error(f"Headscale key creation failed: {e}")
              return jsonify({"error": "internal server error"}), 500

          entry = {
              "hostname": body.get("hostname", "unknown"),
              "mac": body.get("mac", "unknown"),
              "ip": request.remote_addr,
              "registered_at": datetime.now(timezone.utc).isoformat(),
              "key_prefix": key[:12] + "..." if key else "none",
          }
          save_registration(entry)
          app.logger.info(f"Machine registered: {entry}")

          return jsonify({
              "headscale_key": key,
              "login_server": f"https://{HEADSCALE_DOMAIN}",
          })

      @app.route("/machines", methods=["GET"])
      def list_machines():
          if not validate_token(request):
              return jsonify({"error": "unauthorized"}), 401
          return jsonify(load_registrations())

      if __name__ == "__main__":
          app.run(host="127.0.0.1", port=9090)
    '';
  };

  provisionerPython = pkgs.python3.withPackages (ps: [ ps.flask ]);

  provisionerApp = pkgs.writeShellScriptBin "sovran-provisioner" ''
    exec ${provisionerPython}/bin/python3 ${provisionerScript}
  '';

in

{
  options.sovranProvisioner = {
    enable = lib.mkEnableOption "Sovran Systems provisioning server";

    domain = lib.mkOption {
      type = lib.types.str;
      description = "Domain for the provisioning API (e.g. prov.sovransystems.com)";
    };

    headscaleDomain = lib.mkOption {
      type = lib.types.str;
      description = "Domain for the Headscale coordination server (e.g. hs.sovransystems.com)";
    };

    headscaleUser = lib.mkOption {
      type = lib.types.str;
      default = "sovran-deploy";
      description = "Headscale user/namespace for deployed machines";
    };

    adminUser = lib.mkOption {
      type = lib.types.str;
      default = "admin";
      description = "Headscale user/namespace for admin workstations";
    };

    keyExpiry = lib.mkOption {
      type = lib.types.str;
      default = "1h";
      description = "How long each auto-generated Headscale pre-auth key lives";
    };

    rateLimitMax = lib.mkOption {
      type = lib.types.int;
      default = 10;
      description = "Max registrations per rate-limit window";
    };

    rateLimitWindow = lib.mkOption {
      type = lib.types.int;
      default = 60;
      description = "Rate-limit window in seconds";
    };

    stateDir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/sovran-provisioner";
      description = "Directory for provisioner state (enrollment token, logs)";
    };
  };

  config = lib.mkIf cfg.enable {

    # ── Headscale ────────────────────────────────────────────────────────────
    services.headscale = {
      enable = true;
      address = "127.0.0.1";
      port = 8080;
      settings = {
        server_url = "https://${cfg.headscaleDomain}";
        database = {
          type = "sqlite3";
          sqlite.path = "/var/lib/headscale/db.sqlite";
        };
        prefixes = {
          v4 = "100.64.0.0/10";
          v6 = "fd7a:115c:a1e0::/48";
        };
        derp = {
          server = {
            enabled = true;
            region_id = 999;
            stun_listen_addr = "0.0.0.0:3478";
          };
          urls = [];
          auto_update_enabled = false;
        };
        dns = {
          magic_dns = true;
          base_domain = "sovran.tail";
          nameservers.global = [ "1.1.1.1" "9.9.9.9" ];
        };
      };
    };

    # ── Caddy reverse proxy ───────────────────────────────────────────────────
    services.caddy = {
      enable = true;
      virtualHosts = {
        "${cfg.headscaleDomain}" = {
          extraConfig = "reverse_proxy localhost:8080";
        };
        "${cfg.domain}" = {
          extraConfig = "reverse_proxy localhost:9090";
        };
      };
    };

    # ── Provisioner init service (generate token + create headscale users) ────
    systemd.services.sovran-provisioner-init = {
      description = "Initialize Sovran provisioner state";
      wantedBy = [ "multi-user.target" ];
      before = [ "sovran-provisioner.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        mkdir -p ${cfg.stateDir}

        # Auto-generate enrollment token on first boot if not already present
        TOKEN_FILE="${cfg.stateDir}/enroll-token"
        if [ ! -f "$TOKEN_FILE" ]; then
          ${pkgs.openssl}/bin/openssl rand -hex 32 > "$TOKEN_FILE"
          chmod 600 "$TOKEN_FILE"
          echo "Generated new enrollment token: $(cat $TOKEN_FILE)"
        fi

        # Ensure headscale users exist
        ${pkgs.headscale}/bin/headscale users create ${cfg.headscaleUser} 2>/dev/null || true
        ${pkgs.headscale}/bin/headscale users create ${cfg.adminUser} 2>/dev/null || true

        # Initialize registrations log
        [ -f "${cfg.stateDir}/registrations.json" ] || echo "[]" > "${cfg.stateDir}/registrations.json"
      '';
      path = [ pkgs.headscale pkgs.openssl pkgs.coreutils ];
    };

    # ── Provisioning API service ──────────────────────────────────────────────
    systemd.services.sovran-provisioner = {
      description = "Sovran Systems Provisioning API";
      wantedBy = [ "multi-user.target" ];
      after = [ "network-online.target" "headscale.service" "sovran-provisioner-init.service" ];
      wants = [ "network-online.target" ];
      environment = {
        SOVRAN_ENROLL_TOKEN_FILE = "${cfg.stateDir}/enroll-token";
        SOVRAN_STATE_DIR = cfg.stateDir;
        HEADSCALE_USER = cfg.headscaleUser;
        KEY_EXPIRY = cfg.keyExpiry;
        HEADSCALE_DOMAIN = cfg.headscaleDomain;
        RATE_LIMIT_MAX = toString cfg.rateLimitMax;
        RATE_LIMIT_WINDOW = toString cfg.rateLimitWindow;
      };
      serviceConfig = {
        ExecStart = "${provisionerApp}/bin/sovran-provisioner";
        User = "sovran-provisioner";
        Group = "sovran-provisioner";
        StateDirectory = "sovran-provisioner";
        Restart = "always";
        RestartSec = "5s";
        # Give access to headscale CLI
        SupplementaryGroups = [ "headscale" ];
      };
      path = [ pkgs.headscale ];
    };

    # ── System user for provisioner ───────────────────────────────────────────
    users.users.sovran-provisioner = {
      isSystemUser = true;
      group = "sovran-provisioner";
      home = cfg.stateDir;
    };
    users.groups.sovran-provisioner = {};

    # ── Firewall ──────────────────────────────────────────────────────────────
    networking.firewall.allowedTCPPorts = [ 80 443 ];
    networking.firewall.allowedUDPPorts = [ 3478 ]; # STUN for DERP
  };
}
