"""Stateful, human-readable market events based only on completed minute bars."""
from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence
import json


def _n(bar: Mapping[str, Any], key: str) -> float: return float(bar[key])

def generate_market_events(bars: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    sell: dict[str, float] | None = None
    breakout: dict[str, float] | None = None
    for i, bar in enumerate(bars):
        close, opening, high, low, volume = (_n(bar, k) for k in ("close", "open", "high", "low", "volume"))
        if i < 20: continue
        prior = bars[i-20:i]
        base = float(median(_n(x, "volume") for x in prior))
        if base <= 0: continue
        ratio = volume / base
        ts = str(bar["timestamp"])
        def add(kind: str, title: str, summary: str, metrics: dict[str, Any]) -> None:
            events.append({"timestamp": ts, "type": kind, "title": title, "summary": summary, "metrics": metrics})

        # Active selling pressure has priority over any rebound/breakout evidence.
        if sell:
            if not sell.get("continued") and close < sell["low"]:
                add("SELL_PRESSURE_CONTINUES", "賣壓延續", f"收盤跌破賣壓 K 低點 {sell['low']:.1f}。", {"sell_low": sell["low"]})
                sell["continued"] = 1
            if i - int(sell["index"]) >= 3 and all(_n(x, "close") > sell["high"] for x in bars[i-2:i+1]):
                add("SELL_PRESSURE_RELEASED", "賣壓解除／重新轉強", f"連續 3 根收盤站回賣壓 K 高點 {sell['high']:.1f}。", {"sell_high": sell["high"]})
                sell = None
            continue

        range_ = high - low
        reversal = range_ > 0 and ratio >= 2 and close < opening and (close-low)/range_ <= .35
        if reversal:
            sell = {"high": high, "low": low, "index": float(i)}
            breakout = None
            add("SELL_PRESSURE_OCCURRED", "賣壓發生", "爆量收黑且收盤接近本根低點。", {"sell_high": high, "sell_low": low, "volume_ratio": round(ratio, 2)})
            continue

        if breakout:
            if not breakout.get("continued") and close > breakout["peak"] and close > breakout["level"]:
                add("BREAKOUT_CONTINUES", "突破延續", f"收盤再創突破後新高，仍高於突破價 {breakout['level']:.1f}。", {"breakout_level": breakout["level"], "close": close})
                breakout["continued"] = 1; breakout["peak"] = close
            if not breakout.get("failed") and i-int(breakout["index"]) >= 3 and all(_n(x,"close") < breakout["level"] for x in bars[i-2:i+1]):
                add("BREAKOUT_FAILED", "突破失敗", f"連續 3 根收盤低於突破價 {breakout['level']:.1f}。", {"breakout_level": breakout["level"]})
                breakout["failed"] = 1
            continue

        level = max(_n(x, "high") for x in prior)
        if close > level and ratio >= 2:
            breakout = {"level": level, "peak": close, "index": float(i)}
            add("BREAKOUT_OCCURRED", "突破發生", "收盤突破前 20 根高點，且出現放量。", {"breakout_level": level, "volume_ratio": round(ratio, 2)})
    return events

def build_market_event_session(replay: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema_version":"1.0", "symbol":str(replay["symbol"]), "market_date":str(replay["market_date"]), "timeframe":str(replay["timeframe"]), "events":generate_market_events(replay["bars"])}

def write_market_event_session(path: Path, session: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(session, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
