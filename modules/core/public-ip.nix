# ── Unified public-IP detection (privacy-first) ─────────────────────────────
#
# One script, one cache file, every consumer on the system reads the same
# value. Previously the public IP was detected independently in three places,
# each phoning home to a different third party:
#   * the Hub (server.py _get_external_ip) → api.ipify.org / ifconfig.me /
#     icanhazip.com over HTTPS on every /api/network call and every
#     background-loop tick
#   * DDNS (ddns-update.py) → myip.opendns.com via OpenDNS
#   * LiveKit → STUN (its own embedded detection)
#
# This module replaces all of that with a single script
# (/var/lib/sovran/public-ip.py) that detects the IP once per TTL using the
# least-exposing mechanism available, and caches it in
# /var/lib/secrets/external-ip. Consumers (Hub, DDNS, LiveKit) read the cache
# and only invoke the script when it is missing or stale.
#
# Detection chain (first success wins, stops immediately):
#   1. pin         — sovran_systemsOS.elementCalling.externalIP (baked in)
#   2. cache       — /var/lib/secrets/external-ip if newer than cacheTTL
#   3. STUN        — UDP binding request (one packet, no application data,
#                    no HTTP metadata; the same protocol every WebRTC client
#                    uses). Server configurable via publicIP.stunServer.
#   4. DNS         — "myip.opendns.com" A query via publicIP.dnsResolver
#                    (single DNS query, no HTTP headers)
#   5. HTTPS echo  — ONLY endpoints listed in publicIP.httpsEcho (empty by
#                    default → never contacted)
#
# Privacy property: while the cache is fresh, zero third parties are
# contacted. When detection runs, at most ONE party learns the IP per
# refresh interval (default 5 minutes), and the STUN/DNS mechanisms expose
# nothing beyond the bare address.
{
  config,
  pkgs,
  lib,
  ...
}:

let
  stunServer  = config.sovran_systemsOS.publicIP.stunServer;
  stunPort    = config.sovran_systemsOS.publicIP.stunPort;
  dnsResolver = config.sovran_systemsOS.publicIP.dnsResolver;
  httpsEcho   = config.sovran_systemsOS.publicIP.httpsEcho;
  cacheTTL    = config.sovran_systemsOS.publicIP.cacheTTL;

  # Optional pin shared with element-calling (baked in at build time).
  pin = if config.sovran_systemsOS.elementCalling.externalIP != null then config.sovran_systemsOS.elementCalling.externalIP else "";

  echoList = lib.concatStringsSep "," (map (u: "'${u}'") httpsEcho);
in
{
  options.sovran_systemsOS.publicIP = {
    stunServer = lib.mkOption {
      type = lib.types.str;
      default = "stun.l.google.com";
      description = ''
        STUN server used to discover the public IP over UDP. STUN is the most
        privacy-preserving detection mechanism: a single stateless packet,
        no HTTP metadata. Only used when the cache is stale.
      '';
    };
    stunPort = lib.mkOption {
      type = lib.types.port;
      default = 19302;
    };
    dnsResolver = lib.mkOption {
      type = lib.types.str;
      default = "resolver4.opendns.com";
      description = ''
        DNS resolver used as fallback (myip.opendns.com trick) when STUN is
        unavailable (e.g. ISP blocks UDP egress). A single DNS query, no
        HTTP headers.
      '';
    };
    httpsEcho = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      example = [ "https://api.ipify.org" ];
      description = ''
        OPT-IN HTTPS endpoints that return the caller's public IP as a bare
        IPv4 literal. Each listed endpoint observes this server's public IP
        and HTTP metadata every time detection runs. Empty by default — no
        HTTPS echo service is ever contacted unless you add one here. This is
        the last-resort fallback after STUN and DNS.
      '';
    };
    cacheTTL = lib.mkOption {
      type = lib.types.int;
      default = 300;
      description = "Seconds the detected public IP is cached before re-detection.";
    };
  };

  # ── Install the unified detector ──────────────────────────────────────────
  # This module declares `options` above, so ALL configuration must go under
  # the `config` attribute: NixOS forbids mixing bare top-level settings
  # (like `system.*`) with the `options`/`config` keyword attributes in the
  # same module. (Fixes: "Module ... has an unsupported attribute `system'".)
  config.system.activationScripts.sovranPublicIpInstall = lib.stringAfter [ "users" ] ''
    install -d -m 0755 /var/lib/sovran
    cat > /var/lib/sovran/public-ip.py <<'PYEOF'
#!/usr/bin/env python3
"""sovran-public-ip — one detector, one cache, every consumer reads the same IP.

Privacy-first detection chain (first success wins):
  1. pin     — baked in from sovran_systemsOS.elementCalling.externalIP
  2. cache   — /var/lib/secrets/external-ip if newer than CACHE_TTL seconds
  3. STUN    — UDP binding request (one packet, no application data)
  4. DNS     — myip.opendns.com A query via the configured resolver
  5. HTTPS   — ONLY endpoints baked in from publicIP.httpsEcho (opt-in)

Usage:
  public-ip.py check     print current public IP (cache first; refresh if stale)
  public-ip.py refresh   force re-detection, update the cache file, print IP

Exit status: 0 with the IP on stdout on success; 1 if no IP is available
(cached value, if any, is still printed to stdout with a warning on stderr).
"""
import ipaddress
import os
import random
import socket
import struct
import sys
import time
import urllib.request

