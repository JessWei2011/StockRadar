"""Evidence-based detector for potential low-zone accumulation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class AccumulationParameters:
    low_zone_minutes: int = 60
    flow_minutes: int = 5
    baseline_minutes: int = 15
    low_zone_max: float = 0.40
    min_large_volume: int = 10
    min_large_buys: int = 2
    min_large_sells: int = 2
    min_buy_ratio: float = 0.52
    min_absorption_sell_ratio: float = 0.35
    max_absorption_drop_pct: float = 0.003
    support_lookback_bars: int = 5
    breakout_window: int = 20
    breakout_volume_multiple: float = 1.5


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _recent(records: Sequence[Mapping[str, Any]], *, now: datetime, minutes: int) -> list[Mapping[str, Any]]:
    cutoff = now - timedelta(minutes=minutes)
    return [record for record in records if cutoff <= _timestamp(str(record["timestamp"])) <= now]


def _percentile(values: Sequence[int], percentile: float) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    return ordered[max(0, ceil(len(ordered) * percentile) - 1)]


def _price(record: Mapping[str, Any]) -> float | None:
    value = record.get("price")
    return float(value) if value is not None else None


def _session_vwap(bars: Sequence[Mapping[str, Any]]) -> float | None:
    value = 0.0
    volume = 0.0
    for bar in bars:
        bar_volume = float(bar.get("volume", 0) or 0)
        if bar_volume <= 0 or not all(key in bar for key in ("high", "low", "close")):
            continue
        typical = (float(bar["high"]) + float(bar["low"]) + float(bar["close"])) / 3.0
        value += typical * bar_volume
        volume += bar_volume
    return value / volume if volume > 0 else None


def detect_potential_accumulation(
    bars: Sequence[Mapping[str, Any]],
    at_ask_prints: Sequence[Mapping[str, Any]],
    at_bid_prints: Sequence[Mapping[str, Any]],
    latest_tick: Mapping[str, Any] | None,
    parameters: AccumulationParameters = AccumulationParameters(),
) -> dict[str, Any]:
    """Return evidence, never an assertion about a buyer's identity or intent."""
    if latest_tick is None:
        return {"available": False, "active": False, "summary": "等待逐筆成交資料。"}
    now = _timestamp(str(latest_tick["timestamp"]))
    price = float(latest_tick["price"])
    zone_bars = _recent(bars, now=now, minutes=parameters.low_zone_minutes)
    if len(zone_bars) < 20:
        return {"available": False, "active": False, "summary": "低檔區間資料不足。"}
    zone_low = min(float(bar["low"]) for bar in zone_bars)
    zone_high = max(float(bar["high"]) for bar in zone_bars)
    price_position = (price - zone_low) / (zone_high - zone_low) if zone_high > zone_low else 0.5
    flow_cutoff = now - timedelta(minutes=parameters.flow_minutes)
    baseline = [
        record
        for record in _recent([*at_ask_prints, *at_bid_prints], now=now, minutes=parameters.baseline_minutes)
        if _timestamp(str(record["timestamp"])) < flow_cutoff
    ]
    large_threshold = max(parameters.min_large_volume, _percentile([int(record["volume"]) for record in baseline], 0.90))
    buys = _recent(at_ask_prints, now=now, minutes=parameters.flow_minutes)
    sells = _recent(at_bid_prints, now=now, minutes=parameters.flow_minutes)
    buy_volume = sum(int(record["volume"]) for record in buys)
    sell_volume = sum(int(record["volume"]) for record in sells)
    total_volume = buy_volume + sell_volume
    buy_ratio = buy_volume / total_volume if total_volume else 0.0
    large_buys = [record for record in buys if int(record["volume"]) >= large_threshold]
    large_sells = [record for record in sells if int(record["volume"]) >= large_threshold]
    hold_bars = _recent(bars, now=now, minutes=parameters.flow_minutes)
    reference_bars = list(hold_bars[-parameters.support_lookback_bars :])
    hold_floor = min((float(bar["low"]) for bar in reference_bars), default=price)
    flow_records = sorted([*buys, *sells], key=lambda record: str(record["timestamp"]))
    priced_records = [record for record in flow_records if _price(record) is not None]
    start_price = _price(priced_records[0]) if priced_records else None
    price_change_pct = (
        (price / start_price - 1.0)
        if start_price is not None and start_price > 0
        else None
    )
    low_zone = price_position <= parameters.low_zone_max
    sustained_buying = buy_volume > sell_volume and buy_ratio >= parameters.min_buy_ratio
    repeated_large_buys = len(large_buys) >= parameters.min_large_buys
    holds = price >= hold_floor
    sell_ratio = sell_volume / total_volume if total_volume else 0.0
    price_resilient = price_change_pct is not None and price_change_pct >= -parameters.max_absorption_drop_pct
    sell_absorbed = (
        len(large_sells) >= parameters.min_large_sells
        and sell_ratio >= parameters.min_absorption_sell_ratio
        and price_resilient
        and holds
    )

    recent_lows = [float(bar["low"]) for bar in reference_bars]
    midpoint = len(recent_lows) // 2
    higher_lows = (
        midpoint > 0
        and len(recent_lows) - midpoint > 0
        and min(recent_lows[midpoint:]) > min(recent_lows[:midpoint])
    )

    vwap = _session_vwap(bars)
    prior_bars = list(bars[-parameters.breakout_window :])
    breakout_level = max((float(bar["high"]) for bar in prior_bars), default=price)
    prior_volumes = [float(bar.get("volume", 0) or 0) for bar in prior_bars[:-1]]
    positive_prior_volumes = [item for item in prior_volumes if item > 0]
    baseline_bar_volume = (
        sorted(positive_prior_volumes)[len(positive_prior_volumes) // 2]
        if positive_prior_volumes
        else 0.0
    )
    latest_bar_volume = float(prior_bars[-1].get("volume", 0) or 0) if prior_bars else 0.0
    breakout_volume_ratio = latest_bar_volume / baseline_bar_volume if baseline_bar_volume > 0 else 0.0
    above_vwap = vwap is not None and price >= vwap
    breakout = price > breakout_level
    volume_expanding = breakout_volume_ratio >= parameters.breakout_volume_multiple

    absorption_confirmed = low_zone and holds and (
        sell_absorbed or (sustained_buying and repeated_large_buys)
    )
    attack_confirmed = (
        above_vwap
        and breakout
        and volume_expanding
        and sustained_buying
        and repeated_large_buys
    )
    watching = low_zone and holds and (bool(large_buys) or sell_absorbed or higher_lows)
    active = absorption_confirmed or attack_confirmed
    stage = "ATTACK_CONFIRMED" if attack_confirmed else "ABSORPTION" if absorption_confirmed else "WATCHING" if watching else "NONE"
    return {
        "available": True,
        "watching": watching,
        "active": active,
        "stage": stage,
        "timestamp": latest_tick["timestamp"],
        "price": price,
        "price_position": round(price_position, 4),
        "large_threshold": large_threshold,
        "large_buy_count": len(large_buys),
        "large_sell_count": len(large_sells),
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "net_volume": buy_volume - sell_volume,
        "buy_ratio": round(buy_ratio, 4),
        "sell_ratio": round(sell_ratio, 4),
        "price_change_pct": round(price_change_pct, 6) if price_change_pct is not None else None,
        "hold_floor": hold_floor,
        "vwap": round(vwap, 4) if vwap is not None else None,
        "breakout_level": breakout_level,
        "breakout_volume_ratio": round(breakout_volume_ratio, 4),
        "conditions": {
            "low_zone": low_zone,
            "sustained_buying": sustained_buying,
            "repeated_large_buys": repeated_large_buys,
            "holds": holds,
            "sell_absorbed": sell_absorbed,
            "higher_lows": higher_lows,
            "above_vwap": above_vwap,
            "breakout": breakout,
            "volume_expanding": volume_expanding,
            "attack_confirmed": attack_confirmed,
        },
        "summary": (
            f"階段 {stage}｜區間位置 {price_position:.0%}｜5分淨主動量 {buy_volume - sell_volume:+d}｜"
            f"大單 {len(large_buys)} 筆（門檻 {large_threshold}）｜"
            f"{'賣壓已吸收' if sell_absorbed else '賣壓未確認吸收'}｜"
            f"{'站上VWAP' if above_vwap else '未站上VWAP'}"
        ),
    }
