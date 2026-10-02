#!/usr/bin/env python3
"""Sovran DDNS update runner (sovran-ddns-update.service).

For every stored Njal.la update URL this asks Njal.la to point the record at
the address the request came from ("&auto"), then reads back the address
Njal.la says it recorded.  That address is saved to /var/lib/secrets/external-ip,
where livekit-turn-setup and the Hub read it.

Njal.la is the only party involved.  It has to learn the address to publish
it, so nothing else -- no STUN server, no public resolver, no "what is my IP"
service -- is ever asked for it.

Kept from the previous runner:
  * every URL goes through _validate_ddns_url() (https, njal.la only, /update/)
  * curl is run directly: no shell, no redirects
  * the update key is never printed or logged

The module is installed next to security_helpers.py (/etc/sovran/) and run as a
script by the service; it is also importable as
sovran_systemsos_web.ddns_update so the tests can exercise it.
"""
import ipaddress
import json
import os
import subprocess
import sys
import tempfile

try:
    from .security_helpers import _validate_ddns_url  # imported as part of the Hub package
except ImportError:  # run as a script from /etc/sovran, next to security_helpers.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from security_helpers import _validate_ddns_url

URLS_FILE = "/var/lib/njalla/ddns_urls.json"
IP_FILE = "/var/lib/secrets/external-ip"

_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def is_public_ipv4(value) -> bool:
    """True for a globally routable IPv4 literal (not private, loopback, CGNAT ...)."""
    try:
        ip = ipaddress.ip_address(str(value).strip())
    except ValueError:
        return False
    if ip.version != 4 or ip in _CGNAT:
        return False
    # is_global alone is not enough: CPython reports multicast as global.
    return ip.is_global and not (
        ip.is_multicast or ip.is_reserved or ip.is_loopback
        or ip.is_link_local or ip.is_unspecified or ip.is_private
    )


def normalise_url(raw: str) -> str:
    """Return the URL to call for a stored (or freshly pasted) update URL.

    * Older Hubs stored "...&a=${IP}": the address was looked up locally and
      substituted.  Njal.la can use the address the request came from, so that
      placeholder becomes "&auto".
    * "&quiet" is dropped: the reply is how we learn the address Njal.la recorded.
    """
    return raw.replace("&a=${IP}", "&auto").replace("&quiet", "")


def parse_reply(body: str):
    """Return the public IPv4 address Njal.la says it recorded, or None.

    A successful update replies with JSON of the form
        {"status": 200, "message": "record updated", "value": {"A": "203.0.113.7", ...}}
    """
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or str(data.get("status")) != "200":
        return None
    value = data.get("value")
    ip = value.get("A") if isinstance(value, dict) else None
    return str(ip).strip() if is_public_ipv4(ip) else None


def read_ip_file(path: str = None):
    """The address recorded by the last successful update, or None."""
    try:
        with open(path or IP_FILE) as f:
            return f.read().strip() or None
    except OSError:
        return None


def write_ip_file(ip: str, path: str = None) -> None:
    """Replace the file atomically so a path watcher never sees a partial write."""
    path = path or IP_FILE
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".external-ip-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(ip)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update_all(urls, *, run=None, validate=_validate_ddns_url):
    """Call every update URL once; return the address Njal.la reported, or None.

    Nothing secret is printed: URLs are only ever referred to by position.
    """
    run = run or subprocess.run  # resolved per call so tests can substitute it
    reported = None
    seen = set()
    todo = []
    for raw in urls:
        url = normalise_url(raw)
        if url not in seen:  # an old "&a=${IP}" entry and its "&auto" twin are one record
            seen.add(url)
            todo.append(url)
    for number, url in enumerate(todo, 1):
        try:
            validate(url)
            proc = run(
                ["curl", "--silent", "--ipv4", "--max-time", "15", "--fail", "--no-location", url],
                capture_output=True, text=True, timeout=20, check=False,
            )
        except Exception:
            print(f"DDNS update {number}/{len(todo)}: skipped (invalid URL or curl unavailable)")
            continue
        if proc.returncode != 0:
            print(f"DDNS update {number}/{len(todo)}: failed (curl exit {proc.returncode})")
            continue
        ip = parse_reply(proc.stdout)
        if ip is None:
            print(f"DDNS update {number}/{len(todo)}: Njal.la did not report a public IPv4 address")
            continue
        print(f"DDNS update {number}/{len(todo)}: ok")
        if reported is None:
            reported = ip
        elif ip != reported:
            print("DDNS: Njal.la reported different addresses for different records; using the first")
    return reported


def main() -> int:
    try:
        with open(URLS_FILE) as f:
            urls = json.load(f)
        if not isinstance(urls, list):
            raise ValueError("not a list")
    except Exception:
        return 0  # no URLs configured -- nothing to do
    urls = [u for u in urls if isinstance(u, str)]
    if not urls:
        return 0

    ip = update_all(urls)
    if ip is None:
        print("DDNS: no address reported by Njal.la; keeping the last known one")
        return 0
    previous = read_ip_file()
    if ip == previous:
        print(f"DDNS: public IP unchanged ({ip})")
        return 0
    write_ip_file(ip)
    print(f"DDNS: public IP is now {ip} (was {previous or 'unknown'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
