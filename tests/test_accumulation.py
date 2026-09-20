from __future__ import annotations

import unittest

from stock_radar.accumulation import detect_potential_accumulation


def bar(
    minute: int,
    *,
    low: float = 95,
    high: float = 105,
    close: float | None = None,
    volume: int = 0,
) -> dict[str, object]:
    result: dict[str, object] = {
        "timestamp": f"2026-08-28T09:{minute:02d}:00+08:00",
        "low": low,
        "high": high,
        "volume": volume,
    }
    if close is not None:
        result["close"] = close
    return result


def print_(second: int, volume: int, *, price: float | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "timestamp": f"2026-08-28T09:59:{second:02d}+08:00",
        "volume": volume,
    }
    if price is not None:
        result["price"] = price
    return result


class AccumulationTests(unittest.TestCase):
    def test_low_zone_repeated_buying_that_holds_is_active(self) -> None:
        bars = [bar(index, low=90, high=110) for index in range(60)]
        result = detect_potential_accumulation(
            bars,
            [print_(10, 12), print_(20, 15), print_(30, 18)],
            [print_(40, 2)],
            {"timestamp": "2026-08-28T09:59:50+08:00", "price": 95},
        )
        self.assertTrue(result["active"])
        self.assertEqual(3, result["large_buy_count"])

    def test_high_zone_is_not_accumulation(self) -> None:
        bars = [bar(index, low=90, high=110) for index in range(60)]
        result = detect_potential_accumulation(
            bars,
            [print_(10, 12), print_(20, 15), print_(30, 18)],
            [],
            {"timestamp": "2026-08-28T09:59:50+08:00", "price": 108},
        )
        self.assertFalse(result["active"])
        self.assertFalse(result["conditions"]["low_zone"])

    def test_low_zone_with_a_large_buy_is_watching_before_confirmation(self) -> None:
        bars = [bar(index, low=90, high=110) for index in range(60)]
        result = detect_potential_accumulation(
            bars,
            [print_(10, 12)],
            [print_(20, 20)],
            {"timestamp": "2026-08-28T09:59:50+08:00", "price": 95},
        )
        self.assertTrue(result["watching"])
        self.assertFalse(result["active"])

    def test_heavy_selling_that_cannot_break_support_is_absorption(self) -> None:
        bars = [bar(index, low=94.8, high=110) for index in range(60)]
        result = detect_potential_accumulation(
            bars,
            [print_(10, 5, price=95.0)],
            [print_(20, 20, price=94.9), print_(30, 15, price=94.9)],
            {"timestamp": "2026-08-28T09:59:50+08:00", "price": 94.9},
        )
        self.assertTrue(result["active"])
        self.assertEqual("ABSORPTION", result["stage"])
        self.assertTrue(result["conditions"]["sell_absorbed"])

    def test_heavy_selling_that_breaks_support_is_not_absorption(self) -> None:
        bars = [bar(index, low=94.8, high=110) for index in range(60)]
        result = detect_potential_accumulation(
            bars,
            [print_(10, 5, price=95.0)],
            [print_(20, 20, price=94.7), print_(30, 15, price=94.6)],
            {"timestamp": "2026-08-28T09:59:50+08:00", "price": 94.5},
        )
        self.assertFalse(result["active"])
        self.assertFalse(result["conditions"]["holds"])
        self.assertFalse(result["conditions"]["sell_absorbed"])

    def test_small_selling_without_large_repeated_prints_is_not_absorption(self) -> None:
        bars = [bar(index, low=94.8, high=110) for index in range(60)]
        result = detect_potential_accumulation(
            bars,
            [],
            [print_(20, 1, price=94.9)],
            {"timestamp": "2026-08-28T09:59:50+08:00", "price": 94.9},
        )
        self.assertFalse(result["active"])
        self.assertFalse(result["conditions"]["sell_absorbed"])

    def test_breakout_above_vwap_with_expanding_volume_confirms_attack(self) -> None:
        bars = [bar(index, low=90, high=100, close=95, volume=100) for index in range(59)]
        bars.append(bar(59, low=95, high=100, close=99, volume=200))
        result = detect_potential_accumulation(
            bars,
            [print_(10, 20, price=100.5), print_(20, 20, price=101.0)],
            [print_(30, 2, price=100.8)],
            {"timestamp": "2026-08-28T09:59:50+08:00", "price": 101.0},
        )
        self.assertTrue(result["active"])
        self.assertEqual("ATTACK_CONFIRMED", result["stage"])
        self.assertTrue(result["conditions"]["above_vwap"])
        self.assertTrue(result["conditions"]["breakout"])
        self.assertTrue(result["conditions"]["volume_expanding"])
