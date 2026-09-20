"""Fetch today's real one-minute bars and real exchange ticks for replay."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from stock_radar.config import load_settings
from stock_radar.historical import fetch_one_minute_session, fetch_tick_session, write_session


def write_status(destination: Path, **payload: object) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def _cached_session_is_valid(path: Path, key: str, symbol: str, market_date: date) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        payload.get("symbol") == symbol
        and payload.get("market_date") == market_date.isoformat()
        and isinstance(payload.get(key), list)
        and bool(payload[key])
    )


def fetch_today(*, refresh: bool = False) -> int:
    symbols = ["2455", "3324", "3406", "3450", "4958"]
    today = date.today()
    print(f"Preparing today ({today}) real replay data for {symbols}...")

    replays_dir = Path(__file__).resolve().parents[2] / "data" / "replays"
    replays_dir.mkdir(parents=True, exist_ok=True)
    status_path = replays_dir.parent / "live" / "replay_status.json"
    write_status(
        status_path,
        schema_version="1.0",
        mode="REAL_TICK_REPLAY",
        state="CACHE_CHECKING",
        market_date=today.isoformat(),
        completed_symbols=0,
        total_symbols=len(symbols),
    )
    failures = 0
    missing_symbols = []
    for symbol in symbols:
        bars_path = replays_dir / f"{symbol}_{today.isoformat()}_1m.json"
        ticks_path = replays_dir / f"{symbol}_{today.isoformat()}_ticks.json"
        cached = (
            not refresh
            and _cached_session_is_valid(bars_path, "bars", symbol, today)
            and _cached_session_is_valid(ticks_path, "ticks", symbol, today)
        )
        if cached:
            print(f"CACHE_HIT={symbol}; using saved real K bars and ticks")
        else:
            missing_symbols.append(symbol)

    settings = load_settings(allow_production=True) if missing_symbols else None

    for index, symbol in enumerate(symbols, start=1):
        bars_path = replays_dir / f"{symbol}_{today.isoformat()}_1m.json"
        ticks_path = replays_dir / f"{symbol}_{today.isoformat()}_ticks.json"
        cached = symbol not in missing_symbols
        try:
            if not cached:
                if settings is None:
                    raise RuntimeError("下載設定未初始化。")
                bars = fetch_one_minute_session(settings, symbol, today)
                write_session(bars, bars_path)
                ticks = fetch_tick_session(settings, symbol, today)
                write_session(ticks, ticks_path)
                print(f"FETCH_OK={symbol}; BARS={len(bars['bars'])}; TICKS={len(ticks['ticks'])}")
        except Exception as exc:
            failures += 1
            print(f"FETCH_FAILED={symbol}; {type(exc).__name__}: {exc}")
        write_status(
            status_path,
            schema_version="1.0",
            mode="REAL_TICK_REPLAY",
            state="FETCHING" if missing_symbols else "CACHE_CHECKING",
            market_date=today.isoformat(),
            completed_symbols=index,
            total_symbols=len(symbols),
            failures=failures,
        )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch or reuse today's StockRadar replay data")
    parser.add_argument("--refresh", action="store_true", help="Force a fresh Shioaji download")
    args = parser.parse_args()
    return fetch_today(refresh=args.refresh)


if __name__ == "__main__":
    raise SystemExit(main())
