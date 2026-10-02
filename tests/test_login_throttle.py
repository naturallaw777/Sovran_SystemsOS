"""Tests for the Hub's login throttling.

These exercise the exact production implementation in
sovran_systemsos_web.security_helpers.LoginThrottle. The clock and the sleep are
injected, so the tests cover hours of lockout behaviour instantly.

No network access, no filesystem writes, no real delays.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_APP_PARENT = os.path.join(_REPO_ROOT, "app")
if _APP_PARENT not in sys.path:
    sys.path.insert(0, _APP_PARENT)

from sovran_systemsos_web.security_helpers import (  # noqa: E402
    LoginThrottle,
    LOGIN_FAIL_DELAY,
    LOGIN_FAIL_MAX_DELAY,
    LOGIN_FAIL_WINDOW,
    LOGIN_FAIL_MAX,
    LOGIN_LOCKOUT_SECONDS,
)


class FakeClock:
    """A clock that only moves when the test says so."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeSleeper:
    """Records the delays it was asked to apply instead of sleeping."""

    def __init__(self, clock):
        self.clock = clock
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)
        self.clock.advance(seconds)


def _make(**kwargs):
    clock = kwargs.pop("clock", None) or FakeClock()
    sleep = kwargs.pop("sleep", None) or FakeSleeper(clock)
    return LoginThrottle(clock=clock, sleep=sleep, **kwargs), clock, sleep


def _trip(throttle, ip="203.0.113.9"):
    """Fail LOGIN_FAIL_MAX times. The fake sleeper advances the clock for us."""
    for _ in range(LOGIN_FAIL_MAX):
        throttle.record_failure(ip)


class DelayRamp(unittest.TestCase):

    def test_delay_ramps_with_the_failure_count(self):
        throttle, _, _ = _make()
        self.assertEqual(throttle.delay_for(0), 0.0)
        self.assertEqual(throttle.delay_for(1), LOGIN_FAIL_DELAY)
        self.assertEqual(throttle.delay_for(3), LOGIN_FAIL_DELAY * 3)

    def test_delay_is_capped(self):
        # Unbounded ramping would let a single client park a thread-pool worker
        # for minutes at a time.
        throttle, _, _ = _make()
        self.assertLessEqual(throttle.delay_for(999), LOGIN_FAIL_MAX_DELAY)
        self.assertEqual(throttle.delay_for(999), LOGIN_FAIL_MAX_DELAY)

    def test_first_failure_is_not_delayed_much(self):
        throttle, _, sleep = _make()
        delay = throttle.record_failure("203.0.113.9")
        self.assertEqual(delay, LOGIN_FAIL_DELAY)
        self.assertEqual(sleep.calls, [LOGIN_FAIL_DELAY])


class Lockout(unittest.TestCase):

    def test_not_locked_out_initially(self):
        throttle, _, _ = _make()
        self.assertFalse(throttle.is_locked_out("203.0.113.9"))
        self.assertEqual(throttle.remaining_lockout("203.0.113.9"), 0.0)

    def test_reaching_the_limit_locks_the_address_out(self):
        throttle, _, _ = _make()
        _trip(throttle)
        self.assertTrue(throttle.is_locked_out("203.0.113.9"))

    def test_the_limit_is_reachable_inside_the_window(self):
        # Regression guard for the old 60s window: with a ramping delay it
        # takes ~80s to reach LOGIN_FAIL_MAX, so a 60s window expired the
        # earliest failures first and the lockout could never fire.
        throttle, clock, _ = _make()
        start = clock.now
        _trip(throttle)
        self.assertLess(clock.now - start, LOGIN_FAIL_WINDOW)
        self.assertEqual(throttle.failure_count("203.0.113.9"), LOGIN_FAIL_MAX)
        self.assertTrue(throttle.is_locked_out("203.0.113.9"))

    def test_one_failure_short_of_the_limit_is_not_a_lockout(self):
        throttle, _, _ = _make()
        for _ in range(LOGIN_FAIL_MAX - 1):
            throttle.record_failure("203.0.113.9")
        self.assertFalse(throttle.is_locked_out("203.0.113.9"))

    def test_lockout_expires(self):
        throttle, clock, _ = _make()
        _trip(throttle)
        self.assertTrue(throttle.is_locked_out("203.0.113.9"))
        clock.advance(LOGIN_LOCKOUT_SECONDS + 1)
        self.assertFalse(throttle.is_locked_out("203.0.113.9"))

    def test_remaining_lockout_counts_down(self):
        throttle, clock, _ = _make()
        _trip(throttle)
        full = throttle.remaining_lockout("203.0.113.9")
        # the final record_failure applied a delay, which the fake clock has
        # already advanced, so what is left is the lockout minus that delay
        self.assertAlmostEqual(full, LOGIN_LOCKOUT_SECONDS,
                               delta=LOGIN_FAIL_MAX_DELAY + 1.0)
        clock.advance(full / 2)
        self.assertLess(throttle.remaining_lockout("203.0.113.9"), full)
        self.assertGreater(throttle.remaining_lockout("203.0.113.9"), 0.0)

    def test_further_failures_while_locked_out_extend_it(self):
        throttle, clock, _ = _make()
        _trip(throttle)
        clock.advance(LOGIN_LOCKOUT_SECONDS - 1)
        throttle.record_failure("203.0.113.9")
        self.assertTrue(throttle.is_locked_out("203.0.113.9"))


class Isolation(unittest.TestCase):

    def test_one_address_does_not_lock_out_another(self):
        throttle, _, _ = _make()
        _trip(throttle, "203.0.113.9")
        self.assertTrue(throttle.is_locked_out("203.0.113.9"))
        self.assertFalse(throttle.is_locked_out("198.51.100.7"))

    def test_successful_login_clears_the_address(self):
        throttle, _, _ = _make()
        for _ in range(LOGIN_FAIL_MAX - 1):
            throttle.record_failure("203.0.113.9")
        throttle.clear("203.0.113.9")
        self.assertEqual(throttle.failure_count("203.0.113.9"), 0)
        self.assertFalse(throttle.is_locked_out("203.0.113.9"))

    def test_old_failures_age_out_of_the_window(self):
        throttle, clock, _ = _make()
        throttle.record_failure("203.0.113.9")
        clock.advance(LOGIN_FAIL_WINDOW + 1)
        self.assertEqual(throttle.failure_count("203.0.113.9"), 0)


class BoundedMemory(unittest.TestCase):

    def test_tracked_addresses_are_evicted(self):
        throttle, clock, _ = _make(max_tracked_ips=8)
        for i in range(64):
            throttle.record_failure(f"198.51.100.{i}")
        clock.advance(LOGIN_FAIL_WINDOW + LOGIN_LOCKOUT_SECONDS + 1)
        throttle.record_failure("203.0.113.9")
        self.assertLessEqual(throttle.tracked_addresses(), 8)

    def test_sleep_is_never_called_under_the_lock(self):
        # If the lock were held across the sleep, one slow client would stall
        # every other login — a self-inflicted DoS.
        throttle, clock, _ = _make()
        order = []

        def spy(seconds):
            order.append("sleep:start")
            clock.advance(seconds)
            order.append("sleep:end")

        throttle._sleep = spy
        throttle.record_failure("203.0.113.9")
        self.assertEqual(order, ["sleep:start", "sleep:end"])
        # A second address can still be recorded while the first is "sleeping".
        self.assertEqual(throttle.failure_count("198.51.100.7"), 0)


if __name__ == "__main__":
    unittest.main()
