"""Generate the candidate-event replay consumed by the Dashboard."""
from __future__ import annotations

import json
from pathlib import Path

from .candidate_events import build_candidate_session, write_candidate_session


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    replay = json.loads((root / "data/replays/3324_2026-08-28_1m.json").read_text(encoding="utf-8"))
    session = build_candidate_session(replay)
    output = root / "data/candidate-events/3324_2026-08-28_1m.json"
    write_candidate_session(output, session)
    print(f"CANDIDATE_EVENT_EXPORT_OK\nEVENT_COUNT={len(session['events'])}")


if __name__ == "__main__":
    main()
