"""Multi-symbol real historical replay engine pushing to data/live."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import random
import time
from typing import Any, Mapping

from .accumulation import detect_potential_accumulation
from .pressure_gauge import generate_pressure_readings

SYMBOLS = ["2455", "3324", "3406", "3450", "4958"]


def load_sessions(replays_dir: Path, market_date: str) -> dict[str, list[dict[str, Any]]]:
    sessions = {}
    for sym in SYMBOLS:
        p = replays_dir / f"{sym}_{market_date}_1m.json"
        if not p.is_file():
            raise FileNotFoundError(f"找不到 {sym} 的回放檔案：{p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        sessions[sym] = data.get("bars", [])
    return sessions


REFERENCES = {
    "2455": 477.0,
    "3324": 1250.0,
    "3406": 1005.0,
    "3450": 646.0,
    "4958": 500.0,
}


def run_replay(market_date: str = "2026-09-01", speed: int = 5) -> None:
    root = Path(__file__).resolve().parents[2]
    replays_dir = root / "data" / "replays"
    live_dir = root / "data" / "live"
    live_dir.mkdir(parents=True, exist_ok=True)

    sessions = load_sessions(replays_dir, market_date)
    bar_counts = [len(bars) for bars in sessions.values()]
    total_bars = min(bar_counts)

    print(f"🎬 啟動五檔真實數據回放：日期 {market_date} | 總計 {total_bars} 分鐘 | 速度 {speed}x")

    interval = max(0.05, 60.0 / speed)
    history: dict[str, list[dict[str, Any]]] = {sym: [] for sym in SYMBOLS}
    ask_prints: dict[str, list[dict[str, Any]]] = {sym: [] for sym in SYMBOLS}
    bid_prints: dict[str, list[dict[str, Any]]] = {sym: [] for sym in SYMBOLS}
    total_volumes: dict[str, float] = {sym: 0.0 for sym in SYMBOLS}

    for idx in range(total_bars):
        current_time_str = ""

        for sym in SYMBOLS:
            bar = sessions[sym][idx]
            history[sym].append(bar)
            current_time_str = bar["timestamp"]
            ref_price = REFERENCES.get(sym, float(sessions[sym][0]["open"]))
            close_price = float(bar["close"])
            bar_vol = float(bar["volume"])
            total_volumes[sym] += bar_vol

            # Synthesize realistic trades within this minute bar
            # Bullish candle -> more ask prints; Bearish candle -> more bid prints
            is_bullish = bar["close"] >= bar["open"]
            tick_size = 5.0 if sym == "3324" else 0.5
            bid_price = round(close_price - tick_size, 2)
            ask_price = close_price

            change_pct = ((close_price - ref_price) / ref_price) * 100

            # Generate large prints if bar has volume
            if bar_vol >= 10:
                print_count = min(6, max(1, int(bar_vol // 20)))
                chunk_vol = bar_vol / print_count
                for p_idx in range(print_count):
                    p_is_buy = is_bullish if random.random() < 0.75 else not is_bullish
                    p_vol = max(10.0, round(chunk_vol * (0.8 + random.random() * 0.4)))
                    record = {
                        "timestamp": current_time_str,
                        "price": ask_price if p_is_buy else bid_price,
                        "volume": p_vol,
                        "bid_price": bid_price,
                        "ask_price": ask_price,
                        "total_volume": total_volumes[sym],
                    }
                    if p_is_buy:
                        ask_prints[sym].append(record)
                        del ask_prints[sym][:-100]
                    else:
                        bid_prints[sym].append(record)
                        del bid_prints[sym][:-100]

            latest_tick = {
                "timestamp": current_time_str,
                "price": close_price,
                "volume": bar_vol,
                "total_volume": total_volumes[sym],
                "change_percent": round(change_pct, 2),
            }

            # Run real accumulation detection on historical slice
            acc_signal = detect_potential_accumulation(
                history[sym],
                ask_prints[sym],
                bid_prints[sym],
                latest_tick,
            )

            pressure_readings = generate_pressure_readings(history[sym])
            latest_pressure = pressure_readings[-1] if pressure_readings else None

            payload = {
                "schema_version": "1.0",
                "symbol": sym,
                "bar_count": len(history[sym]),
                "latest_bar": bar,
                "candidate_events": [],
                "pressure_gauge": latest_pressure,
                "latest_tick": latest_tick,
                "accumulation_signal": acc_signal,
                "at_ask_prints": ask_prints[sym],
                "at_bid_prints": bid_prints[sym],
            }

            dest = live_dir / f"{sym}.json"
            tmp = dest.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(dest)

        time_display = current_time_str.split("T")[1][:8] if "T" in current_time_str else current_time_str
        print(f"⏱️ [{idx+1:03d}/{total_bars:03d}] 回放時間：{time_display} (進度 {((idx+1)/total_bars)*100:.1f}%)")
        time.sleep(interval)

    print("🏁 今日真實數據回放已全數完成！")


def main() -> None:
    parser = argparse.ArgumentParser(description="StockRadar Multi-Symbol Replay")
    parser.add_argument("--date", default="2026-09-01", help="Market date (YYYY-MM-DD)")
    parser.add_argument("--speed", type=int, default=5, choices=[1, 5, 20, 60], help="Replay speed (1, 5, 20, 60)")
    args = parser.parse_args()
    run_replay(args.date, args.speed)


if __name__ == "__main__":
    main()
