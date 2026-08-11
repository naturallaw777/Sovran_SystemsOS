{ config, pkgs, lib, ... }:

{
  # ── Ensure njalla directory exists on every build ────────────────────────
  systemd.tmpfiles.rules = [
    "d /var/lib/njalla 0750 root root -"
  ];

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
  system.activationScripts.sovran-ddns-update-script = ''
    install -d -m 0755 /var/lib/sovran
    cat > /var/lib/sovran/ddns-update.py <<'PYEOF'
#!/usr/bin/env python3
"""Sovran safe DDNS update runner.  Read ddns_urls.json, call curl per URL."""
import ipaddress, json, os, subprocess

URLS_FILE = "/var/lib/njalla/ddns_urls.json"
ALLOWED_HOSTS = frozenset(["njal.la", "www.njal.la"])

try:
    with open(URLS_FILE) as f:
        urls = json.load(f)
    if not isinstance(urls, list):
        raise ValueError("not a list")
except Exception:
    raise SystemExit(0)  # no URLs configured — nothing to do

# Resolve current public IP once
public_ip = ""
try:
    r = subprocess.run(
        ["dig", "@resolver4.opendns.com", "myip.opendns.com", "+short", "-4"],
        capture_output=True, text=True, timeout=10,
    )
    raw = r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""
    ipaddress.ip_address(raw)  # validates
    public_ip = raw
except Exception:
    pass

import urllib.parse
for raw_url in urls:
    try:
        url = raw_url.replace("\${IP}", public_ip) if public_ip else raw_url
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() != "https":
            continue
        if (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
            continue
        subprocess.run(
            ["curl", "--silent", "--max-time", "15", "--fail", "--no-location", url],
            timeout=20, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
PYEOF
    chmod 0500 /var/lib/sovran/ddns-update.py
  '';
}
