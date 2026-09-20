"""Completed-bar price-volume pressure readings for the Dashboard gauge.

The gauge is deliberately a compact description of OHLCV, not a statement
about trader identity, future prices, or a trading instruction.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence


RISING = "RISING"
FALLING = "FALLING"
STABLE = "STABLE"


@dataclass(frozen=True)
class PressureGaugeParameters:
    volume_window: int = 20
    volume_ratio_cap: float = 3.0
    price_close_weight: float = 0.7
    price_body_weight: float = 0.3
    impulse_scale: float = 55.0
    memory_factor: float = 0.82
    direction_deadband: float = 2.0


def _number(bar: Mapping[str, Any], key: str) -> float:
    return float(bar[key])


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _summary(level: float, ratio: float, close_position: float | None) -> str:
    posture = "量價偏多" if level >= 20 else "量價偏空" if level <= -20 else "量價平衡"
    if close_position is None:
        position_text = "本根無振幅，收盤位置不可判讀"
    else:
        position_text = f"收在本根振幅的 {close_position * 100:.0f}% 位置"
    return f"{posture}；量比 {ratio:.2f} 倍，{position_text}。"


def _unavailable_reading(timestamp: str) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "available": False,
        "level": 0.0,
        "delta": 0.0,
        "direction": STABLE,
        "volume_ratio": None,
        "close_position": None,
        "price_pressure": None,
        "volume_pressure": None,
        "summary": "量能基準尚不足，水位維持中線。",
    }


def generate_pressure_readings(
    bars: Sequence[Mapping[str, Any]],
    parameters: PressureGaugeParameters | None = None,
) -> list[dict[str, Any]]:
    """Build one causal water-level reading for every completed bar."""

    rules = parameters or PressureGaugeParameters()
    if rules.volume_window < 1:
        raise ValueError("volume_window must be positive")
    if rules.volume_ratio_cap <= 0:
        raise ValueError("volume_ratio_cap must be positive")
    if not 0 <= rules.memory_factor <= 1:
        raise ValueError("memory_factor must be between zero and one")

    readings: list[dict[str, Any]] = []
    previous_level = 0.0
    for index, bar in enumerate(bars):
        timestamp = str(bar["timestamp"])
        if index < rules.volume_window:
            readings.append(_unavailable_reading(timestamp))
            previous_level = 0.0
            continue

        baseline = float(median(_number(item, "volume") for item in bars[index - rules.volume_window:index]))
        if baseline <= 0:
            readings.append(_unavailable_reading(timestamp))
            previous_level = 0.0
            continue

        opening = _number(bar, "open")
        high = _number(bar, "high")
        low = _number(bar, "low")
        close = _number(bar, "close")
        volume = _number(bar, "volume")
        bar_range = high - low
        close_position = (close - low) / bar_range if bar_range > 0 else None
        close_position_pressure = 0.0 if close_position is None else 2 * close_position - 1
        body_direction = 1.0 if close > opening else -1.0 if close < opening else 0.0
        price_pressure = _clamp(
            rules.price_close_weight * close_position_pressure
            + rules.price_body_weight * body_direction,
            -1.0,
            1.0,
        )
        volume_ratio = volume / baseline
        volume_pressure = min(volume_ratio, rules.volume_ratio_cap) / rules.volume_ratio_cap
        impulse = price_pressure * volume_pressure * rules.impulse_scale
        candidate = _clamp(previous_level * rules.memory_factor + impulse, -100.0, 100.0)
        delta = candidate - previous_level
        direction = STABLE if abs(delta) < rules.direction_deadband else RISING if delta > 0 else FALLING
        level = round(candidate, 1)
        readings.append(
            {
                "timestamp": timestamp,
                "available": True,
                "level": level,
                "delta": round(delta, 1),
                "direction": direction,
                "volume_ratio": round(volume_ratio, 4),
                "close_position": None if close_position is None else round(close_position, 4),
                "price_pressure": round(price_pressure, 4),
                "volume_pressure": round(volume_pressure, 4),
                "summary": _summary(level, volume_ratio, close_position),
            }
        )
        previous_level = level
    return readings


def build_pressure_gauge_session(
    replay: Mapping[str, Any], parameters: PressureGaugeParameters | None = None
) -> dict[str, Any]:
    rules = parameters or PressureGaugeParameters()
    return {
        "schema_version": "1.0",
        "source_replay": str(replay.get("source", "unknown")),
        "symbol": str(replay["symbol"]),
        "market_date": str(replay["market_date"]),
        "timeframe": str(replay["timeframe"]),
        "parameters": asdict(rules),
        "readings": generate_pressure_readings(replay["bars"], rules),
    }


def write_pressure_gauge_session(path: Path, session: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
