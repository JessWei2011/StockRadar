import unittest

from stock_radar.replay import ReplayController


def session() -> dict:
    return {
        "schema_version": "1.0",
        "symbol": "3324",
        "market_date": "2026-08-28",
        "timeframe": "1m",
        "source": "test",
        "bars": [{"timestamp": "2026-08-28T09:00:00+08:00"}, {"timestamp": "2026-08-28T09:01:00+08:00"}],
    }


class ReplayControllerTests(unittest.TestCase):
    def test_speed_mapping(self) -> None:
        controller = ReplayController(session(), speed=5)
        self.assertEqual(controller.delay_seconds, 12)
        controller.set_speed(20)
        self.assertEqual(controller.delay_seconds, 3)

    def test_pause_and_resume(self) -> None:
        controller = ReplayController(session())
        controller.pause()
        self.assertIsNone(controller.next_bar())
        controller.resume()
        self.assertEqual(controller.next_bar()["timestamp"], "2026-08-28T09:00:00+08:00")
        self.assertEqual(controller.progress, (1, 2))

    def test_rejects_unsupported_speed(self) -> None:
        with self.assertRaises(ValueError):
            ReplayController(session(), speed=2)
