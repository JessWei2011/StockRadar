"""Read-only historical one-minute K-bar retrieval and replay-session export."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from numbers import Integral
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import shioaji as sj

from .config import Settings

TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ReplayBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    tick_count: int


def _columns(raw: Any) -> Mapping[str, Sequence[Any]]:
    """Support both dict-like legacy K-bars and the current SDK KBars object."""
    if isinstance(raw, Mapping):
        return raw
    known_fields = ("ts", "Open", "High", "Low", "Close", "Volume", "Amount", "TickCount")
    columns = {
        field: getattr(raw, field)
        for field in known_fields
        if hasattr(raw, field)
    }
    if not columns:
        raise ValueError("Shioaji 回傳的 KBars 格式無法辨識。")
    return columns


def _series(raw: Mapping[str, Sequence[Any]], *names: str) -> Sequence[Any]:
    """Return a Shioaji K-bar column while tolerating SDK key casing changes."""
    normalized = {str(key).lower(): value for key, value in raw.items()}
    for name in names:
        value = normalized.get(name.lower())
        if value is not None:
            return value
    raise ValueError(f"歷史 K 棒缺少欄位：{', '.join(names)}")


def _optional_series(
    raw: Mapping[str, Sequence[Any]], length: int, default: Any, *names: str
) -> Sequence[Any]:
    try:
        return _series(raw, *names)
    except ValueError:
        return [default] * length


def _to_taipei(value: Any) -> datetime:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, Integral):
        # Shioaji 1.7 KBars timestamps are nanoseconds containing Taiwan's
        # wall-clock exchange time. Interpret the numeric instant as UTC first,
        # then attach Taipei's timezone without shifting that wall-clock time.
        wall_clock = datetime.fromtimestamp(
            int(value) / 1_000_000_000, tz=UTC
        ).replace(tzinfo=None)
        timestamp = wall_clock.replace(tzinfo=TAIPEI)
    else:
        timestamp = datetime.fromisoformat(str(value))
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=TAIPEI)
    return timestamp.astimezone(TAIPEI)


def normalise_kbars(raw: Any, symbol: str, market_date: date) -> list[ReplayBar]:
    """Convert raw K-bars into sorted, date-filtered, serialisable replay bars."""
    columns = _columns(raw)
    timestamps = _series(columns, "ts", "time", "timestamp")
    opens = _series(columns, "open")
    highs = _series(columns, "high")
    lows = _series(columns, "low")
    closes = _series(columns, "close")
    volumes = _series(columns, "volume")
    amounts = _series(columns, "amount")
    # Historical K-bars do not always expose per-minute TickCount. Preserve that
    # absence as 0 instead of inventing an estimate from OHLCV.
    tick_counts = _optional_series(
        columns, len(timestamps), 0, "tickcount", "tick_count"
    )
    columns = (timestamps, opens, highs, lows, closes, volumes, amounts, tick_counts)
    if len({len(column) for column in columns}) != 1:
        raise ValueError("歷史 K 棒欄位長度不一致。")

    bars: list[ReplayBar] = []
    for values in zip(*columns, strict=True):
        timestamp = _to_taipei(values[0])
        if timestamp.date() != market_date:
            continue
        bars.append(
            ReplayBar(
                timestamp=timestamp.isoformat(),
                open=float(values[1]),
                high=float(values[2]),
                low=float(values[3]),
                close=float(values[4]),
                volume=int(values[5]),
                amount=float(values[6]),
                tick_count=int(values[7]),
            )
        )
    bars.sort(key=lambda bar: bar.timestamp)
    if not bars:
        raise ValueError(f"{symbol} 在 {market_date.isoformat()} 沒有可用的一分 K 資料。")
    return bars


def fetch_one_minute_session(
    settings: Settings, symbol: str, market_date: date
) -> dict[str, Any]:
    """Fetch historical one-minute K-bars through a simulation-only Shioaji session."""
    api = sj.Shioaji(simulation=True)
    authenticated = False
    try:
        api.login(
            api_key=settings.api_key,
            secret_key=settings.secret_key,
            subscribe_trade=False,
        )
        authenticated = True
        contract = api.contracts.get(symbol)
        if contract is None:
            raise ValueError(f"找不到股票代碼 {symbol} 的商品契約。")
        raw = api.kbars(
            contract,
            start=market_date.isoformat(),
            end=(market_date + timedelta(days=1)).isoformat(),
        )
        bars = normalise_kbars(raw, symbol, market_date)
        return {
            "schema_version": SESSION_SCHEMA_VERSION,
            "symbol": symbol,
            "market_date": market_date.isoformat(),
            "timeframe": "1m",
            "source": "shioaji_historical_kbars",
            "bars": [asdict(bar) for bar in bars],
        }
    finally:
        if authenticated:
            api.logout()


def write_session(session: Mapping[str, Any], destination: Path) -> None:
    """Write a replay session atomically as UTF-8 JSON."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(destination)
