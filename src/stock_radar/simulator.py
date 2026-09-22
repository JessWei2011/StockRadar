"""Realistic live market data simulator for StockRadar UI testing."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import random
import time
from zoneinfo import ZoneInfo

from .accumulation import detect_potential_accumulation
from .live_collector import OrderFlowPowerTracker
from .pressure_gauge import generate_pressure_readings

TAIPEI = ZoneInfo("Asia/Taipei")

INITIAL_STOCKS = {
    "2455": {"name": "全新", "base": 135.0, "tick": 0.5, "scenario": "steady_up"},
    "3324": {"name": "雙鴻", "base": 1370.0, "tick": 5.0, "scenario": "accumulation"},
    "3406": {"name": "玉晶光", "base": 450.0, "tick": 0.5, "scenario": "dumping"},
    "3450": {"name": "聯鈞", "base": 220.0, "tick": 0.5, "scenario": "sweeping"},
    "4958": {"name": "臻鼎-KY", "base": 118.0, "tick": 0.5, "scenario": "flat"},
}


def run_simulator() -> None:
    root = Path(__file__).resolve().parents[2]
    live_dir = root / "data" / "live"
    live_dir.mkdir(parents=True, exist_ok=True)

    state = {}
    now = datetime.now(TAIPEI)

    # Seed baseline bars for each stock (last 60 bars)
    for symbol, conf in INITIAL_STOCKS.items():
        base = conf["base"]
        bars = []
        for i in range(60, 0, -1):
            t = (now - timedelta(minutes=i)).replace(second=0, microsecond=0)
            noise = (random.random() - 0.48) * conf["tick"] * 3
            p = round(base + noise, 2)
            bars.append({
                "timestamp": t.isoformat(),
                "open": p,
                "high": round(p + conf["tick"] * random.randint(0, 2), 2),
                "low": round(p - conf["tick"] * random.randint(0, 2), 2),
                "close": p,
                "volume": float(random.randint(10, 80)),
                "amount": float(random.randint(10, 80)) * p * 1000,
                "tick_count": random.randint(5, 20),
            })
        thresh = 10 if conf["base"] >= 500 else 20
        state[symbol] = {
            "price": base,
            "bars": bars,
            "at_ask_prints": [],
            "at_bid_prints": [],
            "total_vol": 1000,
            "conf": conf,
            "tracker": OrderFlowPowerTracker(),
            "threshold": thresh,
        }

    print("🚀 StockRadar 行情模擬產生器已啟動... 每秒模擬推送五檔大單與動態行情")

    while True:
        sim_now = datetime.now(TAIPEI)
        timestamp_str = sim_now.isoformat(timespec="milliseconds")

        for symbol, conf in INITIAL_STOCKS.items():
            data = state[symbol]
            cur_price = data["price"]
            tick_size = conf["tick"]
            scenario = conf["scenario"]

            # Price simulation based on scenario
            if scenario == "steady_up":
                bias = 0.62
            elif scenario == "sweeping":
                bias = 0.70  # strong buy
            elif scenario == "dumping":
                bias = 0.25  # strong sell
            elif scenario == "accumulation":
                bias = 0.55  # low-zone steady absorption
            else:
                bias = 0.50

            is_buy = random.random() < bias
            price_delta = (tick_size if is_buy else -tick_size) if random.random() < 0.4 else 0
            cur_price = round(max(1.0, cur_price + price_delta), 2)
            data["price"] = cur_price

            bid_price = round(cur_price - tick_size, 2)
            ask_price = cur_price

            # Big prints generator
            thresh = data["threshold"]
            if random.random() < 0.65:
                vol = random.choice([10, 15, 20, 30, 50, 80, 120]) if random.random() < 0.45 else random.randint(2, 9)
                data["total_vol"] += vol

                print_record = {
                    "timestamp": timestamp_str,
                    "price": ask_price if is_buy else bid_price,
                    "volume": float(vol),
                    "bid_price": bid_price,
                    "ask_price": ask_price,
                    "total_volume": float(data["total_vol"]),
                }

                if is_buy:
                    data["at_ask_prints"].append(print_record)
                    del data["at_ask_prints"][:-100]
                else:
                    data["at_bid_prints"].append(print_record)
                    del data["at_bid_prints"][:-100]

                data["tracker"].update(
                    timestamp_str,
                    ask_price if is_buy else bid_price,
                    int(vol),
                    is_buy=is_buy,
                    threshold=thresh,
                )

            # Latest tick
            change_pct = ((cur_price - conf["base"]) / conf["base"]) * 100
            latest_tick = {
                "timestamp": timestamp_str,
                "price": cur_price,
                "volume": random.randint(1, 10),
                "total_volume": data["total_vol"],
                "change_percent": round(change_pct, 2),
            }

            # Update latest bar
            latest_bar = data["bars"][-1]
            latest_bar["close"] = cur_price
            latest_bar["high"] = max(latest_bar["high"], cur_price)
            latest_bar["low"] = min(latest_bar["low"], cur_price)
            latest_bar["volume"] += 1

            # Accumulation signal
            acc_signal = detect_potential_accumulation(
                data["bars"],
                data["at_ask_prints"],
                data["at_bid_prints"],
                latest_tick,
            )

            # Pressure gauge
            pressure_readings = generate_pressure_readings(data["bars"])
            latest_pressure = pressure_readings[-1] if pressure_readings else None

            # Write snapshot
            payload = {
                "schema_version": "1.0",
                "symbol": symbol,
                "bar_count": len(data["bars"]),
                "latest_bar": latest_bar,
                "candidate_events": [],
                "pressure_gauge": latest_pressure,
                "latest_tick": latest_tick,
                "accumulation_signal": acc_signal,
                "at_ask_prints": data["at_ask_prints"],
                "at_bid_prints": data["at_bid_prints"],
                "order_flow_power": data["tracker"].to_dict(thresh),
            }

            dest = live_dir / f"{symbol}.json"
            tmp = dest.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(dest)

        time.sleep(0.8)


if __name__ == "__main__":
    try:
        run_simulator()
    except KeyboardInterrupt:
        print("SIMULATOR_STOPPED")
