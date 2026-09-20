import json
from pathlib import Path

symbols = {'2455': '全新', '3324': '雙鴻', '3406': '玉晶光', '3450': '聯鈞', '4958': '臻鼎-KY'}
replays_dir = Path('c:/Code/Python/Cooperation/apps/StockRadar/data/replays')

for sym, name in symbols.items():
    p = replays_dir / f'{sym}_2026-09-01_1m.json'
    if p.is_file():
        data = json.loads(p.read_text(encoding='utf-8'))
        bars = data.get('bars', [])
        if bars:
            first_bar = bars[0]
            last_bar = bars[-1]
            high_p = max(b['high'] for b in bars)
            low_p = min(b['low'] for b in bars)
            total_vol = sum(b['volume'] for b in bars)
            chg = ((last_bar['close'] - first_bar['open']) / first_bar['open']) * 100
            print(f'{sym} {name} | Open: {first_bar["open"]} | High: {high_p} | Low: {low_p} | Close: {last_bar["close"]} ({chg:+.2f}%) | Vol: {total_vol} shares')