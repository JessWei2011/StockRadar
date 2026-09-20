"""CLI entry point for the fixed historical replay dataset used in Phase 1."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .config import load_settings
from .historical import fetch_one_minute_session, write_session

SYMBOL = "3324"
MARKET_DATE = date(2026, 8, 28)


def main() -> int:
    destination = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "replays"
        / "3324_2026-08-28_1m.json"
    )
    try:
        session = fetch_one_minute_session(load_settings(), SYMBOL, MARKET_DATE)
        write_session(session, destination)
    except (RuntimeError, ValueError) as error:
        print(f"REPLAY_FETCH_FAILED={error}")
        return 2
    except Exception as error:
        print(f"REPLAY_FETCH_FAILED={type(error).__name__}")
        print("ACTION=Review the Shioaji historical-data response and connection state.")
        return 3
    print("REPLAY_FETCH_OK")
    print(f"BAR_COUNT={len(session['bars'])}")
    print(f"DESTINATION={destination.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
