"""Local Windows Toast delivery for already-confirmed candidate events.

This module only formats and delivers events generated elsewhere.  It does not
connect to Shioaji, infer a signal, place an order, or retain credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ToastMessage:
    event_key: str
    title: str
    body: str


class ToastSink(Protocol):
    def show(self, message: ToastMessage) -> None: ...


class WindowsToastSink:
    """Use winotify so this unpackaged local Python app has a Toast identity."""

    def __init__(self, app_id: str = "StockRadar") -> None:
        self.app_id = app_id

    def show(self, message: ToastMessage) -> None:
        try:
            from winotify import Notification
        except ModuleNotFoundError as exc:
            raise RuntimeError("winotify is required for local Windows Toast delivery") from exc
        Notification(app_id=self.app_id, title=message.title, msg=message.body).show()


class OncePerEventDispatcher:
    """De-duplicate while the live collector remains running."""

    def __init__(self, sink: ToastSink) -> None:
        self.sink = sink
        self._sent: set[str] = set()

    def dispatch(self, message: ToastMessage) -> bool:
        if message.event_key in self._sent:
            return False
        self.sink.show(message)
        self._sent.add(message.event_key)
        return True


def candidate_event_to_toast(symbol: str, event: Mapping[str, Any]) -> ToastMessage:
    """Render an explainable alert without directing the user to trade."""

    kind = str(event["kind"])
    event_key = f"{symbol}|{event['timestamp']}|{kind}"
    is_invalidated = kind == "EXIT_CANDIDATE_TRIGGERED"
    title = f"{symbol}｜{'突破候選失效' if is_invalidated else '放量突破候選'}"
    body = (
        f"收盤 {float(event['close']):.1f}；失效價 {float(event['invalidation_price']):.1f}；"
        f"VWAP {float(event['vwap']):.1f}。"
        if is_invalidated
        else f"收盤 {float(event['close']):.1f} 突破 {float(event['breakout_level']):.1f}；"
        f"量比 {float(event['volume_ratio']):.2f}x；失效價 {float(event['invalidation_price']):.1f}。"
    )
    return ToastMessage(event_key=event_key, title=title, body=body)
