from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from stock_radar.monitoring import MonitoringController


class MonitoringControllerTests(unittest.TestCase):
    def _wait_for_state(self, controller: MonitoringController, state: str) -> dict[str, object]:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            status = controller.status()
            if status["state"] == state:
                return status
            time.sleep(0.01)
        self.fail(f"Controller never reached {state}; status={controller.status()}")

    def test_is_disabled_by_default_and_does_not_run_collector(self) -> None:
        calls: list[bool] = []

        def runner(stop_event: threading.Event, set_state) -> int:
            calls.append(True)
            return 0

        with tempfile.TemporaryDirectory() as directory:
            controller = MonitoringController(Path(directory), runner=runner)
            self.assertEqual("DISABLED", controller.status()["state"])
            self.assertFalse(controller.status()["enabled"])
            self.assertEqual([], calls)
            saved = json.loads((Path(directory) / "data" / "monitoring-status.json").read_text(encoding="utf-8"))
            self.assertFalse(saved["enabled"])

    def test_start_and_stop_control_the_collector_lifecycle(self) -> None:
        started = threading.Event()
        stopped = threading.Event()

        def runner(stop_event: threading.Event, set_state) -> int:
            set_state("STREAMING")
            started.set()
            stop_event.wait(1.0)
            stopped.set()
            return 0

        with tempfile.TemporaryDirectory() as directory:
            controller = MonitoringController(Path(directory), runner=runner)
            controller.start()
            self.assertTrue(started.wait(1.0))
            self.assertTrue(controller.status()["enabled"])
            self.assertEqual("STREAMING", controller.status()["state"])
            controller.stop()
            self.assertTrue(stopped.wait(1.0))
            self._wait_for_state(controller, "DISABLED")
            self.assertFalse(controller.status()["enabled"])

    def test_failure_enters_reconnecting_until_explicit_stop(self) -> None:
        def runner(stop_event: threading.Event, set_state) -> int:
            raise RuntimeError("network unavailable")

        with tempfile.TemporaryDirectory() as directory:
            controller = MonitoringController(Path(directory), runner=runner)
            controller.start()
            status = self._wait_for_state(controller, "RECONNECTING")
            self.assertTrue(status["enabled"])
            self.assertIn("network unavailable", str(status["last_error"]))
            controller.stop()
            self._wait_for_state(controller, "DISABLED")
