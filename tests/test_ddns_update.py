"""Tests for the DDNS runner (sovran_systemsos_web.ddns_update).

The runner asks Njal.la to use the address the request came from ("&auto"),
reads back the address Njal.la recorded and saves it for LiveKit and the Hub.

Tests must never:
  - access the network (curl is replaced by a fake ``run``)
  - write to system paths (the URL and IP files live in a temp dir)
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_APP_PARENT = os.path.join(_REPO_ROOT, "app")
if _APP_PARENT not in sys.path:
    sys.path.insert(0, _APP_PARENT)

from sovran_systemsos_web import ddns_update as d  # noqa: E402

KEY = "SECRETKEY123"
AUTO_URL = f"https://njal.la/update/?h=sub.example.com&k={KEY}&auto"
LEGACY_URL = f"https://njal.la/update/?h=sub.example.com&k={KEY}&a=${{IP}}"
PUBLIC_IP = "93.184.216.34"
OTHER_IP = "8.8.4.4"


def reply(ip=PUBLIC_IP, status=200):
    return json.dumps({"status": status, "message": "record updated", "value": {"A": ip}})


class FakeRun:
    """Stands in for subprocess.run; records every command it is given."""

    def __init__(self, stdout=None, returncode=0, raises=None):
        self.stdout = reply() if stdout is None else stdout
        self.returncode = returncode
        self.raises = raises
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=self.stdout, stderr="")


class NormaliseUrlTests(unittest.TestCase):
    def test_legacy_placeholder_becomes_auto(self):
        self.assertEqual(d.normalise_url(LEGACY_URL), AUTO_URL)

    def test_quiet_is_dropped_so_the_reply_can_be_read(self):
        self.assertEqual(d.normalise_url(AUTO_URL + "&quiet"), AUTO_URL)

    def test_plain_auto_is_unchanged(self):
        self.assertEqual(d.normalise_url(AUTO_URL), AUTO_URL)

    def test_explicit_address_is_unchanged(self):
        url = "https://njal.la/update/?h=a.example.com&k=K&a=93.184.216.34"
        self.assertEqual(d.normalise_url(url), url)


class IsPublicIpv4Tests(unittest.TestCase):
    def test_public_addresses(self):
        for ip in ("93.184.216.34", "8.8.8.8", " 1.1.1.1\n"):
            self.assertTrue(d.is_public_ipv4(ip), ip)

    def test_everything_else_is_rejected(self):
        for ip in ("10.0.0.1", "192.168.1.5", "172.16.0.9", "127.0.0.1", "169.254.1.1",
                   "100.64.0.1", "0.0.0.0", "224.0.0.1", "::1", "2001:4860:4860::8888",
                   "not-an-ip", "", None):
            self.assertFalse(d.is_public_ipv4(ip), ip)


class ParseReplyTests(unittest.TestCase):
    def test_success_returns_the_recorded_address(self):
        self.assertEqual(d.parse_reply(reply()), PUBLIC_IP)

    def test_status_may_be_a_string(self):
        self.assertEqual(d.parse_reply(reply(status="200")), PUBLIC_IP)

    def test_error_status_is_rejected(self):
        body = json.dumps({"status": 401, "message": "invalid host or key"})
        self.assertIsNone(d.parse_reply(body))

    def test_garbage_is_rejected(self):
        for body in ("", "not json", "[]", "null", "{}", json.dumps({"status": 200})):
            self.assertIsNone(d.parse_reply(body), body)

    def test_non_public_or_non_ipv4_address_is_rejected(self):
        for ip in ("10.1.2.3", "100.64.9.9", "127.0.0.1", "::1", "2001:4860:4860::8888", "x"):
            self.assertIsNone(d.parse_reply(reply(ip)), ip)


class IpFileTests(unittest.TestCase):
    def test_write_then_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "secrets", "external-ip")
            d.write_ip_file(PUBLIC_IP, path)
            self.assertEqual(d.read_ip_file(path), PUBLIC_IP)
            self.assertEqual(open(path).read(), PUBLIC_IP)  # no trailing newline
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o644)

    def test_replace_is_atomic_and_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "external-ip")
            d.write_ip_file(PUBLIC_IP, path)
            d.write_ip_file(OTHER_IP, path)
            self.assertEqual(d.read_ip_file(path), OTHER_IP)
            self.assertEqual(os.listdir(tmp), ["external-ip"])

    def test_missing_file_reads_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(d.read_ip_file(os.path.join(tmp, "nope")))


class UpdateAllTests(unittest.TestCase):
    def run_update(self, urls, fake):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = d.update_all(urls, run=fake)
        return result, out.getvalue()

    def test_curl_is_called_directly_with_ipv4_and_no_redirects(self):
        fake = FakeRun()
        result, _ = self.run_update([AUTO_URL], fake)
        self.assertEqual(result, PUBLIC_IP)
        self.assertEqual(len(fake.calls), 1)
        cmd = fake.calls[0]
        self.assertEqual(cmd[0], "curl")
        for flag in ("--ipv4", "--no-location", "--fail", "--silent"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[-1], AUTO_URL)

    def test_legacy_entry_and_its_auto_twin_are_one_call(self):
        fake = FakeRun()
        self.run_update([LEGACY_URL, AUTO_URL], fake)
        self.assertEqual(fake.calls[0][-1], AUTO_URL)
        self.assertEqual(len(fake.calls), 1)

    def test_url_for_another_host_is_never_called(self):
        fake = FakeRun()
        result, _ = self.run_update([f"https://evil.example/update/?h=x&k={KEY}&auto"], fake)
        self.assertIsNone(result)
        self.assertEqual(fake.calls, [])

    def test_failed_curl_yields_nothing(self):
        result, _ = self.run_update([AUTO_URL], FakeRun(returncode=22))
        self.assertIsNone(result)

    def test_reply_without_an_address_yields_nothing(self):
        result, _ = self.run_update([AUTO_URL], FakeRun(stdout=json.dumps({"status": 200})))
        self.assertIsNone(result)

    def test_missing_curl_is_survived(self):
        result, out = self.run_update([AUTO_URL], FakeRun(raises=FileNotFoundError("curl")))
        self.assertIsNone(result)
        self.assertIn("skipped", out)

    def test_first_reported_address_wins(self):
        calls = iter([reply(PUBLIC_IP), reply(OTHER_IP)])

        def fake(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout=next(calls), stderr="")

        other = f"https://njal.la/update/?h=other.example.com&k={KEY}&auto"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = d.update_all([AUTO_URL, other], run=fake)
        self.assertEqual(result, PUBLIC_IP)

    def test_the_key_is_never_printed(self):
        for fake in (FakeRun(), FakeRun(returncode=22), FakeRun(stdout="junk"),
                     FakeRun(raises=FileNotFoundError("curl"))):
            _, out = self.run_update([AUTO_URL, LEGACY_URL], fake)
            self.assertNotIn(KEY, out)


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.urls_file = os.path.join(self.tmp.name, "ddns_urls.json")
        self.ip_file = os.path.join(self.tmp.name, "secrets", "external-ip")
        for patch in (mock.patch.object(d, "URLS_FILE", self.urls_file),
                      mock.patch.object(d, "IP_FILE", self.ip_file)):
            patch.start()
            self.addCleanup(patch.stop)

    def store(self, urls):
        with open(self.urls_file, "w") as f:
            json.dump(urls, f)

    def main(self, fake):
        out = io.StringIO()
        with mock.patch.object(d.subprocess, "run", fake), contextlib.redirect_stdout(out):
            code = d.main()
        self.assertEqual(code, 0)
        return out.getvalue()

    def test_first_update_records_the_address(self):
        self.store([LEGACY_URL])
        out = self.main(FakeRun())
        self.assertEqual(d.read_ip_file(self.ip_file), PUBLIC_IP)
        self.assertIn("now " + PUBLIC_IP, out)
        self.assertNotIn(KEY, out)

    def test_unchanged_address_does_not_touch_the_file(self):
        # A path unit restarts LiveKit whenever the file is written, so an
        # unchanged address must not rewrite it.
        self.store([AUTO_URL])
        self.main(FakeRun())
        before = os.stat(self.ip_file)
        out = self.main(FakeRun())
        after = os.stat(self.ip_file)
        self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))
        self.assertIn("unchanged", out)

    def test_changed_address_is_recorded(self):
        self.store([AUTO_URL])
        self.main(FakeRun(stdout=reply(PUBLIC_IP)))
        out = self.main(FakeRun(stdout=reply(OTHER_IP)))
        self.assertEqual(d.read_ip_file(self.ip_file), OTHER_IP)
        self.assertIn(f"now {OTHER_IP} (was {PUBLIC_IP})", out)

    def test_failed_update_keeps_the_last_known_address(self):
        self.store([AUTO_URL])
        self.main(FakeRun(stdout=reply(PUBLIC_IP)))
        self.main(FakeRun(returncode=7))
        self.assertEqual(d.read_ip_file(self.ip_file), PUBLIC_IP)

    def test_nothing_configured_does_nothing(self):
        fake = FakeRun()
        self.main(fake)  # no URL file at all
        self.store([])
        self.main(fake)  # empty list
        self.assertEqual(fake.calls, [])
        self.assertFalse(os.path.exists(self.ip_file))


if __name__ == "__main__":
    unittest.main()
