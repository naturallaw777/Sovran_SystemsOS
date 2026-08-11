{ config, pkgs, lib, ... }:

{
  # ── Ensure njalla directory exists on every build ────────────────────────
  systemd.tmpfiles.rules = [
    "d /var/lib/njalla 0750 root root -"
  ];

  # ── Install the shared validation helper so the DDNS runner can import it ─
  # The exact same _validate_ddns_url() function used by the Hub web application
  # is installed here as a read-only system file.  The DDNS runner imports it
  # directly so the two code paths share one validator — no weaker inline copy.
  environment.etc."sovran/security_helpers.py" = {
    source = ../../app/sovran_systemsos_web/security_helpers.py;
    mode   = "0444";
    user   = "root";
    group  = "root";
  };

  # ── Safe DDNS update service ─────────────────────────────────────────────
  # Reads DDNS update URLs from the JSON store written by the Hub API and
  # invokes curl directly — no shell interpolation, no script execution.
  # Replaces the legacy root cron job that ran /var/lib/njalla/njalla.sh.
  systemd.services.sovran-ddns-update = {
    description = "Sovran Njal.la DDNS update (safe JSON-based runner)";
    wants = [ "network-online.target" ];
    after = [ "network-online.target" ];
    serviceConfig = {
      Type        = "oneshot";
      User        = "root";
      ExecStart   = "${pkgs.python3}/bin/python3 /var/lib/sovran/ddns-update.py";
      # Harden the service — it only needs network access and read access to
      # /var/lib/njalla/ddns_urls.json.
      NoNewPrivileges    = true;
      ProtectSystem      = "strict";
      ReadWritePaths     = [ "/var/lib/njalla" ];
      ReadOnlyPaths      = [ "/etc/sovran" ];
      ProtectHome        = true;
      PrivateTmp         = true;
      RestrictAddressFamilies = [ "AF_INET" "AF_INET6" ];
    };
  };

  # Run the update every 15 minutes
  systemd.timers.sovran-ddns-update = {
    description = "Sovran Njal.la DDNS update timer";
    wantedBy    = [ "timers.target" ];
    timerConfig = {
      OnBootSec    = "2min";
      OnUnitActiveSec = "15min";
      Persistent   = true;
    };
  };

  # Install the Python runner script at build time so the service can find it.
  # The script is owned by root and not world-writable.
  # Uses _validate_ddns_url() from /etc/sovran/security_helpers.py — the same
  # production validator used by the Hub API — before executing any curl call.
  # No shell is used; no redirects; no script execution.
  # ${IP} placeholder is preserved in stored URLs and substituted at runtime;
  # the URL is validated after substitution so any remaining $ is rejected.
  system.activationScripts.sovran-ddns-update-script = ''
    install -d -m 0755 /var/lib/sovran
    cat > /var/lib/sovran/ddns-update.py <<'PYEOF'
#!/usr/bin/env python3
"""Sovran safe DDNS update runner.

Reads ddns_urls.json, substitutes the public IP for the ''${IP} placeholder,
validates each URL using the production _validate_ddns_url() from
/etc/sovran/security_helpers.py, then calls curl per URL.
No shell interpolation.  No redirects.  No script execution.
"""
import ipaddress, json, os, subprocess, sys

sys.path.insert(0, '/etc/sovran')
try:
    from security_helpers import _validate_ddns_url
except ImportError:
    sys.exit(0)  # validator not available — skip silently

URLS_FILE = "/var/lib/njalla/ddns_urls.json"

try:
    with open(URLS_FILE) as f:
        urls = json.load(f)
    if not isinstance(urls, list):
        raise ValueError("not a list")
except Exception:
    sys.exit(0)  # no URLs configured — nothing to do

# Resolve current public IP once
public_ip = ""
try:
    r = subprocess.run(
        ["dig", "@resolver4.opendns.com", "myip.opendns.com", "+short", "-4"],
        capture_output=True, text=True, timeout=10,
    )
    raw = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
    ipaddress.ip_address(raw)  # validates — raises if not a real IP
    public_ip = raw
except Exception:
    pass

if not public_ip:
    sys.exit(0)  # no IP resolved — skip to avoid sending bare ''${IP}

for raw_url in urls:
    try:
        # Substitute ''${IP} placeholder then validate through production validator.
        # After substitution there must be no $ left; _validate_ddns_url rejects
        # any remaining $ expression.
        url = raw_url.replace("''${IP}", public_ip)
        _validate_ddns_url(url)
        subprocess.run(
            ["curl", "--silent", "--max-time", "15", "--fail", "--no-location", url],
            timeout=20, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (ValueError, Exception):
        pass
PYEOF
    chmod 0500 /var/lib/sovran/ddns-update.py
  '';
}
