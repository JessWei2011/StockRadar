"""Taiwan Stock Directory and Contract Resolver for StockRadar."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

# Standard Top / Popular Taiwan Stock Names dictionary
TW_POPULAR_STOCKS: Dict[str, str] = {
    "2330": "台積電",
    "2317": "鴻海",
    "2454": "聯發科",
    "2382": "廣達",
    "2308": "台達電",
    "3231": "緯創",
    "2357": "華碩",
    "2376": "技嘉",
    "6669": "緯穎",
    "2356": "英業達",
    "3017": "奇鋐",
    "3324": "雙鴻",
    "2455": "全新",
    "3450": "聯鈞",
    "4958": "臻鼎-KY",
    "3406": "玉晶光",
    "3008": "大立光",
    "3037": "欣興",
    "8046": "南電",
    "3189": "景碩",
    "3661": "世芯-KY",
    "3443": "創意",
    "3035": "智原",
    "2603": "長榮",
    "2609": "陽明",
    "2615": "萬海",
    "2618": "長榮航",
    "2610": "華航",
    "2881": "富邦金",
    "2882": "國泰金",
    "2891": "中信金",
    "2886": "兆豐金",
    "2002": "中鋼",
    "1301": "台塑",
    "1303": "南亞",
    "6446": "藥華藥",
    "4743": "合一",
    "6488": "環球晶",
    "5483": "中美晶",
    "3529": "力旺",
    "6533": "晶心科",
}


def lookup_stock_name(symbol: str) -> str:
    """Return Chinese stock name if known, else return symbol."""
    if symbol in TW_POPULAR_STOCKS:
        return TW_POPULAR_STOCKS[symbol]
    # Attempt online fetch for any symbol
    info = fetch_online_stock_info(symbol)
    if info and info.get("name"):
        return info["name"]
    return f"個股 {symbol}"


def fetch_online_stock_info(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch real-time stock name and reference price via TWSE/TPEx MIS API."""
    import urllib.request

    clean_sym = symbol.strip()
    if not clean_sym:
        return None

    # Query both TSE and OTC channels in one call
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{clean_sym}.tw|otc_{clean_sym}.tw"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw)
            msg_array = data.get("msgArray", [])
            for item in msg_array:
                code = item.get("c")
                name = item.get("n")
                if code == clean_sym and name:
                    ref = 0.0
                    limit_up = 0.0
                    limit_down = 0.0
                    try:
                        ref = float(item.get("y", 0.0) or 0.0)
                    except (ValueError, TypeError):
                        pass
                    try:
                        limit_up = float(item.get("u", 0.0) or 0.0)
                    except (ValueError, TypeError):
                        pass
                    try:
                        limit_down = float(item.get("w", 0.0) or 0.0)
                    except (ValueError, TypeError):
                        pass

                    # Cache into TW_POPULAR_STOCKS for fast repeated lookups
                    TW_POPULAR_STOCKS[clean_sym] = name

                    return {
                        "symbol": clean_sym,
                        "name": name,
                        "reference": ref,
                        "limit_up": limit_up,
                        "limit_down": limit_down,
                    }
    except Exception:
        pass

    return None


def query_shioaji_contract(api: Any, symbol: str) -> Optional[Dict[str, Any]]:
    """Query Shioaji API Contracts for stock details (name, reference price, limit prices)."""
    if api is None or not hasattr(api, "Contracts") or not hasattr(api.Contracts, "Stocks"):
        return None
    try:
        # Check TSE first then OTC
        for market in ["TSE", "OTC"]:
            market_stocks = getattr(api.Contracts.Stocks, market, None)
            if market_stocks and symbol in market_stocks:
                contract = market_stocks[symbol]
                name = getattr(contract, "name", "") or lookup_stock_name(symbol)
                ref_price = float(getattr(contract, "reference", 0.0) or 0.0)
                limit_up = float(getattr(contract, "limit_up", 0.0) or 0.0)
                limit_down = float(getattr(contract, "limit_down", 0.0) or 0.0)
                return {
                    "symbol": symbol,
                    "name": name,
                    "market": market,
                    "reference": ref_price,
                    "limit_up": limit_up,
                    "limit_down": limit_down,
                }
    except Exception:
        pass
    return None