"""Tests for Taiwan stocks dictionary and contract lookup."""

from __future__ import annotations

import unittest

from stock_radar.tw_stocks import fetch_online_stock_info, lookup_stock_name, query_shioaji_contract


class TWStocksTests(unittest.TestCase):
    def test_lookup_stock_name_known(self) -> None:
        self.assertEqual("台積電", lookup_stock_name("2330"))
        self.assertEqual("鴻海", lookup_stock_name("2317"))
        self.assertEqual("雙鴻", lookup_stock_name("3324"))

    def test_lookup_stock_name_online(self) -> None:
        # 2481 and 6147 are dynamically resolved
        name_2481 = lookup_stock_name("2481")
        self.assertIn(name_2481, ["強茂", "個股 2481"])
        name_6147 = lookup_stock_name("6147")
        self.assertIn(name_6147, ["頎邦", "個股 6147"])

    def test_fetch_online_stock_info(self) -> None:
        info = fetch_online_stock_info("2481")
        if info:
            self.assertEqual("2481", info["symbol"])
            self.assertEqual("強茂", info["name"])
            self.assertGreater(info["reference"], 0)

    def test_lookup_stock_name_fallback(self) -> None:
        self.assertEqual("個股 9999", lookup_stock_name("9999"))

    def test_query_shioaji_contract_none_safe(self) -> None:
        self.assertIsNone(query_shioaji_contract(None, "2330"))