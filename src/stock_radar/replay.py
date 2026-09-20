"""Deterministic replay control for completed one-minute K-bars."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

ALLOWED_SPEEDS = frozenset({1, 5, 20})
BAR_SECONDS = 60


@dataclass
class ReplayController:
    """Emit one completed bar at a time, with a UI-friendly pause state."""

    session: Mapping[str, Any]
    speed: int = 1
    _cursor: int = field(default=0, init=False)
    _paused: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.speed not in ALLOWED_SPEEDS:
            raise ValueError(f"不支援的回放倍率：{self.speed}x")
        if self.session.get("timeframe") != "1m":
            raise ValueError("目前只支援一分 K 回放。")
        if not isinstance(self.session.get("bars"), list):
            raise ValueError("replay session 缺少 bars 陣列。")

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_finished(self) -> bool:
        return self._cursor >= len(self.session["bars"])

    @property
    def delay_seconds(self) -> float:
        return BAR_SECONDS / self.speed

    @property
    def progress(self) -> tuple[int, int]:
        return self._cursor, len(self.session["bars"])

    def set_speed(self, speed: int) -> None:
        if speed not in ALLOWED_SPEEDS:
            raise ValueError(f"不支援的回放倍率：{speed}x")
        self.speed = speed

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def next_bar(self) -> Mapping[str, Any] | None:
        """Return the next completed bar, or None while paused/finished."""
        if self._paused or self.is_finished:
            return None
        bar = self.session["bars"][self._cursor]
        self._cursor += 1
        return bar

    def bars(self) -> Iterator[Mapping[str, Any]]:
        """Yield remaining bars for non-realtime test and export callers."""
        while not self.is_finished:
            bar = self.next_bar()
            if bar is None:
                return
            yield bar

    async def stream(self) -> Iterator[Mapping[str, Any]]:
        """Yield bars at the selected playback rate until paused or completed."""
        while not self.is_finished:
            bar = self.next_bar()
            if bar is None:
                await asyncio.sleep(0.05)
                continue
            yield bar
            if not self.is_finished:
                await asyncio.sleep(self.delay_seconds)
