from __future__ import annotations

import unittest

from stock_radar.market_context import (
    POSTURE_BEARISH,
    POSTURE_BULLISH,
    POSTURE_CONFLICT,
    MarketContextParameters,
    build_market_context_session,
    generate_market_contexts,
)


def bar(
    index: int,
    *,
    opening: float = 10,
    high: float = 12,
    low: float = 8,
    close: float = 10,
    volume: float = 100,
) -> dict[str, object]:
    return {
        "timestamp": f"2026-08-28T09:{index:02d}:00+08:00",
        "open": opening,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def event(index: int) -> dict[str, object]:
    return {
        "timestamp": f"2026-08-28T09:{index:02d}:00+08:00",
        "type": "BREAKOUT_OCCURRED",
        "metrics": {"breakout_level": 12},
    }


class MarketContextTests(unittest.TestCase):
    rules = MarketContextParameters(volume_window=3)

    def test_bullish_context_uses_only_prior_completed_bars(self) -> None:
        bars = [bar(i, volume=100) for i in range(3)]
        bars.append(bar(3, opening=10, high=13, low=9, close=13, volume=300))

        contexts = generate_market_contexts(bars, [event(3)], self.rules)

        self.assertEqual(1, len(contexts))
        self.assertEqual(POSTURE_BULLISH, contexts[0]["posture"])
        self.assertEqual(3.0, contexts[0]["volume_ratio"])
        self.assertEqual(1.0, contexts[0]["close_position"])
        self.assertEqual(12.0, contexts[0]["key_high"])

    def test_bearish_context(self) -> None:
        bars = [bar(i, volume=100) for i in range(3)]
        bars.append(bar(3, opening=12, high=13, low=9, close=9.5, volume=300))

        contexts = generate_market_contexts(bars, [event(3)], self.rules)

        self.assertEqual(POSTURE_BEARISH, contexts[0]["posture"])

    def test_conflict_context(self) -> None:
        bars = [bar(i, volume=100) for i in range(3)]
        bars.append(bar(3, opening=12, high=13, low=9, close=11, volume=300))

        contexts = generate_market_contexts(bars, [event(3)], self.rules)

        self.assertEqual(POSTURE_CONFLICT, contexts[0]["posture"])

    def test_insufficient_history_and_zero_baseline_are_omitted(self) -> None:
        insufficient = [bar(i, volume=100) for i in range(3)]
        self.assertEqual([], generate_market_contexts(insufficient, [event(2)], self.rules))

        zero_baseline = [bar(i, volume=0) for i in range(3)] + [bar(3, volume=300)]
        self.assertEqual([], generate_market_contexts(zero_baseline, [event(3)], self.rules))

    def test_zero_range_is_retained_as_conflict_with_no_close_position(self) -> None:
        bars = [bar(i, volume=100) for i in range(3)]
        bars.append(bar(3, opening=10, high=10, low=10, close=10, volume=300))

        contexts = generate_market_contexts(bars, [event(3)], self.rules)

        self.assertEqual(POSTURE_CONFLICT, contexts[0]["posture"])
        self.assertIsNone(contexts[0]["close_position"])

    def test_session_contract(self) -> None:
        bars = [bar(i, volume=100) for i in range(3)]
        bars.append(bar(3, opening=10, high=13, low=9, close=13, volume=300))
        replay = {
            "symbol": "3324",
            "market_date": "2026-08-28",
            "timeframe": "1m",
            "source": "shioaji_historical_kbars",
            "bars": bars,
        }

        session = build_market_context_session(replay, [event(3)], self.rules)

        self.assertEqual("1.0", session["schema_version"])
        self.assertEqual("shioaji_historical_kbars", session["source_replay"])
        self.assertEqual(3, session["parameters"]["volume_window"])
        self.assertEqual(
            {
                "timestamp", "event_type", "event_title", "posture", "title", "summary",
                "volume_ratio", "close_position", "key_high", "key_low",
            },
            set(session["contexts"][0]),
        )
