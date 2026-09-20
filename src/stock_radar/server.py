"""Local-only static server for the StockRadar replay dashboard."""

from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Any


def make_radar_handler(root: Path, monitoring: Any | None = None):
    class RadarHandler(SimpleHTTPRequestHandler):
        def __init__(self, *handler_args, **handler_kwargs):
            super().__init__(*handler_args, directory=str(root), **handler_kwargs)

        def log_message(self, format, *log_args):
            pass

        def do_GET(self) -> None:
            if self.path.startswith("/api/monitoring"):
                if monitoring is None:
                    self._write_json(503, {"enabled": False, "state": "UNAVAILABLE", "last_error": "此 Web Server 不支援監控控制。"})
                else:
                    self._write_json(200, monitoring.status())
                return

            if self.path.startswith("/api/contract"):
                from urllib.parse import parse_qs, urlparse
                from stock_radar.tw_stocks import fetch_online_stock_info, lookup_stock_name

                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                symbol = params.get("symbol", [""])[0].strip()

                watchlist_path = root / "data" / "watchlist.json"
                name = None
                ref_price = 0.0
                limit_up = 0.0
                disposition = None

                # 1. Read existing watchlist configuration
                if watchlist_path.exists():
                    try:
                        wl_data = json.loads(watchlist_path.read_text(encoding="utf-8-sig"))
                        raw_name = wl_data.get("names", {}).get(symbol)
                        # Do not keep fallback placeholder names
                        if raw_name and not raw_name.startswith(f"個股 {symbol}"):
                            name = raw_name
                        if symbol in wl_data.get("references", {}):
                            ref_price = float(wl_data["references"][symbol])
                        if symbol in wl_data.get("limit_up", {}):
                            limit_up = float(wl_data["limit_up"][symbol])
                        if symbol in wl_data.get("dispositions", {}):
                            disposition = wl_data["dispositions"][symbol]
                    except Exception:
                        pass

                # 2. Check live snapshot if available (often contains reference and disposition)
                live_file = root / "data" / "live" / f"{symbol}.json"
                if live_file.exists():
                    try:
                        live_data = json.loads(live_file.read_text(encoding="utf-8"))
                        if not disposition and live_data.get("disposition"):
                            disposition = live_data["disposition"]
                        if ref_price == 0.0:
                            first_bar = (live_data.get("bars") or [None])[0]
                            if first_bar and first_bar.get("open"):
                                ref_price = float(first_bar["open"])
                    except Exception:
                        pass

                # 3. If name or price is missing, fetch real-time from TWSE/TPEx online API
                if not name or ref_price == 0.0:
                    online_info = fetch_online_stock_info(symbol)
                    if online_info:
                        if not name and online_info.get("name"):
                            name = online_info["name"]
                        if ref_price == 0.0 and online_info.get("reference", 0.0) > 0:
                            ref_price = online_info["reference"]
                        if limit_up == 0.0 and online_info.get("limit_up", 0.0) > 0:
                            limit_up = online_info["limit_up"]

                # 4. Fallback to dictionary lookup
                if not name:
                    name = lookup_stock_name(symbol)

                payload = {
                    "symbol": symbol,
                    "name": name,
                    "reference": ref_price,
                    "limit_up": limit_up,
                    "disposition": disposition,
                }
                self._write_json(200, payload)
                return

            super().do_GET()

        def do_POST(self) -> None:
            if self.path == "/api/monitoring":
                if monitoring is None:
                    self._write_json(503, {"enabled": False, "state": "UNAVAILABLE", "last_error": "此 Web Server 不支援監控控制。"})
                    return
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                    enabled = payload.get("enabled")
                    if not isinstance(enabled, bool):
                        raise ValueError("enabled 必須是布林值。")
                    self._write_json(200, monitoring.start() if enabled else monitoring.stop())
                except (ValueError, json.JSONDecodeError) as exc:
                    self._write_json(400, {"status": "error", "message": str(exc)})
                return

            if self.path == "/api/watchlist":
                content_length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_length).decode("utf-8")
                try:
                    data = json.loads(raw_body)
                    watchlist_path = root / "data" / "watchlist.json"
                    watchlist_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    existing = {}
                    if watchlist_path.exists():
                        try:
                            existing = json.loads(watchlist_path.read_text(encoding="utf-8-sig"))
                        except Exception:
                            pass
                    
                    existing_symbols = data.get("symbols", existing.get("symbols", []))
                    existing_names = {**existing.get("names", {}), **data.get("names", {})}
                    existing_refs = {**existing.get("references", {}), **data.get("references", {})}
                    existing_limits = {**existing.get("limit_up", {}), **data.get("limit_up", {})}
                    existing_disps = {**existing.get("dispositions", {}), **data.get("dispositions", {})}
                    
                    updated = {
                        "symbols": existing_symbols,
                        "names": existing_names,
                        "references": existing_refs,
                        "limit_up": existing_limits,
                        "dispositions": existing_disps,
                    }
                    watchlist_path.write_text(json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8")

                    self._write_json(200, {"status": "ok", "watchlist": updated})
                    return
                except Exception as e:
                    self._write_json(400, {"status": "error", "message": str(e)})
                    return

            self.send_response(404)
            self.end_headers()

        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return RadarHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve StockRadar locally.")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]

    handler_cls = make_radar_handler(root)
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_cls)
    if sys.stdout is not None:
        print(f"STOCK_RADAR_SERVER=http://127.0.0.1:{args.port}/web/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
