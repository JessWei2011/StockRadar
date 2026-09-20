"""Lifecycle control for the optional Shioaji live-monitoring session."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
from pathlib import Path
import threading
import time
from typing import Any
from zoneinfo import ZoneInfo

from .live_collector import main as run_live_collector


TAIPEI = ZoneInfo("Asia/Taipei")
CollectorRunner = Callable[[threading.Event, Callable[[str], None]], int]


class MonitoringController:
    """Own the one live session; the dashboard never connects to Shioaji itself."""

    def __init__(self, root: Path, *, runner: CollectorRunner = run_live_collector) -> None:
        self._runner = runner
        self._status_path = root / "data" / "monitoring-status.json"
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = "DISABLED"
        self._enabled = False
        self._last_error: str | None = None
        self._updated_at = ""
        # Starting the local web service must never implicitly reconnect to the API.
        self._persist_locked()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._payload_locked()

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self._payload_locked()
            self._stop_event = threading.Event()
            self._enabled = True
            self._state = "CONNECTING"
            self._last_error = None
            self._persist_locked()
            self._thread = threading.Thread(target=self._run, name="stock-radar-collector", daemon=True)
            self._thread.start()
            return self._payload_locked()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._enabled = False
            self._stop_event.set()
            self._state = "STOPPING" if self._thread and self._thread.is_alive() else "DISABLED"
            self._persist_locked()
            return self._payload_locked()

    def _run(self) -> None:
        retry_delay = 1.0
        while not self._stop_event.is_set():
            try:
                self._runner(self._stop_event, self._set_stream_state)
                if not self._stop_event.is_set():
                    raise RuntimeError("行情收集器意外結束。")
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                with self._lock:
                    self._state = "RECONNECTING"
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    self._persist_locked()
                self._stop_event.wait(retry_delay)
                retry_delay = min(retry_delay * 2, 30.0)
            else:
                retry_delay = 1.0

        with self._lock:
            self._state = "DISABLED"
            self._enabled = False
            self._persist_locked()

    def _set_stream_state(self, state: str) -> None:
        with self._lock:
            if not self._stop_event.is_set():
                self._state = state
                self._persist_locked()

    def _payload_locked(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "state": self._state,
            "updated_at": self._updated_at,
            "last_error": self._last_error,
        }

    def _persist_locked(self) -> None:
        self._updated_at = datetime.now(TAIPEI).isoformat(timespec="seconds")
        self._status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._status_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._payload_locked(), ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self._status_path)
