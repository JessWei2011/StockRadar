# StockRadar

StockRadar 是僅讀取行情的台股盤中訊號雷達。第一版監控 3–5 檔股票，協助使用者發現量價結構、候選訊號、收 K 確認與失效條件；不提供下單功能。

## 設定檔 (.env)

專案根目錄下的 `.env` 包含連線 Shioaji 行情所須的金鑰：

```env
SJ_API_KEY=...
SJ_SEC_KEY=...
SJ_PRODUCTION=true
```

## 快速啟動

- 雙擊執行 `start_mini_hud.bat`：靜默啟動後端並開啟右側獨立常駐 Mini HUD 看盤視窗。
- 或以手動命令列啟動：

```powershell
$env:PYTHONPATH = 'src;.deps'
python -m stock_radar.launcher --start-monitoring
```

瀏覽器開啟 `http://127.0.0.1:8765/web/live.html` 或 `http://127.0.0.1:8765/web/mini.html`。
