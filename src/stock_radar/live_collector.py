"""Read-only Shioaji collector for StockRadar live monitoring."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import time
import threading
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

import shioaji as sj

from .accumulation import detect_potential_accumulation
from .candidate_events import CandidateParameters, generate_candidate_events
from .config import load_settings
from .historical import normalise_kbars
from .pressure_gauge import generate_pressure_readings
from .toast_notifications import OncePerEventDispatcher, WindowsToastSink, candidate_event_to_toast


TAIPEI = ZoneInfo("Asia/Taipei")


def _value(source: Any, name: str) -> Any:
    normalised = name.replace("_", "").lower()
    if isinstance(source, Mapping):
        for key, value in source.items():
            if str(key).replace("_", "").lower() == normalised:
                return value
        return None
    for attribute in dir(source):
        if attribute.replace("_", "").lower() == normalised:
            return getattr(source, attribute)
    return None


def normalise_kbar(kbar: Any) -> dict[str, Any]:
    """Normalise SDK KBar callback values without retaining SDK objects."""
    date = str(_value(kbar, "date")).replace("/", "-")
    time = str(_value(kbar, "time"))
    timestamp = f"{date}T{time[:8]}+08:00"
    return {
        "timestamp": timestamp,
        "open": float(_value(kbar, "open")),
        "high": float(_value(kbar, "high")),
        "low": float(_value(kbar, "low")),
        "close": float(_value(kbar, "close")),
        "volume": float(_value(kbar, "volume")),
        "amount": float(_value(kbar, "amount") or 0),
        "tick_count": int(_value(kbar, "tick_count") or 0),
    }


def _normalise_quote_timestamp(quote: Any) -> str:
    """Return an Asia/Taipei ISO timestamp from a Shioaji stream object."""
    value = _value(quote, "datetime")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=TAIPEI)
        return value.astimezone(TAIPEI).isoformat(timespec="milliseconds")
    date = str(_value(quote, "date")).replace("/", "-")
    time = str(_value(quote, "time"))
    return f"{date}T{time}+08:00"


def normalise_tick(tick: Any) -> dict[str, Any]:
    """Keep Tick fields needed to identify an actual completed stock trade."""
    raw_change = _value(tick, "pct_chg")
    try:
        change_percent = float(raw_change) if raw_change is not None else None
    except (TypeError, ValueError):
        change_percent = None
    return {
        "timestamp": _normalise_quote_timestamp(tick),
        "price": float(_value(tick, "close")),
        "volume": int(_value(tick, "volume") or 0),
        "total_volume": int(_value(tick, "total_volume") or 0),
        "change_percent": change_percent,
        # Shioaji marks collection-auction indicative quotes with simtrade.
        # Preserve it so they can never be treated as completed trades.
        "simtrade": bool(_value(tick, "simtrade")),
    }


def normalise_bidask(bidask: Any) -> dict[str, Any]:
    """Keep the best bid/ask present when a Tick is received."""
    bid_prices = _value(bidask, "bid_price") or []
    ask_prices = _value(bidask, "ask_price") or []
    return {
        "timestamp": _normalise_quote_timestamp(bidask),
        "bid_price": float(bid_prices[0]) if bid_prices else None,
        "ask_price": float(ask_prices[0]) if ask_prices else None,
    }


def _book_is_fresh(book: Mapping[str, Any], tick: Mapping[str, Any]) -> bool:
    """Avoid classifying a trade with a stale order-book snapshot."""
    try:
        book_time = datetime.fromisoformat(str(book["timestamp"]))
        tick_time = datetime.fromisoformat(str(tick["timestamp"]))
    except (KeyError, TypeError, ValueError):
        return False
    return abs((tick_time - book_time).total_seconds()) <= 5


class OrderFlowPowerTracker:
    """Tracks intraday cumulative buy/sell power and VWAP for major and retail players."""

    def __init__(self) -> None:
        self.major_buy_vol = 0
        self.major_sell_vol = 0
        self.major_buy_amt = 0.0
        self.major_sell_amt = 0.0
        self.retail_buy_vol = 0
        self.retail_sell_vol = 0
        self.retail_buy_amt = 0.0
        self.retail_sell_amt = 0.0
        self.timeline: dict[str, dict[str, int]] = {}

    def update(self, timestamp_str: str, price: float, volume: int, is_buy: bool, threshold: int) -> None:
        amt = price * volume
        if volume >= threshold:
            if is_buy:
                self.major_buy_vol += volume
                self.major_buy_amt += amt
            else:
                self.major_sell_vol += volume
                self.major_sell_amt += amt
        else:
            if is_buy:
                self.retail_buy_vol += volume
                self.retail_buy_amt += amt
            else:
                self.retail_sell_vol += volume
                self.retail_sell_amt += amt

        try:
            if "T" in timestamp_str:
                time_key = timestamp_str.split("T")[1][:5]
            elif " " in timestamp_str:
                time_key = timestamp_str.split(" ")[1][:5]
            else:
                time_key = timestamp_str[:5]
        except Exception:
            time_key = "09:00"

        major_net = self.major_buy_vol - self.major_sell_vol
        retail_net = self.retail_buy_vol - self.retail_sell_vol
        self.timeline[time_key] = {"m": major_net, "r": retail_net}

    def to_dict(self, threshold: int) -> dict[str, Any]:
        major_tot = self.major_buy_vol + self.major_sell_vol
        major_vwap = round((self.major_buy_amt + self.major_sell_amt) / major_tot, 2) if major_tot > 0 else None
        retail_tot = self.retail_buy_vol + self.retail_sell_vol
        retail_vwap = round((self.retail_buy_amt + self.retail_sell_amt) / retail_tot, 2) if retail_tot > 0 else None

        sorted_times = sorted(self.timeline.keys())
        series = [{"t": t, "m": self.timeline[t]["m"], "r": self.timeline[t]["r"]} for t in sorted_times]

        return {
            "major_net": self.major_buy_vol - self.major_sell_vol,
            "major_buy_vol": self.major_buy_vol,
            "major_sell_vol": self.major_sell_vol,
            "major_vwap": major_vwap,
            "retail_net": self.retail_buy_vol - self.retail_sell_vol,
            "retail_buy_vol": self.retail_buy_vol,
            "retail_sell_vol": self.retail_sell_vol,
            "retail_vwap": retail_vwap,
            "threshold": threshold,
            "series": series,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OrderFlowPowerTracker:
        tracker = cls()
        tracker.major_buy_vol = int(data.get("major_buy_vol", 0))
        tracker.major_sell_vol = int(data.get("major_sell_vol", 0))
        m_vwap = float(data.get("major_vwap") or 0.0)
        tracker.major_buy_amt = tracker.major_buy_vol * m_vwap
        tracker.major_sell_amt = tracker.major_sell_vol * m_vwap

        tracker.retail_buy_vol = int(data.get("retail_buy_vol", 0))
        tracker.retail_sell_vol = int(data.get("retail_sell_vol", 0))
        r_vwap = float(data.get("retail_vwap") or 0.0)
        tracker.retail_buy_amt = tracker.retail_buy_vol * r_vwap
        tracker.retail_sell_amt = tracker.retail_sell_vol * r_vwap

        if "series" in data and isinstance(data["series"], list):
            for pt in data["series"]:
                if isinstance(pt, dict) and "t" in pt:
                    tracker.timeline[str(pt["t"])] = {"m": int(pt.get("m", 0)), "r": int(pt.get("r", 0))}
        return tracker


class LiveCandidateProcessor:
    """State held in memory for one collector process; no order capability."""

    def __init__(self, output_dir: Path, dispatch: Callable[[str, Mapping[str, Any]], bool] | None = None) -> None:
        self.output_dir = output_dir
        self.dispatch = dispatch
        self.bars: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.pressure_readings: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.latest_bidask: dict[str, dict[str, Any]] = {}
        self.latest_ticks: dict[str, dict[str, Any]] = {}
        self.last_prices: dict[str, float] = {}
        self.at_ask_prints: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.at_bid_prints: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.accumulation_signals: dict[str, dict[str, Any]] = {}
        self.dispositions: dict[str, str] = {}
        self.order_flow_trackers: dict[str, OrderFlowPowerTracker] = {}
        self.custom_thresholds: dict[str, int] = {}

    def get_threshold(self, symbol: str) -> int:
        if symbol in self.custom_thresholds and self.custom_thresholds[symbol] > 0:
            return self.custom_thresholds[symbol]
        try:
            wl_path = self.output_dir.parent / "watchlist.json"
            if wl_path.exists():
                wl_data = json.loads(wl_path.read_text(encoding="utf-8-sig"))
                thresh_map = wl_data.get("thresholds", {})
                if symbol in thresh_map and int(thresh_map[symbol]) > 0:
                    self.custom_thresholds[symbol] = int(thresh_map[symbol])
                    return self.custom_thresholds[symbol]
        except Exception:
            pass
        ref_price = self.last_prices.get(symbol, 100.0)
        if ref_price >= 1000:
            return 5
        if ref_price >= 500:
            return 8
        if ref_price >= 200:
            return 15
        if ref_price >= 100:
            return 25
        if ref_price >= 50:
            return 50
        return 80

    def _refresh_accumulation(self, symbol: str) -> None:
        self.accumulation_signals[symbol] = detect_potential_accumulation(
            self.bars[symbol],
            self.at_ask_prints[symbol],
            self.at_bid_prints[symbol],
            self.latest_ticks.get(symbol),
        )

    def process(self, symbol: str, bar: Mapping[str, Any]) -> list[dict[str, Any]]:
        history = self.bars[symbol]
        if history and str(bar["timestamp"]) <= str(history[-1]["timestamp"]):
            return []
        history.append(dict(bar))
        self.events[symbol] = []
        self.pressure_readings[symbol] = generate_pressure_readings(history)
        self._refresh_accumulation(symbol)
        self._write(symbol)
        return []

    def seed_existing_live(self, symbol: str) -> None:
        """Preserve today's accumulated trades and state across restarts for continuous history."""
        target = self.output_dir / f"{symbol}.json"
        if not target.exists():
            return
        try:
            content = json.loads(target.read_text(encoding="utf-8"))
            updated_at = content.get("updated_at")
            if not updated_at:
                return
            today_str = datetime.now(TAIPEI).strftime("%Y-%m-%d")
            # Only restore if the data is from today
            if not updated_at.startswith(today_str):
                return

            if "at_ask_prints" in content and isinstance(content["at_ask_prints"], list):
                self.at_ask_prints[symbol] = content["at_ask_prints"]
            if "at_bid_prints" in content and isinstance(content["at_bid_prints"], list):
                self.at_bid_prints[symbol] = content["at_bid_prints"]
            if "latest_tick" in content and content["latest_tick"]:
                self.latest_ticks[symbol] = content["latest_tick"]
                if "price" in content["latest_tick"]:
                    self.last_prices[symbol] = float(content["latest_tick"]["price"])
            if "disposition" in content and content["disposition"]:
                self.dispositions[symbol] = content["disposition"]
            if "order_flow_power" in content and isinstance(content["order_flow_power"], dict):
                self.order_flow_trackers[symbol] = OrderFlowPowerTracker.from_dict(content["order_flow_power"])
        except Exception:
            pass

    def seed(self, symbol: str, bars: list[Mapping[str, Any]]) -> None:
        """Load completed bars at startup without replaying historic Toasts."""
        self.seed_existing_live(symbol)
        history = self.bars[symbol]
        for bar in bars:
            if history and str(bar["timestamp"]) <= str(history[-1]["timestamp"]):
                continue
            history.append(dict(bar))
        if not history:
            return
        self.events[symbol] = []
        self.pressure_readings[symbol] = generate_pressure_readings(history)
        self._refresh_accumulation(symbol)
        self._write(symbol)

    def process_bidask(self, symbol: str, bidask: Mapping[str, Any]) -> None:
        """Remember the latest five-level best prices; this never sends orders."""
        self.latest_bidask[symbol] = dict(bidask)

    def process_tick(self, symbol: str, tick: Mapping[str, Any]) -> dict[str, Any] | None:
        """Record executed trades for UI-side filtering and lamp triggering."""
        if bool(tick.get("simtrade", False)):
            return None
        self.latest_ticks[symbol] = dict(tick)
        price = float(tick["price"])
        prev_price = self.last_prices.get(symbol)
        self.last_prices[symbol] = price

        candidate_book = self.latest_bidask.get(symbol)
        book = candidate_book if candidate_book and _book_is_fresh(candidate_book, tick) else None
        ask_price = book.get("ask_price") if book else None
        bid_price = book.get("bid_price") if book else None

        # Only classify trades backed by evidence.  A trade inside the spread is
        # intentionally left unclassified instead of being forced to buy/sell.
        if ask_price is not None and abs(price - float(ask_price)) <= 0.000001:
            classification, signals = "AT_BEST_ASK", self.at_ask_prints[symbol]
        elif bid_price is not None and abs(price - float(bid_price)) <= 0.000001:
            classification, signals = "AT_BEST_BID", self.at_bid_prints[symbol]
        elif ask_price is not None and bid_price is not None and float(ask_price) > float(bid_price):
            self._refresh_accumulation(symbol)
            self._write(symbol)
            return None
        elif prev_price is not None and price != prev_price:
            if price > prev_price:
                classification, signals = "AT_BEST_ASK", self.at_ask_prints[symbol]
            else:
                classification, signals = "AT_BEST_BID", self.at_bid_prints[symbol]
        else:
            self._refresh_accumulation(symbol)
            self._write(symbol)
            return None

        record = {
            "timestamp": tick["timestamp"],
            "price": price,
            "volume": int(tick["volume"]),
            "total_volume": int(tick["total_volume"]),
            "bid_price": bid_price,
            "ask_price": ask_price,
            "classification": classification,
        }
        signals.append(record)
        # Keep the live file bounded while retaining enough records for inspection.
        del signals[:-500]

        # Update order flow power tracker (major vs retail net volume & VWAP)
        thresh = self.get_threshold(symbol)
        if symbol not in self.order_flow_trackers:
            self.order_flow_trackers[symbol] = OrderFlowPowerTracker()
        self.order_flow_trackers[symbol].update(
            str(tick["timestamp"]),
            price,
            int(tick["volume"]),
            is_buy=(classification == "AT_BEST_ASK"),
            threshold=thresh,
        )

        self._refresh_accumulation(symbol)
        self._write(symbol)
        return record

    def _write(self, symbol: str) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            latest_bar = self.bars[symbol][-1] if self.bars[symbol] else None
            tracker = self.order_flow_trackers.get(symbol)
            thresh = self.get_threshold(symbol)
            power_payload = tracker.to_dict(thresh) if tracker else None
            payload = {
                "schema_version": "1.0",
                "symbol": symbol,
                "bar_count": len(self.bars[symbol]),
                "updated_at": datetime.now(TAIPEI).isoformat(timespec="milliseconds"),
                "latest_bar": latest_bar,
                "candidate_events": self.events[symbol],
                "pressure_gauge": self.pressure_readings[symbol][-1] if self.pressure_readings[symbol] else None,
                "latest_tick": self.latest_ticks.get(symbol),
                "accumulation_signal": self.accumulation_signals.get(symbol),
                "at_ask_prints": self.at_ask_prints[symbol],
                "at_bid_prints": self.at_bid_prints[symbol],
                "disposition": self.dispositions.get(symbol),
                "order_flow_power": power_payload,
            }
            content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            destination = self.output_dir / f"{symbol}.json"
            temporary = destination.with_suffix(".tmp")
            for attempt in range(5):
                try:
                    temporary.write_text(content, encoding="utf-8")
                    temporary.replace(destination)
                    break
                except (PermissionError, OSError):
                    if attempt == 4:
                        try:
                            destination.write_text(content, encoding="utf-8")
                        except Exception:
                            pass
                    else:
                        time.sleep(0.02)
        except Exception:
            pass


