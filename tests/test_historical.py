from datetime import date, datetime
from types import SimpleNamespace
import unittest

from stock_radar.historical import normalise_kbars


class HistoricalNormalisationTests(unittest.TestCase):
    def test_filters_and_sorts_target_day(self) -> None:
        raw = {
            "ts": [
                datetime(2026, 8, 29, 9, 0),
                datetime(2026, 8, 28, 9, 1),
                datetime(2026, 8, 28, 9, 0),
            ],
            "Open": [3, 2, 1],
            "High": [3, 2, 1],
            "Low": [3, 2, 1],
            "Close": [3, 2, 1],
            "Volume": [3, 2, 1],
            "Amount": [30, 20, 10],
            "TickCount": [3, 2, 1],
        }

        bars = normalise_kbars(raw, "3324", date(2026, 8, 28))

        self.assertEqual([bar.close for bar in bars], [1.0, 2.0])
        self.assertTrue(bars[0].timestamp.endswith("+08:00"))

    def test_rejects_empty_target_day(self) -> None:
        raw = {
            "ts": [datetime(2026, 8, 29, 9, 0)],
            "Open": [1], "High": [1], "Low": [1], "Close": [1],
            "Volume": [1], "Amount": [1], "TickCount": [1],
        }
        with self.assertRaises(ValueError):
            normalise_kbars(raw, "3324", date(2026, 8, 28))

    def test_accepts_sdk_style_object(self) -> None:
        raw = SimpleNamespace(
            ts=[datetime(2026, 8, 28, 9, 0)],
            Open=[1], High=[1], Low=[1], Close=[1],
            Volume=[1], Amount=[1], TickCount=[1],
        )
        bars = normalise_kbars(raw, "3324", date(2026, 8, 28))
        self.assertEqual(bars[0].close, 1.0)

    def test_missing_tick_count_is_recorded_as_zero(self) -> None:
        raw = {
            "ts": [datetime(2026, 8, 28, 9, 0)],
            "Open": [1], "High": [1], "Low": [1], "Close": [1],
            "Volume": [1], "Amount": [1],
        }
        bars = normalise_kbars(raw, "3324", date(2026, 8, 28))
        self.assertEqual(bars[0].tick_count, 0)

    def test_accepts_unix_nanosecond_timestamp(self) -> None:
        raw = {
            "ts": [1787907660000000000],
            "Open": [1], "High": [1], "Low": [1], "Close": [1],
            "Volume": [1], "Amount": [1],
        }
        bars = normalise_kbars(raw, "3324", date(2026, 8, 28))
        self.assertEqual(bars[0].timestamp, "2026-08-28T09:01:00+08:00")