CACHE_FILE = "/var/lib/secrets/external-ip"
PIN        = "${pin}"
STUN_SERVER = "${stunServer}"
STUN_PORT   = ${toString stunPort}
DNS_RESOLVER = "${dnsResolver}"
DNS_HOST     = "myip.opendns.com"
ECHO_URLS    = [ ${echoList} ]
CACHE_TTL    = ${toString cacheTTL}
TIMEOUT      = 3.0

# ---------------------------------------------------------------------------
# Detection primitives
# ---------------------------------------------------------------------------

def is_usable_ip(text: str) -> bool:
    """True if text is a globally routable IPv4 that LiveKit may advertise."""
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    if ip.version != 4:
        return False
    if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
            or ip.is_reserved or ip.is_unspecified or not ip.is_global):
        return False
    # RFC 6598 shared (CGNAT) space — not reachable from the internet.
    if ip in ipaddress.ip_network("100.64.0.0/10"):
        return False
    return True


def stun_public_ip() -> str | None:
    """RFC 5389 Binding request over UDP; returns the mapped (public) IPv4."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    try:
        txid = random.randbytes(12)
        req = struct.pack("!HHI", 0x0001, 0, 0) + txid  # Binding request
        sock.sendto(req, (STUN_SERVER, STUN_PORT))
        data, _ = sock.recvfrom(2048)
    except OSError:
        return None
    finally:
        sock.close()

    if len(data) < 20:
        return None
    mtype, _mlen = struct.unpack("!HH", data[:4])
    if mtype != 0x0101:  # Binding success response
        return None

    cookie = data[4:8]
    i = 20
    while i + 4 <= len(data):
        atype, alen = struct.unpack("!HH", data[i : i + 4])
        aval = data[i + 4 : i + 4 + alen]
        if atype in (0x0001, 0x0020) and len(aval) >= 8:  # MAPPED / XOR-MAPPED
            family = aval[1]
            if family == 0x01:  # IPv4
                raw = aval[4:8]
                if atype == 0x0020:  # XOR with magic cookie + txid prefix
                    raw = bytes(b ^ c for b, c in zip(raw, cookie + txid[:4]))
                return socket.inet_ntop(socket.AF_INET, raw)
        i += 4 + ((alen + 3) // 4) * 4
    return None


def dns_public_ip() -> str | None:
    """Minimal DNS A query for myip.opendns.com against the given resolver."""
    qid = random.randint(0, 0xFFFF)
    qname = b"".join(bytes([len(p)]) + p.encode() for p in DNS_HOST.split(".")) + b"\x00"
    query = struct.pack("!HHHHHH", qid, 0x0100, 1, 0, 0, 0) + qname + struct.pack("!HH", 1, 1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    try:
        sock.sendto(query, (DNS_RESOLVER, 53))
        data, _ = sock.recvfrom(4096)
    except OSError:
        return None
    finally:
        sock.close()

    try:
        if len(data) < 12:
            return None
        rid, _flags, _qd, an, _ns, _ar = struct.unpack("!HHHHHH", data[:12])
        if rid != qid or an == 0:
            return None
        i = 12
        for _ in range(_qd):  # skip question
            while data[i] != 0:
                i += 1 + data[i]
            i += 5
        for _ in range(an):
            if data[i] & 0xC0 == 0xC0:
                i += 2
            else:
                while data[i] != 0:
                    i += 1 + data[i]
                i += 1
            rtype, _rclass, _ttl, rdlen = struct.unpack("!HHIH", data[i : i + 10])
            i += 10
            if rtype == 1 and rdlen == 4:
                return socket.inet_ntop(socket.AF_INET, data[i : i + 4])
            i += rdlen
    except (IndexError, struct.error):
        return None
    return None


def echo_public_ip() -> str | None:
    """Opt-in HTTPS echo endpoints (baked in at build time; empty by default)."""
    for url in ECHO_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sovran-public-ip"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                text = resp.read().decode().strip()
            if is_usable_ip(text):
                return text
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Cache handling
# ---------------------------------------------------------------------------

def read_cache() -> str:
    try:
        with open(CACHE_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def write_cache(ip: str) -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        tmp = f"{CACHE_FILE}.tmp"
        with open(tmp, "w") as f:
            f.write(ip + "\n")
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass


def cache_fresh() -> bool:
    try:
        return time.time() - os.path.getmtime(CACHE_FILE) < CACHE_TTL
    except OSError:
        return False


def detect() -> str:
    """Run the chain; returns usable IP or an empty string."""
    if PIN and is_usable_ip(PIN):
        return PIN
    for fn in (stun_public_ip, dns_public_ip, echo_public_ip):
        try:
            cand = fn()
        except Exception:
            continue
        if cand and is_usable_ip(cand):
            return cand
    return ""


def main() -> int:
    force = len(sys.argv) > 1 and sys.argv[1] == "refresh"
    ip = ""
    if not force and cache_fresh():
        ip = read_cache()
    if not ip:
        ip = detect()
        if ip:
            write_cache(ip)
        else:
            stale = read_cache()
            if stale:
                print(stale)
                print("WARNING: detection failed; using last known public IP", file=sys.stderr)
                return 0
            print("ERROR: could not determine a public IP (STUN/DNS unreachable)", file=sys.stderr)
            return 1
    print(ip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF
    chmod 0555 /var/lib/sovran/public-ip.py
  '';
}