def _load_watchlist(root: Path) -> list[str]:
    payload = json.loads((root / "data/watchlist.json").read_text(encoding="utf-8-sig"))
    symbols = [str(symbol) for symbol in payload.get("symbols", [])]
    if not symbols:
        raise RuntimeError("watchlist.json 沒有設定任何股票代號。")
    if len(symbols) > 5:
        raise RuntimeError("第一版最多監控 5 檔股票。")
    return symbols


async def _run_live_collector(
    api: Any,
    *,
    symbols: list[str],
    processor: LiveCandidateProcessor,
    production: bool,
    stop_event: threading.Event | None = None,
    on_state: Callable[[str], None] | None = None,
) -> None:
    subscribed: list[Any] = []

    try:
        settings = load_settings(allow_production=True)
        if on_state:
            on_state("CONNECTING")
        api.login(api_key=settings.api_key, secret_key=settings.secret_key, subscribe_trade=False)
        if stop_event and stop_event.is_set():
            return
        kbar_receiver = api.get_kbar_receiver()
        tick_receiver = api.get_tick_stk_v1_receiver()
        bidask_receiver = api.get_bidask_stk_v1_receiver()
        market_date = datetime.now(TAIPEI).date()
        for symbol in symbols:
            if stop_event and stop_event.is_set():
                return
            contract = api.contracts.get(symbol)
            if contract is None:
                raise RuntimeError(f"找不到股票合約：{symbol}")
            try:
                stock_info = api.Contracts.Stocks[symbol]
                disp_min = getattr(stock_info, "disposition_match_interval_min", None)
                disp_lvl = getattr(stock_info, "disposition_level", None)
                if disp_min:
                    processor.dispositions[symbol] = f"{disp_min}分"
                elif disp_lvl:
                    processor.dispositions[symbol] = f"處置{disp_lvl}"
            except Exception:
                pass
            try:
                raw_bars = api.kbars(
                    contract,
                    start=market_date.isoformat(),
                    end=(market_date + timedelta(days=1)).isoformat(),
                )
                processor.seed(
                    symbol,
                    [asdict(bar) for bar in normalise_kbars(raw_bars, symbol, market_date)],
                )
                print(
                    f"BOOTSTRAP_OK={symbol}; BARS={len(processor.bars[symbol])}",
                    flush=True,
                )
            except Exception as exc:
                print(f"BOOTSTRAP_FAILED={symbol}; {type(exc).__name__}: {exc}", flush=True)
            if stop_event and stop_event.is_set():
                return
            if on_state:
                on_state("SUBSCRIBING")
            api.subscribe(contract, quote_type=sj.QuoteType.KBar)
            api.subscribe(contract, quote_type=sj.QuoteType.Tick)
            api.subscribe(contract, quote_type=sj.QuoteType.BidAsk)
            subscribed.append(contract)
        mode = "PRODUCTION" if production else "SIMULATION"
        print(f"LIVE_COLLECTOR_STARTED={mode}; SYMBOLS={','.join(symbols)}; TRADE_SUBSCRIPTION=DISABLED", flush=True)
        print("監聽已收 1 分 K、逐筆成交與五檔報價；按 Ctrl+C 停止。", flush=True)
        receivers = {
            "kbar": kbar_receiver,
            "tick": tick_receiver,
            "bidask": bidask_receiver,
        }
        pending = {asyncio.ensure_future(receiver.recv()): kind for kind, receiver in receivers.items()}
        last_packet_time = time.monotonic()
        WATCHDOG_TIMEOUT_SEC = 90.0  # 90 秒無任何行情封包則觸發自我修復與自動重連
        if on_state:
            on_state("STREAMING")

        while True:
            if stop_event and stop_event.is_set():
                return
            done, _ = await asyncio.wait(pending, timeout=5.0, return_when=asyncio.FIRST_COMPLETED)
            now_mono = time.monotonic()

            # 寫入心跳檔案供 Server 與前端檢查健康度
            try:
                hb_file = processor.output_dir / ".heartbeat.json"
                hb_data = {
                    "updated_at": datetime.now(TAIPEI).isoformat(timespec="milliseconds"),
                    "status": "HEALTHY",
                    "symbols": symbols,
                    "seconds_since_last_packet": round(now_mono - last_packet_time, 1),
                }
                hb_file.write_text(json.dumps(hb_data), encoding="utf-8")
            except Exception:
                pass

            if not done:
                now_dt = datetime.now(TAIPEI)
                is_market_hours = (now_dt.weekday() < 5) and (
                    (now_dt.hour == 9) or (now_dt.hour in (10, 11, 12)) or (now_dt.hour == 13 and now_dt.minute <= 35)
                )
                if is_market_hours and (now_mono - last_packet_time > WATCHDOG_TIMEOUT_SEC):
                    print(
                        f"[StockRadar Watchdog] ⚠️ 警告：已超過 {int(now_mono - last_packet_time)} 秒未收到任何行情封包，觸發自我修復與重新連線...",
                        flush=True,
                    )
                    raise ConnectionResetError(
                        f"Watchdog triggered: no market packets received for {int(now_mono - last_packet_time)}s"
                    )
                continue

            for task in done:
                last_packet_time = time.monotonic()
                kind = pending.pop(task)
                try:
                    quote = task.result()
                    symbol = str(_value(quote, "code") or "")
                    if kind == "kbar":
                        events = processor.process(symbol, normalise_kbar(quote))
                        if events:
                            print(f"CANDIDATE_EVENT={symbol}|{events[-1]['kind']}|{events[-1]['timestamp']}", flush=True)
                    elif kind == "bidask":
                        processor.process_bidask(symbol, normalise_bidask(quote))
                    else:
                        signal = processor.process_tick(symbol, normalise_tick(quote))
                        if signal:
                            print(f"AT_ASK_PRINT={symbol}|{signal['timestamp']}|{signal['price']}|{signal['volume']}", flush=True)
                except Exception as loop_err:
                    print(f"[LiveCollectorStreamWarning] {kind}: {loop_err}", flush=True)
                finally:
                    pending[asyncio.ensure_future(receivers[kind].recv())] = kind
    finally:
        for task in locals().get("pending", {}):
            task.cancel()
        for contract in subscribed:
            try:
                api.unsubscribe(contract, quote_type=sj.QuoteType.KBar)
                api.unsubscribe(contract, quote_type=sj.QuoteType.Tick)
                api.unsubscribe(contract, quote_type=sj.QuoteType.BidAsk)
            except Exception:
                pass
        try:
            api.logout()
        except Exception:
            pass


def main(
    stop_event: threading.Event | None = None,
    on_state: Callable[[str], None] | None = None,
) -> int:
    root = Path(__file__).resolve().parents[2]
    runtime_home = root / "data" / ".shioaji-runtime"
    runtime_home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("SJ_HOME_PATH", str(runtime_home))
    settings = load_settings(allow_production=True)
    symbols = _load_watchlist(root)
    dispatcher = OncePerEventDispatcher(WindowsToastSink())
    processor = LiveCandidateProcessor(
        root / "data/live",
        dispatch=lambda symbol, event: dispatcher.dispatch(candidate_event_to_toast(symbol, event)),
    )
    api = sj.Shioaji(simulation=not settings.production)
    try:
        asyncio.run(
            _run_live_collector(
                api,
                symbols=symbols,
                processor=processor,
                production=settings.production,
                stop_event=stop_event,
                on_state=on_state,
            )
        )
    except KeyboardInterrupt:
        print("LIVE_COLLECTOR_STOPPED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
