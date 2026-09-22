from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stock_radar.live_collector import (
    LiveCandidateProcessor,
    normalise_bidask,
    normalise_kbar,
    normalise_tick,
)


def bar(index: int, *, close: float = 9, high: float = 10, low: float = 8, volume: float = 100) -> dict[str, object]:
    return {"timestamp": f"2026-08-28T09:{index:02d}:00+08:00", "open": 9, "high": high, "low": low, "close": close, "volume": volume, "amount": 0, "tick_count": 0}


class LiveCollectorTests(unittest.TestCase):
    def test_normalise_sdk_style_kbar(self) -> None:
        bar_ = normalise_kbar({"Code": "3324", "Date": "2026/08/28", "Time": "09:01:00.000000", "Open": 10, "High": 11, "Low": 9, "Close": 11, "Volume": 12, "Amount": 120, "TickCount": 3})
        self.assertEqual("2026-08-28T09:01:00+08:00", bar_["timestamp"])
        self.assertEqual(11.0, bar_["close"])
        self.assertEqual(3, bar_["tick_count"])

    def test_records_tick_executed_at_current_best_ask(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = LiveCandidateProcessor(Path(directory))
            processor.seed("3324", [bar(0)])
            processor.process_bidask(
                "3324",
                normalise_bidask({"Date": "2026/08/28", "Time": "09:01:00.000000", "BidPrice": [100], "AskPrice": [100.5]}),
            )
            signal = processor.process_tick(
                "3324",
                normalise_tick({"Date": "2026/08/28", "Time": "09:01:01.000000", "Close": 100.5, "Volume": 10, "TotalVolume": 99}),
            )
            self.assertIsNotNone(signal)
            self.assertEqual("AT_BEST_ASK", signal["classification"])
            self.assertEqual(10, signal["volume"])
            snapshot = json.loads((Path(directory) / "3324.json").read_text(encoding="utf-8"))
            self.assertEqual(1, len(snapshot["at_ask_prints"]))
            self.assertIsNone(snapshot["latest_tick"]["change_percent"])

    def test_normalise_tick_retains_price_change_percent(self) -> None:
        tick = normalise_tick({"Date": "2026/08/28", "Time": "09:01:01.000000", "Close": 100.5, "Volume": 10, "TotalVolume": 99, "PctChg": "10.0"})
        self.assertEqual(10.0, tick["change_percent"])

    def test_ignores_simulated_matching_tick(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = LiveCandidateProcessor(Path(directory))
            processor.seed("3324", [bar(0)])
            tick = normalise_tick(
                {"Date": "2026/08/28", "Time": "09:01:01.000000", "Close": 100.5, "Volume": 10, "TotalVolume": 99, "Simtrade": True}
            )

            self.assertTrue(tick["simtrade"])
            self.assertIsNone(processor.process_tick("3324", tick))
            snapshot = json.loads((Path(directory) / "3324.json").read_text(encoding="utf-8"))
            self.assertIsNone(snapshot["latest_tick"])
            self.assertEqual([], snapshot["at_ask_prints"])
            self.assertEqual([], snapshot["at_bid_prints"])

    def test_tick_before_failed_kbar_bootstrap_writes_safe_snapshot(self) -> None:
        """A single unavailable KBar request must not stop the whole feed."""
        with tempfile.TemporaryDirectory() as directory:
            processor = LiveCandidateProcessor(Path(directory))
            processor.process_tick(
                "2455",
                normalise_tick({"Date": "2026/08/28", "Time": "09:01:01.000000", "Close": 100.5, "Volume": 10, "TotalVolume": 99}),
            )
            snapshot = json.loads((Path(directory) / "2455.json").read_text(encoding="utf-8"))
            self.assertEqual(0, snapshot["bar_count"])
            self.assertIsNone(snapshot["latest_bar"])
            self.assertEqual("2026-08-28T09:01:01.000000+08:00", snapshot["latest_tick"]["timestamp"])
            self.assertIn("updated_at", snapshot)

    def test_ignores_tick_between_best_bid_and_ask(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = LiveCandidateProcessor(Path(directory))
            processor.seed("3324", [bar(0)])
            processor.process_bidask(
                "3324",
                normalise_bidask({"Date": "2026/08/28", "Time": "09:01:00.000000", "BidPrice": [100], "AskPrice": [100.5]}),
            )
            signal = processor.process_tick(
                "3324",
                normalise_tick({"Date": "2026/08/28", "Time": "09:01:01.000000", "Close": 100.25, "Volume": 10, "TotalVolume": 99}),
            )
            self.assertIsNone(signal)

    def test_records_tick_executed_at_current_best_bid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = LiveCandidateProcessor(Path(directory))
            processor.seed("3324", [bar(0)])
            processor.process_bidask(
                "3324",
                normalise_bidask({"Date": "2026/08/28", "Time": "09:01:00.000000", "BidPrice": [100], "AskPrice": [100.5]}),
            )
            signal = processor.process_tick(
                "3324",
                normalise_tick({"Date": "2026/08/28", "Time": "09:01:01.000000", "Close": 100, "Volume": 12, "TotalVolume": 99}),
            )
            self.assertIsNotNone(signal)
            self.assertEqual("AT_BEST_BID", signal["classification"])
            snapshot = json.loads((Path(directory) / "3324.json").read_text(encoding="utf-8"))
            self.assertEqual(1, len(snapshot["at_bid_prints"]))

    def test_processor_writes_snapshot_and_dispatches_new_event_once(self) -> None:
        delivered: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as directory:
            processor = LiveCandidateProcessor(Path(directory), lambda symbol, event: delivered.append((symbol, str(event["kind"]))) or True)
            for index in range(20):
                processor.process("3324", bar(index))
            events = processor.process("3324", bar(20, close=12, high=12, low=10, volume=250))
            self.assertEqual([], events)
            self.assertEqual([], delivered)
            snapshot = json.loads((Path(directory) / "3324.json").read_text(encoding="utf-8"))
            self.assertEqual(21, snapshot["bar_count"])
            self.assertTrue(snapshot["pressure_gauge"]["available"])


    def test_seed_uses_history_without_replaying_toasts(self) -> None:
        delivered: list[tuple[str, str]] = []
        with tempfile.TemporaryDirectory() as directory:
            processor = LiveCandidateProcessor(
                Path(directory),
                lambda symbol, event: delivered.append((symbol, str(event["kind"]))) or True,
            )
            bars = [bar(index) for index in range(20)]
            bars.append(bar(20, close=12, high=12, low=10, volume=250))
            processor.seed("3324", bars)
            self.assertEqual([], delivered)
            snapshot = json.loads((Path(directory) / "3324.json").read_text(encoding="utf-8"))
            self.assertEqual(21, snapshot["bar_count"])
            self.assertTrue(snapshot["pressure_gauge"]["available"])

    def test_order_flow_power_tracking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            processor = LiveCandidateProcessor(Path(directory))
            processor.custom_thresholds["3324"] = 10
            processor.seed("3324", [bar(0)])
            processor.process_bidask(
                "3324",
                normalise_bidask({"Date": "2026/08/28", "Time": "09:01:00.000000", "BidPrice": [100.0], "AskPrice": [101.0]}),
            )
            # Major buy: vol 15 >= 10 at ask 101.0
            processor.process_tick(
                "3324",
                normalise_tick({"Date": "2026/08/28", "Time": "09:01:01.000000", "Close": 101.0, "Volume": 15, "TotalVolume": 15}),
            )
            # Retail sell: vol 3 < 10 at bid 100.0
            processor.process_tick(
                "3324",
                normalise_tick({"Date": "2026/08/28", "Time": "09:01:05.000000", "Close": 100.0, "Volume": 3, "TotalVolume": 18}),
            )
            snapshot = json.loads((Path(directory) / "3324.json").read_text(encoding="utf-8"))
            power = snapshot.get("order_flow_power")
            self.assertIsNotNone(power)
            self.assertEqual(15, power["major_net"])
            self.assertEqual(101.0, power["major_vwap"])
            self.assertEqual(-3, power["retail_net"])
            self.assertEqual(100.0, power["retail_vwap"])
            self.assertEqual(10, power["threshold"])
            self.assertEqual(1, len(power["series"]))
            self.assertEqual("09:01", power["series"][0]["t"])
            self.assertEqual(15, power["series"][0]["m"])
            self.assertEqual(-3, power["series"][0]["r"])
