from __future__ import annotations

import unittest

from stock_radar.candidate_events import (
    ENTRY_CANDIDATE_TRIGGERED,
    EXIT_CANDIDATE_TRIGGERED,
    CandidateParameters,
    build_candidate_session,
    generate_candidate_events,
)


def bar(index: int, *, opening: float = 10, high: float = 11, low: float = 9, close: float = 10, volume: float = 100) -> dict[str, object]:
    return {"timestamp": f"2026-08-28T09:{index:02d}:00+08:00", "open": opening, "high": high, "low": low, "close": close, "volume": volume}


class CandidateEventTests(unittest.TestCase):
    rules = CandidateParameters(breakout_window=3, volume_multiple=2.0)

    def test_entry_requires_breakout_volume_and_vwap_alignment(self) -> None:
        bars = [bar(i, high=10, low=8, close=9, volume=100) for i in range(3)]
        bars.append(bar(3, opening=10, high=12, low=10, close=12, volume=250))
        events = generate_candidate_events(bars, self.rules)
        self.assertEqual([ENTRY_CANDIDATE_TRIGGERED], [event["kind"] for event in events])
        self.assertEqual(10.0, events[0]["invalidation_price"])
        self.assertGreater(events[0]["close"], events[0]["vwap"])

    def test_no_entry_when_close_is_not_above_vwap(self) -> None:
        bars = [bar(i, high=100, low=90, close=100, volume=100) for i in range(3)]
        bars.append(bar(3, opening=100, high=200, low=100, close=101, volume=250))
        self.assertEqual([], generate_candidate_events(bars, self.rules))

    def test_invalidation_is_emitted_once_after_entry(self) -> None:
        bars = [bar(i, high=10, low=8, close=9, volume=100) for i in range(3)]
        bars += [bar(3, opening=10, high=12, low=10, close=12, volume=250), bar(4, high=11, low=8, close=9, volume=100), bar(5, high=10, low=8, close=9, volume=100)]
        kinds = [event["kind"] for event in generate_candidate_events(bars, self.rules)]
        self.assertEqual([ENTRY_CANDIDATE_TRIGGERED, EXIT_CANDIDATE_TRIGGERED], kinds)

    def test_future_bar_does_not_change_previous_events(self) -> None:
        bars = [bar(i, high=10, low=8, close=9, volume=100) for i in range(3)]
        bars += [bar(3, opening=10, high=12, low=10, close=12, volume=250), bar(4, high=12, low=10, close=11, volume=100)]
        baseline = generate_candidate_events(bars, self.rules)
        changed = list(bars) + [bar(5, high=999, low=1, close=1, volume=99999)]
        self.assertEqual(baseline, generate_candidate_events(changed, self.rules)[:len(baseline)])

    def test_session_contract(self) -> None:
        bars = [bar(i, high=10, low=8, close=9, volume=100) for i in range(3)]
        bars.append(bar(3, opening=10, high=12, low=10, close=12, volume=250))
        replay = {"source": "replay", "symbol": "3324", "market_date": "2026-08-28", "timeframe": "1m", "bars": bars}
        session = build_candidate_session(replay, self.rules)
        self.assertEqual("1.0", session["schema_version"])
        self.assertEqual({"timestamp", "kind", "title", "summary", "close", "breakout_level", "invalidation_price", "volume_ratio", "vwap"}, set(session["events"][0]) if session["events"] else set())
