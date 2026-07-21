"""Concurrency tests for the autonomous scheduler."""
from __future__ import annotations

import threading
import time
import unittest

from agents.scheduler import SchedulerAgent


class SchedulerAgentTests(unittest.TestCase):
    def test_manual_triggers_are_claimed_before_thread_start(self) -> None:
        scheduler = SchedulerAgent()
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def job() -> dict:
            calls.append("run")
            entered.set()
            release.wait(timeout=2)
            return {"ok": True}

        scheduler.register("scan", "fixture", 1, job)
        first = scheduler.run_now("scan")
        self.assertTrue(first["ok"])
        self.assertTrue(entered.wait(timeout=1))

        second = scheduler.run_now("scan")
        self.assertFalse(second["ok"])
        self.assertEqual("Already running", second["error"])
        self.assertEqual(["run"], calls)

        release.set()
        deadline = time.monotonic() + 2
        while scheduler.status()["jobs"][0]["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(scheduler.status()["jobs"][0]["running"])
        self.assertEqual(1, scheduler.status()["jobs"][0]["runs_ok"])

    def test_duplicate_registration_is_idempotent(self) -> None:
        scheduler = SchedulerAgent()
        scheduler.register("scan", "first", 1, lambda: {})
        scheduler.register("scan", "duplicate", 1, lambda: {})
        self.assertEqual(1, len(scheduler.status()["jobs"]))


if __name__ == "__main__":
    unittest.main()
