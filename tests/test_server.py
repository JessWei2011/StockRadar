from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from stock_radar.server import make_radar_handler


class ServerWatchlistTests(unittest.TestCase):
    def test_watchlist_api_get_and_post(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            handler_cls = make_radar_handler(root, None)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
            port = server.server_address[1]
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()

            try:
                # 1. Test GET empty
                url = f"http://127.0.0.1:{port}/api/watchlist"
                with urlopen(url) as resp:
                    self.assertEqual(resp.status, 200)
                    data = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual([], data.get("symbols"))

                # 2. Test POST symbols and thresholds
                payload = {
                    "symbols": ["2330", "2317"],
                    "thresholds": {"2330": 10},
                }
                req = Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(req) as resp:
                    self.assertEqual(resp.status, 200)
                    res = json.loads(resp.read().decode("utf-8"))
                    wl = res["watchlist"]
                    self.assertEqual(["2330", "2317"], wl["symbols"])
                    self.assertEqual("台積電", wl["names"]["2330"])
                    self.assertEqual(10, wl["thresholds"]["2330"])

                # 3. Test GET after update
                with urlopen(url) as resp:
                    self.assertEqual(resp.status, 200)
                    data = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(["2330", "2317"], data.get("symbols"))
                    self.assertEqual(10, data["thresholds"]["2330"])

            finally:
                server.shutdown()
                server.server_close()
