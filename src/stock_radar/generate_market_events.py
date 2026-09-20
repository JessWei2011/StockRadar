from __future__ import annotations
import json
from pathlib import Path
from .market_events import build_market_event_session, write_market_event_session
root=Path(__file__).resolve().parents[2]
replay=json.loads((root/'data/replays/3324_2026-08-28_1m.json').read_text(encoding='utf-8'))
session=build_market_event_session(replay)
output=root/'data/market-events/3324_2026-08-28_1m.json'
write_market_event_session(output, session)
print(f'MARKET_EVENT_EXPORT_OK\nEVENT_COUNT={len(session["events"])}')
