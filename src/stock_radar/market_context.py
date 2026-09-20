"""Versioned price-volume context derived only from completed minute bars.

The module deliberately describes observable price/volume alignment.  OHLCV
does not identify the actual aggressor, trader identity, or "main force".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median
from typing import Any, Mapping, Sequence
import json
from pathlib import Path


@dataclass(frozen=True)
class MarketContextParameters:
    """Rules shared by replay and a future completed-bar live adapter."""

    volume_window: int = 20
    high_volume_ratio: float = 2.0
    bullish_close_position_min: float = 0.65
    bearish_close_position_max: float = 0.35


POSTURE_BULLISH = "PRICE_VOLUME_BULLISH"
POSTURE_BEARISH = "PRICE_VOLUME_BEARISH"
POSTURE_CONFLICT = "PRICE_VOLUME_CONFLICT"

_POSTURE_TITLE = {
    POSTURE_BULLISH: "量價偏多",
    POSTURE_BEARISH: "量價偏空",
    POSTURE_CONFLICT: "量價矛盾",
}


def _number(bar: Mapping[str, Any], key: str) -> float:
    return float(bar[key])


def _event_type(event: Mapping[str, Any]) -> str:
    value = event.get("type", event.get("event_type"))
    if not value:
        raise ValueError("Market event is missing type")
    return str(value)


def _summarise(
    posture: str,
    event_title: str,
    ratio: float,
    close_position: float | None,
) -> str:
    if close_position is None:
        return (
            f"量比 {ratio:.2f} 倍，但本根 K 無振幅，無法判讀收盤位置；"
            f"量價矛盾，對應事件：{event_title}。"
        )
    percentage = round(close_position * 100)
    if posture == POSTURE_BULLISH:
        return (
            f"量比 {ratio:.2f} 倍，收在本根振幅上緣 {percentage}%；"
            f"量價偏多，對應事件：{event_title}。"
        )
    if posture == POSTURE_BEARISH:
        return (
            f"量比 {ratio:.2f} 倍，收在本根振幅下緣 {percentage}%；"
            f"量價偏空，對應事件：{event_title}。"
        )
    return (
        f"量比 {ratio:.2f} 倍，收盤位置 {percentage}%；"
        f"量價未形成同向優勢，對應事件：{event_title}。"
    )


def generate_market_contexts(
    bars: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    parameters: MarketContextParameters | None = None,
) -> list[dict[str, Any]]:
    """Return one context for each event that has a usable completed-bar baseline.

    The baseline excludes the event bar and all future bars.  Contexts are
    intentionally omitted for insufficient history or a zero-volume baseline.
    A zero-range event bar is retained as conflict because the event itself is
    important, but its close position is explicitly unavailable.
    """

    rules = parameters or MarketContextParameters()
    if rules.volume_window < 1:
        raise ValueError("volume_window must be positive")

    bar_index = {str(bar["timestamp"]): index for index, bar in enumerate(bars)}
    contexts: list[dict[str, Any]] = []

    for event in events:
        timestamp = str(event["timestamp"])
        index = bar_index.get(timestamp)
        if index is None or index < rules.volume_window:
            continue

        history = bars[index - rules.volume_window:index]
        baseline = float(median(_number(bar, "volume") for bar in history))
        if baseline <= 0:
            continue

        bar = bars[index]
        high, low = _number(bar, "high"), _number(bar, "low")
        bar_range = high - low

        opening, close, volume = (
            _number(bar, "open"),
            _number(bar, "close"),
            _number(bar, "volume"),
        )
        volume_ratio = volume / baseline
        close_position = (close - low) / bar_range if bar_range > 0 else None

        if close_position is None:
            posture = POSTURE_CONFLICT
        elif (
            volume_ratio >= rules.high_volume_ratio
            and close >= opening
            and close_position >= rules.bullish_close_position_min
        ):
            posture = POSTURE_BULLISH
        elif (
            volume_ratio >= rules.high_volume_ratio
            and close <= opening
            and close_position <= rules.bearish_close_position_max
        ):
            posture = POSTURE_BEARISH
        else:
            posture = POSTURE_CONFLICT

        event_metrics = event.get("metrics", {})
        if not isinstance(event_metrics, Mapping):
            event_metrics = {}
        key_high = float(event_metrics.get("sell_high", event_metrics.get("breakout_level", high)))
        key_low = float(event_metrics.get("sell_low", low))
        event_type = _event_type(event)
        event_title = str(event.get("title", event_type))

        contexts.append(
            {
                "timestamp": timestamp,
                "event_type": event_type,
                "event_title": event_title,
                "posture": posture,
                "title": _POSTURE_TITLE[posture],
                "summary": _summarise(posture, event_title, volume_ratio, close_position),
                "volume_ratio": round(volume_ratio, 2),
                "close_position": None if close_position is None else round(close_position, 4),
                "key_high": key_high,
                "key_low": key_low,
            }
        )
    return contexts


def build_market_context_session(
    replay: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    parameters: MarketContextParameters | None = None,
) -> dict[str, Any]:
    """Build the stable file contract consumed by the Dashboard."""

    rules = parameters or MarketContextParameters()
    return {
        "schema_version": "1.0",
        "source_replay": str(replay.get("source", "unknown")),
        "symbol": str(replay["symbol"]),
        "market_date": str(replay["market_date"]),
        "timeframe": str(replay["timeframe"]),
        "parameters": asdict(rules),
        "contexts": generate_market_contexts(replay["bars"], events, rules),
    }


def write_market_context_session(path: Path, session: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
