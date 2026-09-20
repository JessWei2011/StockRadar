"""Causal, explainable candidate-entry and invalidation events.

These events ask the user to inspect the market; they never issue orders or
claim that a trade will succeed.  Every calculation receives completed minute
bars only and every event records its own invalidation price.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence


ENTRY_CANDIDATE_TRIGGERED = "ENTRY_CANDIDATE_TRIGGERED"
EXIT_CANDIDATE_TRIGGERED = "EXIT_CANDIDATE_TRIGGERED"


@dataclass(frozen=True)
class CandidateParameters:
    breakout_window: int = 20
    volume_multiple: float = 2.0
    require_close_above_vwap: bool = True

    def __post_init__(self) -> None:
        if self.breakout_window < 1:
            raise ValueError("breakout_window must be positive")
        if self.volume_multiple <= 0:
            raise ValueError("volume_multiple must be positive")


def _number(bar: Mapping[str, Any], key: str) -> float:
    return float(bar[key])


def _event(
    bar: Mapping[str, Any],
    *,
    kind: str,
    title: str,
    summary: str,
    breakout_level: float,
    invalidation_price: float,
    volume_ratio: float,
    vwap: float,
) -> dict[str, Any]:
    return {
        "timestamp": str(bar["timestamp"]),
        "kind": kind,
        "title": title,
        "summary": summary,
        "close": round(_number(bar, "close"), 2),
        "breakout_level": round(breakout_level, 2),
        "invalidation_price": round(invalidation_price, 2),
        "volume_ratio": round(volume_ratio, 2),
        "vwap": round(vwap, 2),
    }


def generate_candidate_events(
    bars: Sequence[Mapping[str, Any]],
    parameters: CandidateParameters | None = None,
) -> list[dict[str, Any]]:
    """Return state transitions, not a repetitive per-bar signal stream."""

    rules = parameters or CandidateParameters()
    events: list[dict[str, Any]] = []
    cumulative_value = 0.0
    cumulative_volume = 0.0
    active: dict[str, float] | None = None

    for index, bar in enumerate(bars):
        high = _number(bar, "high")
        low = _number(bar, "low")
        close = _number(bar, "close")
        volume = _number(bar, "volume")
        typical_price = (high + low + close) / 3
        cumulative_value += typical_price * volume
        cumulative_volume += volume
        vwap = cumulative_value / cumulative_volume if cumulative_volume > 0 else close

        if active is not None:
            if close < active["invalidation_price"]:
                events.append(
                    _event(
                        bar,
                        kind=EXIT_CANDIDATE_TRIGGERED,
                        title="突破候選失效",
                        summary=(
                            f"收盤跌回候選失效價 {active['invalidation_price']:.1f} 下方；"
                            "先前的放量突破條件不再成立。"
                        ),
                        breakout_level=active["breakout_level"],
                        invalidation_price=active["invalidation_price"],
                        volume_ratio=volume / active["baseline_volume"],
                        vwap=vwap,
                    )
                )
                active = None
            continue

        if index < rules.breakout_window:
            continue

        prior = bars[index - rules.breakout_window : index]
        baseline_volume = float(median(_number(previous, "volume") for previous in prior))
        if baseline_volume <= 0:
            continue
        breakout_level = max(_number(previous, "high") for previous in prior)
        volume_ratio = volume / baseline_volume
        vwap_aligned = close >= vwap if rules.require_close_above_vwap else True
        if close > breakout_level and volume_ratio >= rules.volume_multiple and vwap_aligned:
            active = {
                "breakout_level": breakout_level,
                "invalidation_price": breakout_level,
                "baseline_volume": baseline_volume,
            }
            events.append(
                _event(
                    bar,
                    kind=ENTRY_CANDIDATE_TRIGGERED,
                    title="放量突破候選",
                    summary=(
                        f"收盤突破前 {rules.breakout_window} 根高點，量比 {volume_ratio:.2f} 倍，"
                        f"且收在當日 VWAP {vwap:.1f} 之上。"
                    ),
                    breakout_level=breakout_level,
                    invalidation_price=breakout_level,
                    volume_ratio=volume_ratio,
                    vwap=vwap,
                )
            )
    return events


def build_candidate_session(
    replay: Mapping[str, Any], parameters: CandidateParameters | None = None
) -> dict[str, Any]:
    rules = parameters or CandidateParameters()
    bars = replay.get("bars")
    if not isinstance(bars, list):
        raise ValueError("Replay data must contain a bars list")
    return {
        "schema_version": "1.0",
        "source_replay": str(replay.get("source", "unknown")),
        "symbol": str(replay["symbol"]),
        "market_date": str(replay["market_date"]),
        "timeframe": str(replay["timeframe"]),
        "parameters": asdict(rules),
        "events": generate_candidate_events(bars, rules),
    }


def write_candidate_session(path: Path, session: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
