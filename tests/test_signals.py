from __future__ import annotations

import unittest

from stock_radar.signals import SignalParameters, build_signal_session, generate_signal_events


def bar(index: int, *, opening: float = 10, high: float = 11, low: float = 9, close: float = 10, volume: int = 100) -> dict[str, object]:
    return {
        "timestamp": f"2026-08-28T09:{index:02d}:00+08:00",
        "open": opening,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def signals(events: list[dict[str, object]]) -> list[str]:
    return [str(event["signal"]) for event in events]


class SignalRuleTests(unittest.TestCase):
    def test_rising_structure_triggers(self) -> None:
        bars = [bar(0, close=10)] + [bar(i, high=11 + i, low=9 + i, close=10 + i) for i in range(1, 6)]
        self.assertIn("RISING_STRUCTURE", signals(generate_signal_events(bars)))

    def test_rising_structure_does_not_trigger_when_low_falls(self) -> None:
        bars = [bar(0, close=10)] + [bar(i, high=11 + i, low=9 + i, close=10 + i) for i in range(1, 6)]
        bars[3]["low"] = 1
        self.assertNotIn("RISING_STRUCTURE", signals(generate_signal_events(bars)))

    def test_rising_structure_needs_history(self) -> None:
        bars = [bar(i, high=11 + i, low=9 + i, close=10 + i) for i in range(5)]
        self.assertNotIn("RISING_STRUCTURE", signals(generate_signal_events(bars)))

    def test_volume_breakout_triggers(self) -> None:
        bars = [bar(i, high=10, volume=100) for i in range(20)]
        bars.append(bar(20, high=12, close=11, volume=250))
        self.assertIn("VOLUME_BREAKOUT", signals(generate_signal_events(bars)))

    def test_volume_breakout_requires_price_and_volume(self) -> None:
        bars = [bar(i, high=10, volume=100) for i in range(20)]
        bars.append(bar(20, high=11, close=10, volume=250))
        self.assertNotIn("VOLUME_BREAKOUT", signals(generate_signal_events(bars)))

    def test_volume_breakout_needs_history(self) -> None:
        bars = [bar(i, high=10, volume=100) for i in range(20)]
        self.assertNotIn("VOLUME_BREAKOUT", signals(generate_signal_events(bars)))

    def test_high_volume_reversal_triggers(self) -> None:
        bars = [bar(i, volume=100) for i in range(20)]
        bars.append(bar(20, opening=12, high=13, low=10, close=10.5, volume=250))
        self.assertIn("HIGH_VOLUME_REVERSAL", signals(generate_signal_events(bars)))

    def test_high_volume_reversal_rejects_green_or_high_close(self) -> None:
        bars = [bar(i, volume=100) for i in range(20)]
        bars.append(bar(20, opening=10, high=13, low=10, close=12.5, volume=250))
        self.assertNotIn("HIGH_VOLUME_REVERSAL", signals(generate_signal_events(bars)))

    def test_high_volume_reversal_handles_insufficient_and_zero_range(self) -> None:
        insufficient = [bar(i, volume=100) for i in range(20)]
        self.assertNotIn("HIGH_VOLUME_REVERSAL", signals(generate_signal_events(insufficient)))
        zero_range = insufficient + [bar(20, opening=12, high=10, low=10, close=9, volume=250)]
        self.assertNotIn("HIGH_VOLUME_REVERSAL", signals(generate_signal_events(zero_range)))

    def test_session_contract_includes_source_and_parameters(self) -> None:
        replay = {
            "symbol": "3324", "market_date": "2026-08-28", "timeframe": "1m",
            "source": "shioaji_historical_kbars", "bars": [bar(0)],
        }
        session = build_signal_session(replay, SignalParameters())
        self.assertEqual("1.0", session["schema_version"])
        self.assertEqual("shioaji_historical_kbars", session["source_replay"])
        self.assertEqual(20, session["parameters"]["breakout_window"])
