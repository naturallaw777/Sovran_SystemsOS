{ config, lib, pkgs, ... }:

# ── sovran-provisioner.nix ────────────────────────────────────────────────────
# NixOS module for the Sovran Systems VPS provisioning server.
#
# Deploys:
#   - Headscale (coordination server, listening on 127.0.0.1:8080)
#   - Python Flask provisioning API (port 9090)
#   - Caddy reverse proxy (80/443 with automatic TLS)
#   - Bootstrap service (creates Headscale users + enrollment token on first boot)
#
# Headscale 0.28.0 compatible — uses numeric user IDs (-u <id>) throughout.
# ─────────────────────────────────────────────────────────────────────────────

let
  cfg = config.sovranProvisioner;

  # ── Python Flask provisioner script ────────────────────────────────────────
  provisionerScript = pkgs.writeText "sovran-provisioner.py" ''
    #!/usr/bin/env python3
    """
    Sovran Systems provisioning API — Headscale 0.28.0 compatible.
    Endpoints:
      POST /register  — register a new machine and return a Headscale pre-auth key
      GET  /machines  — list registered machines (requires Bearer token)
      GET  /health    — liveness check
    """
    import json
    import os
    import subprocess
    import time
    from collections import defaultdict
    from functools import wraps
    from pathlib import Path

    from flask import Flask, request, jsonify, abort

    app = Flask(__name__)

    # ── Configuration ─────────────────────────────────────────────────────────
    DATA_DIR       = Path(os.environ.get("PROVISIONER_DATA_DIR", "/var/lib/sovran-provisioner"))
    TOKEN_FILE     = DATA_DIR / "enroll-token"
    MACHINES_FILE  = DATA_DIR / "machines.json"
    HEADSCALE_USER = os.environ.get("HEADSCALE_USER", "sovran-deploy")
    KEY_EXPIRY     = os.environ.get("KEY_EXPIRY", "1h")
    RATE_LIMIT_MAX = int(os.environ.get("RATE_LIMIT_MAX", "10"))
    RATE_LIMIT_WIN = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))

    # ── Simple in-memory rate limiter ─────────────────────────────────────────
    _rate_buckets: dict = defaultdict(list)

    def _rate_limit_check(key: str) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        now = time.monotonic()
        bucket = _rate_buckets[key]
        # Purge entries outside the window
        _rate_buckets[key] = [t for t in bucket if now - t < RATE_LIMIT_WIN]
        if len(_rate_buckets[key]) >= RATE_LIMIT_MAX:
            return False
        _rate_buckets[key].append(now)
        return True

    # ── Helper: read enrollment token ─────────────────────────────────────────
    def _get_token() -> str:
        try:
            return TOKEN_FILE.read_text().strip()
        except FileNotFoundError:
            return ""

    # ── Helper: require Bearer token ──────────────────────────────────────────
    def require_token(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                abort(401)
            token = auth[len("Bearer "):].strip()
            expected = _get_token()
            if not expected or token != expected:
                abort(401)
            return f(*args, **kwargs)
        return decorated

    # ── Helper: persist machine record ────────────────────────────────────────
    def _save_machine(hostname: str, mac: str, tailscale_ip: str = ""):
        machines = _load_machines()
        machines[mac] = {
            "hostname": hostname,
            "mac": mac,
            "registered_at": time.time(),
            "tailscale_ip": tailscale_ip,
        }
        MACHINES_FILE.write_text(json.dumps(machines, indent=2))

    def _load_machines() -> dict:
        try:
            return json.loads(MACHINES_FILE.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    # ── Headscale helpers (0.28.0 compatible) ────────────────────────────────

    def get_user_id(username: str):
        """Look up numeric user ID from username for Headscale 0.28.0."""
        result = subprocess.run(
            ["headscale", "users", "list", "-o", "json"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            app.logger.error("headscale users list failed: %s", result.stderr)
            return None
        try:
            users = json.loads(result.stdout)
        except json.JSONDecodeError:
            app.logger.error("headscale users list returned invalid JSON: %s", result.stdout)
            return None
        for user in users:
            if user.get("name") == username:
                return user.get("id")
        return None

    def create_preauthkey(user_id, expiry: str = "1h") -> str | None:
        """Create a pre-auth key using the numeric user ID (Headscale 0.28.0)."""
        result = subprocess.run(
            ["headscale", "preauthkeys", "create",
             "-u", str(user_id),
             "-e", expiry,
             "-o", "json"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            app.logger.error("headscale preauthkeys create failed: %s", result.stderr)
            return None
        try:
            key_data = json.loads(result.stdout)
        except json.JSONDecodeError:
            app.logger.error("preauthkeys create returned invalid JSON: %s", result.stdout)
            return None
        return key_data.get("key")

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/register", methods=["POST"])
    @require_token
    def register():
        # Rate-limit by source IP
        client_ip = request.remote_addr or "unknown"
        if not _rate_limit_check(client_ip):
            return jsonify({"error": "rate limit exceeded"}), 429

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        hostname = data.get("hostname", "").strip()
        mac      = data.get("mac", "").strip()
        if not hostname or not mac:
            return jsonify({"error": "hostname and mac are required"}), 400

        # Look up the numeric user ID (Headscale 0.28.0 requires -u <id>)
        user_id = get_user_id(HEADSCALE_USER)
        if user_id is None:
            app.logger.error("Headscale user '%s' not found", HEADSCALE_USER)
            return jsonify({"error": "provisioning user not found on Headscale server"}), 500

        # Create a single-use pre-auth key
        key = create_preauthkey(user_id, expiry=KEY_EXPIRY)
        if key is None:
            return jsonify({"error": "failed to create pre-auth key"}), 500

        # Persist the registration record
        _save_machine(hostname, mac)

        login_server = os.environ.get("HEADSCALE_URL", "")
        return jsonify({
            "headscale_key":  key,
            "login_server":   login_server,
            "hostname":       hostname,
        })

    @app.route("/machines")
    @require_token
    def machines():
        return jsonify(list(_load_machines().values()))

    # ── Entry point ───────────────────────────────────────────────────────────

    if __name__ == "__main__":
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        app.run(host="127.0.0.1", port=9090)
  '';

  # ── Headscale YAML config ──────────────────────────────────────────────────
  headscaleConfig = pkgs.writeText "headscale.yaml" ''
    server_url: https://${cfg.headscaleDomain}
    listen_addr: 127.0.0.1:8080
    metrics_listen_addr: 127.0.0.1:9090

    # Logging
    log:
      level: info

    # Database
    database:
      type: sqlite
      sqlite:
        path: /var/lib/headscale/db.sqlite

    # DERP (relay/STUN)
    derp:
      server:
        enabled: false
      urls:
        - https://controlplane.tailscale.com/derpmap/default
      auto_update_enabled: true
      update_frequency: 24h

    # Disable magic DNS by default (clients opt in)
    dns:
      magic_dns: false
      base_domain: sovran.internal

    # Node expiry
    node_update_check_interval: 10s
  '';

in

{
  # ── Module options ─────────────────────────────────────────────────────────
  options.sovranProvisioner = {
    enable = lib.mkEnableOption "Sovran Systems provisioning server (Headscale + Flask API + Caddy)";

    domain = lib.mkOption {
      type        = lib.types.str;
      description = "Public FQDN for the provisioning API (e.g. prov.yourdomain.com)";
    };

    headscaleDomain = lib.mkOption {
      type        = lib.types.str;
      description = "Public FQDN for the Headscale coordination server (e.g. hs.yourdomain.com)";
    };

    headscaleUser = lib.mkOption {
      type    = lib.types.str;
      default = "sovran-deploy";
      description = "Headscale user namespace for deployed machines";
    };

    adminUser = lib.mkOption {
      type    = lib.types.str;
      default = "admin";
      description = "Headscale user namespace for admin workstations";
    };

    keyExpiry = lib.mkOption {
      type    = lib.types.str;
      default = "1h";
      description = "Lifetime of generated pre-auth keys (e.g. 1h, 2h, 24h)";
    };

    rateLimitMax = lib.mkOption {
      type    = lib.types.int;
      default = 10;
      description = "Maximum number of /register calls per rateLimitWindow seconds per IP";
    };

    rateLimitWindow = lib.mkOption {
      type    = lib.types.int;
      default = 60;
      description = "Rate-limit sliding window in seconds";
    };
  };

  # ── Module implementation ──────────────────────────────────────────────────
  config = lib.mkIf cfg.enable {

    # ── Headscale ─────────────────────────────────────────────────────────────
    services.headscale = {
      enable = true;
      address = "127.0.0.1";
      port    = 8080;
      settings = {
        server_url   = "https://${cfg.headscaleDomain}";
        listen_addr  = "127.0.0.1:8080";
        database = {
          type   = "sqlite";
          sqlite = { path = "/var/lib/headscale/db.sqlite"; };
        };
        dns = {
          magic_dns   = false;
          base_domain = "sovran.internal";
        };
        derp = {
          server.enabled       = false;
          urls                 = [ "https://controlplane.tailscale.com/derpmap/default" ];
          auto_update_enabled  = true;
          update_frequency     = "24h";
        };
        log.level = "info";
      };
    };

    # ── Python / Flask dependencies ────────────────────────────────────────────
    environment.systemPackages = [
      pkgs.headscale
      (pkgs.python3.withPackages (ps: [ ps.flask ]))
    ];

    # ── Provisioner systemd service ────────────────────────────────────────────
    systemd.services.sovran-provisioner = {
      description = "Sovran provisioning API";
      after       = [ "network-online.target" "headscale.service" ];
      wants       = [ "network-online.target" ];
      wantedBy    = [ "multi-user.target" ];
      environment = {
        PROVISIONER_DATA_DIR = "/var/lib/sovran-provisioner";
        HEADSCALE_USER       = cfg.headscaleUser;
        KEY_EXPIRY           = cfg.keyExpiry;
        RATE_LIMIT_MAX       = toString cfg.rateLimitMax;
        RATE_LIMIT_WINDOW    = toString cfg.rateLimitWindow;
        HEADSCALE_URL        = "https://${cfg.headscaleDomain}";
      };
      serviceConfig = {
        Type             = "simple";
        Restart          = "on-failure";
        RestartSec       = "5s";
        DynamicUser      = false;
        User             = "sovran-provisioner";
        Group            = "sovran-provisioner";
        StateDirectory   = "sovran-provisioner";
        RuntimeDirectory = "sovran-provisioner";
        ExecStart = "${pkgs.python3.withPackages (ps: [ ps.flask ])}/bin/python3 ${provisionerScript}";
      };
    };

    # ── Dedicated system user for the provisioner ──────────────────────────────
    users.users.sovran-provisioner = {
      isSystemUser = true;
      group        = "sovran-provisioner";
      description  = "Sovran provisioning API service user";
    };
    users.groups.sovran-provisioner = {};

    # Allow the provisioner user to call headscale CLI
    security.sudo.extraRules = [{
      users    = [ "sovran-provisioner" ];
      commands = [{
        command = "${pkgs.headscale}/bin/headscale";
        options = [ "NOPASSWD" ];
      }];
    }];

    # ── Bootstrap service (first-boot: create Headscale users + enroll token) ──
    systemd.services.sovran-provisioner-bootstrap = {
      description = "Bootstrap Headscale users and enrollment token";
      after       = [ "headscale.service" ];
      wants       = [ "headscale.service" ];
      wantedBy    = [ "multi-user.target" ];
      serviceConfig = {
        Type            = "oneshot";
        RemainAfterExit = true;
        StateDirectory  = "sovran-provisioner";
      };
      path = [ pkgs.headscale pkgs.coreutils pkgs.openssl ];
      script = ''
        DATA_DIR="/var/lib/sovran-provisioner"
        TOKEN_FILE="$DATA_DIR/enroll-token"
        STAMP="$DATA_DIR/.bootstrap-done"

        # Idempotent — only run once
        [ -f "$STAMP" ] && exit 0

        # Wait for headscale socket to be ready
        for i in $(seq 1 30); do
          headscale users list -o json >/dev/null 2>&1 && break
          sleep 2
        done

        # Create headscale users if they don't exist
        headscale users list -o json | grep -q '"name":"${cfg.headscaleUser}"' \
          || headscale users create ${cfg.headscaleUser}

        headscale users list -o json | grep -q '"name":"${cfg.adminUser}"' \
          || headscale users create ${cfg.adminUser}

        # Generate enrollment token if not already present
        if [ ! -f "$TOKEN_FILE" ] || [ ! -s "$TOKEN_FILE" ]; then
          openssl rand -hex 32 > "$TOKEN_FILE"
          chmod 600 "$TOKEN_FILE"
        fi

        touch "$STAMP"
        echo "Bootstrap complete."
      '';
    };

    # ── Caddy reverse proxy ────────────────────────────────────────────────────
    services.caddy = {
      enable = true;
      virtualHosts."${cfg.headscaleDomain}" = {
        extraConfig = ''
          reverse_proxy 127.0.0.1:8080
        '';
      };
      virtualHosts."${cfg.domain}" = {
        extraConfig = ''
          reverse_proxy 127.0.0.1:9090
        '';
      };
    };

    # ── Firewall ────────────────────────────────────────────────────────────────
    networking.firewall = {
      allowedTCPPorts = [ 80 443 ];
      allowedUDPPorts = [ 3478 ];
    };
  };
}
