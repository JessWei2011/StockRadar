"""Pure, explainable signal calculations for replayed minute bars."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence
import json


@dataclass(frozen=True)
class SignalParameters:
    structure_window: int = 5
    breakout_window: int = 20
    volume_multiple: float = 2.0
    reversal_close_position_max: float = 0.35

    def __post_init__(self) -> None:
        if self.structure_window < 2 or self.breakout_window < 1:
            raise ValueError("Signal windows must be positive and structure_window must be at least 2.")
        if self.volume_multiple <= 0:
            raise ValueError("volume_multiple must be positive.")
        if not 0 <= self.reversal_close_position_max <= 1:
            raise ValueError("reversal_close_position_max must be between 0 and 1.")


def _number(bar: Mapping[str, Any], name: str) -> float:
    return float(bar[name])


def _event(
    bar: Mapping[str, Any], signal: str, severity: str, reason: str, metrics: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "timestamp": str(bar["timestamp"]),
        "signal": signal,
        "severity": severity,
        "reason": reason,
        "metrics": dict(metrics),
    }


def generate_signal_events(
    bars: Sequence[Mapping[str, Any]], parameters: SignalParameters | None = None
) -> list[dict[str, Any]]:
    """Return observations that match the documented rules, without trading advice."""
    params = parameters or SignalParameters()
    events: list[dict[str, Any]] = []

    for index, bar in enumerate(bars):
        close = _number(bar, "close")
        volume = _number(bar, "volume")

        if index >= params.structure_window:
            recent = bars[index - params.structure_window + 1 : index + 1]
            high_non_decreasing = all(
                _number(later, "high") >= _number(earlier, "high")
                for earlier, later in zip(recent, recent[1:])
            )
            low_non_decreasing = all(
                _number(later, "low") >= _number(earlier, "low")
                for earlier, later in zip(recent, recent[1:])
            )
            prior_close = _number(bars[index - params.structure_window], "close")
            if high_non_decreasing and low_non_decreasing and close > prior_close:
                events.append(
                    _event(
                        bar,
                        "RISING_STRUCTURE",
                        "INFO",
                        f"最近 {params.structure_window} 根高低點未下移，收盤高於 {params.structure_window} 根前。",
                        {
                            "close": close,
                            "prior_close": prior_close,
                            "structure_window": params.structure_window,
                        },
                    )
                )

        if index < params.breakout_window:
            continue

        prior_bars = bars[index - params.breakout_window : index]
        prior_volumes = [_number(previous, "volume") for previous in prior_bars]
        baseline_volume = float(median(prior_volumes))
        if baseline_volume <= 0:
            continue
        volume_ratio = volume / baseline_volume
        prior_high = max(_number(previous, "high") for previous in prior_bars)

        if close > prior_high and volume_ratio >= params.volume_multiple:
            events.append(
                _event(
                    bar,
                    "VOLUME_BREAKOUT",
                    "WATCH",
                    f"收盤突破前 {params.breakout_window} 根最高價，量比 {volume_ratio:.2f}。",
                    {
                        "close": close,
                        "prior_high": prior_high,
                        "volume": volume,
                        "median_volume": baseline_volume,
                        "volume_ratio": round(volume_ratio, 4),
                    },
                )
            )

        high = _number(bar, "high")
        low = _number(bar, "low")
        opening = _number(bar, "open")
        bar_range = high - low
        if bar_range <= 0:
            continue
        close_position = (close - low) / bar_range
        if (
            volume_ratio >= params.volume_multiple
            and close < opening
            and close_position <= params.reversal_close_position_max
        ):
            events.append(
                _event(
                    bar,
                    "HIGH_VOLUME_REVERSAL",
                    "CAUTION",
                    f"爆量收黑且收盤位於本根振幅下方 {close_position:.0%}，量比 {volume_ratio:.2f}。",
                    {
                        "open": opening,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": volume,
                        "median_volume": baseline_volume,
                        "volume_ratio": round(volume_ratio, 4),
                        "close_position": round(close_position, 4),
                    },
                )
            )

    return events


def build_signal_session(
    replay: Mapping[str, Any], parameters: SignalParameters | None = None
) -> dict[str, Any]:
    """Build the stable signal-file contract from a historical replay session."""
    bars = replay.get("bars")
    if not isinstance(bars, list):
        raise ValueError("Replay data must contain a bars list.")
    params = parameters or SignalParameters()
    return {
        "schema_version": "1.0",
        "symbol": str(replay["symbol"]),
        "market_date": str(replay["market_date"]),
        "timeframe": str(replay["timeframe"]),
        "source_replay": str(replay.get("source", "unknown")),
        "parameters": asdict(params),
        "events": generate_signal_events(bars, params),
    }


def write_signal_session(path: Path, session: Mapping[str, Any]) -> None:
    """Write a UTF-8 signal session file without retaining any credentials."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
