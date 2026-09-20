"""Generate the checked-in signal observations for the bundled replay data."""

from __future__ import annotations

import json
from pathlib import Path

from .signals import build_signal_session, write_signal_session


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    replay_path = project_root / "data" / "replays" / "3324_2026-08-28_1m.json"
    output_path = project_root / "data" / "signals" / "3324_2026-08-28_1m.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    session = build_signal_session(replay)
    write_signal_session(output_path, session)
    print("SIGNAL_EXPORT_OK")
    print(f"EVENT_COUNT={len(session['events'])}")
    print(f"DESTINATION={output_path}")


if __name__ == "__main__":
    main()
