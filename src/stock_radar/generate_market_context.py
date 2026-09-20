"""Generate the checked-in replay context consumed by the Dashboard."""
from __future__ import annotations

import json
from pathlib import Path

from .market_context import build_market_context_session, write_market_context_session


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    replay = json.loads(
        (root / "data/replays/3324_2026-08-28_1m.json").read_text(encoding="utf-8")
    )
    event_session = json.loads(
        (root / "data/market-events/3324_2026-08-28_1m.json").read_text(encoding="utf-8")
    )
    session = build_market_context_session(replay, event_session["events"])
    output = root / "data/market-context/3324_2026-08-28_1m.json"
    write_market_context_session(output, session)
    print(f"MARKET_CONTEXT_EXPORT_OK\nCONTEXT_COUNT={len(session['contexts'])}")


if __name__ == "__main__":
    main()
