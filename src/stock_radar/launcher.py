"""Launch the local dashboard without implicitly connecting to market data."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import time
import webbrowser

from .monitoring import MonitoringController
from .server import make_radar_handler


def start_background_server(root: Path, monitoring: MonitoringController, port: int = 8765):
    from http.server import ThreadingHTTPServer

    handler_cls = make_radar_handler(root, monitoring)
    ThreadingHTTPServer.allow_reuse_address = True
    server = None
    for attempt in range(10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
            break
        except OSError:
            if attempt < 9:
                time.sleep(0.5)
            else:
                raise
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> int:
    # Ensure UTF-8 output encoding across Windows consoles
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if sys.stderr is not None:
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    root = Path(__file__).resolve().parents[2]
    log_dir = root / "data"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Redirect stdout and stderr if headless (pythonw)
    if sys.stdout is None or sys.stderr is None:
        log_file = open(log_dir / "radar.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file

    import argparse
    parser = argparse.ArgumentParser(description="Unified launcher for StockRadar")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto open browser window")
    parser.add_argument("--start-monitoring", action="store_true", help="Start market monitoring immediately")
    args, _ = parser.parse_known_args()

    port = 8765
    monitoring = MonitoringController(root)
    try:
        server = start_background_server(root, monitoring, port)
    except OSError:
        print(f"[StockRadar] Web Server already exists on port {port}; keeping the existing service untouched.")
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{port}/web/live.html")
        return 0

    pid_file = log_dir / "radar.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    print(f"[StockRadar] Web Server running on http://127.0.0.1:{port}/web/live.html")

    if args.start_monitoring:
        print("[StockRadar] Starting market monitoring immediately...")
        monitoring.start()
    else:
        print("[StockRadar] Market monitoring is disabled until the user presses 開始監控.")

    if not args.no_browser:
        time.sleep(0.5)
        webbrowser.open(f"http://127.0.0.1:{port}/web/live.html")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        monitoring.stop()
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        if pid_file.is_file() and pid_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
            try:
                pid_file.unlink()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
