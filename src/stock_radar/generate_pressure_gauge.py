"""Generate the checked-in completed-bar pressure-gauge replay data."""
from __future__ import annotations

import json
from pathlib import Path

from .pressure_gauge import build_pressure_gauge_session, write_pressure_gauge_session


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    replay = json.loads((root / "data/replays/3324_2026-08-28_1m.json").read_text(encoding="utf-8"))
    session = build_pressure_gauge_session(replay)
    output = root / "data/pressure-gauge/3324_2026-08-28_1m.json"
    write_pressure_gauge_session(output, session)
    print(f"PRESSURE_GAUGE_EXPORT_OK\nREADING_COUNT={len(session['readings'])}")


if __name__ == "__main__":
    main()
