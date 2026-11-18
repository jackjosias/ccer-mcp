"""Viewer tests ensure browser shows frames without racing HTTP responses."""
import threading
import unittest
from urllib.request import urlopen
from ccer.isolated_session import viewer

class IsolatedViewerTests(unittest.TestCase):
    def test_refresh_waits_for_previous_frame(self):
        server = viewer({}, None, "viewer-test-token")
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/?pass=viewer-test-token"
            with urlopen(url, timeout=5) as response:
                self.assertEqual(response.status, 200)
                html = response.read().decode("utf-8")
            self.assertIn("img.onload=()=>setTimeout(paint,1200)", html)
            self.assertIn("img.onerror=()=>setTimeout(paint,3000)", html)
            self.assertNotIn("setInterval(paint", html)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
if __name__ == "__main__":
    unittest.main()
