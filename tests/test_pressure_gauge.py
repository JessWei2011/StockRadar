from __future__ import annotations

import unittest

from stock_radar.pressure_gauge import (
    FALLING,
    RISING,
    STABLE,
    PressureGaugeParameters,
    build_pressure_gauge_session,
    generate_pressure_readings,
)


def bar(index: int, *, opening: float = 10, high: float = 12, low: float = 8, close: float = 10, volume: float = 100) -> dict[str, object]:
    return {
        "timestamp": f"2026-08-28T09:{index:02d}:00+08:00",
        "open": opening,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


class PressureGaugeTests(unittest.TestCase):
    rules = PressureGaugeParameters(volume_window=3)

    def test_initial_bars_are_safe_readings(self) -> None:
        readings = generate_pressure_readings([bar(i) for i in range(3)], self.rules)
        self.assertEqual(3, len(readings))
        self.assertTrue(all(not reading["available"] for reading in readings))
        self.assertTrue(all(reading["level"] == 0.0 for reading in readings))

    def test_high_volume_close_high_pushes_up(self) -> None:
        bars = [bar(i) for i in range(3)] + [bar(3, high=13, low=9, close=13, volume=240)]
        reading = generate_pressure_readings(bars, self.rules)[-1]
        self.assertTrue(reading["available"])
        self.assertEqual(2.4, reading["volume_ratio"])
        self.assertEqual(1.0, reading["price_pressure"])
        self.assertEqual(RISING, reading["direction"])
        self.assertGreater(reading["level"], 0)

    def test_high_volume_close_low_pushes_down(self) -> None:
        bars = [bar(i) for i in range(3)] + [bar(3, opening=12, high=13, low=9, close=9, volume=250)]
        reading = generate_pressure_readings(bars, self.rules)[-1]
        self.assertEqual(FALLING, reading["direction"])
        self.assertLess(reading["level"], 0)

    def test_low_volume_neutral_bar_returns_slowly_to_center(self) -> None:
        bars = [bar(i) for i in range(3)]
        bars.append(bar(3, high=13, low=9, close=13, volume=20))
        bars.append(bar(4, opening=10, high=12, low=8, close=10, volume=80))
        reading = generate_pressure_readings(bars, self.rules)[-1]
        self.assertEqual(STABLE, reading["direction"])
        self.assertGreater(reading["level"], 0)

    def test_zero_range_marks_position_unavailable_without_crashing(self) -> None:
        bars = [bar(i) for i in range(3)] + [bar(3, high=10, low=10, close=10, volume=300)]
        reading = generate_pressure_readings(bars, self.rules)[-1]
        self.assertTrue(reading["available"])
        self.assertIsNone(reading["close_position"])
        self.assertEqual(0.0, reading["price_pressure"])

    def test_zero_baseline_is_safe(self) -> None:
        bars = [bar(i, volume=0) for i in range(3)] + [bar(3, volume=300)]
        reading = generate_pressure_readings(bars, self.rules)[-1]
        self.assertFalse(reading["available"])
        self.assertIsNone(reading["volume_ratio"])

    def test_level_is_bounded(self) -> None:
        bars = [bar(i) for i in range(3)]
        bars.extend(bar(i, high=13, low=9, close=13, volume=10000) for i in range(3, 25))
        readings = generate_pressure_readings(bars, self.rules)
        self.assertTrue(all(-100 <= reading["level"] <= 100 for reading in readings))

    def test_changing_future_bar_does_not_change_prior_readings(self) -> None:
        bars = [bar(i, volume=100 + i) for i in range(8)]
        baseline = generate_pressure_readings(bars, self.rules)
        changed = list(bars)
        changed[-1] = bar(7, high=999, low=1, close=999, volume=999999)
        altered = generate_pressure_readings(changed, self.rules)
        self.assertEqual(baseline[:-1], altered[:-1])

    def test_session_contract(self) -> None:
        bars = [bar(i) for i in range(4)]
        session = build_pressure_gauge_session({"source": "replay", "symbol": "3324", "market_date": "2026-08-28", "timeframe": "1m", "bars": bars}, self.rules)
        self.assertEqual("1.0", session["schema_version"])
        self.assertEqual(4, len(session["readings"]))
        self.assertEqual({"timestamp", "available", "level", "delta", "direction", "volume_ratio", "close_position", "price_pressure", "volume_pressure", "summary"}, set(session["readings"][-1]))
