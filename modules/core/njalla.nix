{ config, pkgs, lib, ... }:

{
  # The public-IP detector (STUN / OpenDNS / HTTPS echo) is gone: the public
  # address is whatever Njal.la reports back for the DDNS update below, and
  # nothing else on the system looks it up. Fail with a pointer, instead of
  # silently ignoring them, if a custom.nix still sets one of its old options.
  imports = map (opt:
    lib.mkRemovedOptionModule [ "sovran_systemsOS" "publicIP" opt ]
      "Sovran no longer looks up the public IP: the Njal.la DDNS update reports it (modules/core/njalla.nix). To force an address for Element Calling, set sovran_systemsOS.elementCalling.externalIP."
  ) [ "stunServer" "stunPort" "dnsResolver" "httpsEcho" "cacheTTL" ];

  # ── Ensure njalla directory exists on every build ────────────────────────
  systemd.tmpfiles.rules = [
    "d /var/lib/njalla 0750 root root -"
  ];

  # ── Install the DDNS runner and the validator it shares with the Hub ─────
  # Both files come straight from the Hub's source tree and are installed side
  # by side as read-only system files. The runner imports the exact same
  # _validate_ddns_url() the Hub API uses — no weaker inline copy.
  environment.etc."sovran/security_helpers.py" = {
    source = ../../app/sovran_systemsos_web/security_helpers.py;
    mode   = "0444";
    user   = "root";
    group  = "root";
  };
  environment.etc."sovran/ddns-update.py" = {
    source = ../../app/sovran_systemsos_web/ddns_update.py;
    mode   = "0444";
    user   = "root";
    group  = "root";
  };

  # ── Safe DDNS update service ─────────────────────────────────────────────
  # Reads DDNS update URLs from the JSON store written by the Hub API and
  # invokes curl directly — no shell interpolation, no script execution.
  # Njal.la is asked to use the address the request came from ("&auto") and
  # reports it back; the runner saves it to /var/lib/secrets/external-ip,
  # where LiveKit and the Hub read it. See app/sovran_systemsos_web/ddns_update.py.
  systemd.services.sovran-ddns-update = {
    description = "Sovran Njal.la DDNS update (safe JSON-based runner)";
    wants = [ "network-online.target" ];
    after = [ "network-online.target" ];
    # curl is not in a NixOS unit's default PATH (coreutils, findutils, grep,
    # sed, systemd): without this the runner cannot start it.
    path = [ pkgs.curl ];
    serviceConfig = {
      Type        = "oneshot";
      User        = "root";
      ExecStart   = "${pkgs.python3}/bin/python3 /etc/sovran/ddns-update.py";
      # Harden the service — it needs network access, the URL store, and the
      # file that receives the reported address.
      NoNewPrivileges    = true;
      ProtectSystem      = "strict";
      ReadWritePaths     = [ "/var/lib/njalla" "/var/lib/secrets" ];
      ReadOnlyPaths      = [ "/etc/sovran" ];
      ProtectHome        = true;
      PrivateTmp         = true;
      # AF_UNIX: name lookups can go through nscd / systemd-resolved sockets.
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
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

  # The runner used to be written to /var/lib/sovran by this activation script,
  # next to the old public-ip.py detector. Remove those stale copies.
  system.activationScripts.sovran-ddns-update-script = ''
    rm -f /var/lib/sovran/ddns-update.py /var/lib/sovran/public-ip.py
  '';
}
