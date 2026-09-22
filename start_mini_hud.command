#!/bin/bash
cd "$(dirname "$0")"

# 啟動後端服務（若尚未在執行）
if ! lsof -i :8765 >/dev/null 2>&1; then
    PYTHONPATH=src python3 -m stock_radar.launcher --no-browser >/dev/null 2>&1 &
    sleep 1
fi

# 開啟 Mini HUD 視窗
# 若有安裝 Chrome / Edge，可以 App 模式開啟獨立小視窗
if [ -d "/Applications/Google Chrome.app" ]; then
    open -na "Google Chrome" --args --app="http://127.0.0.1:8765/web/mini.html" --window-size=240,700
elif [ -d "/Applications/Microsoft Edge.app" ]; then
    open -na "Microsoft Edge" --args --app="http://127.0.0.1:8765/web/mini.html" --window-size=240,700
else
    open "http://127.0.0.1:8765/web/mini.html"
fi
