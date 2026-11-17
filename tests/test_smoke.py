"""End-to-end HTTP smoke checks for all three standalone services.

No third-party libraries or external network connections are required.
Each application uses a new temporary SQLite directory.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SERVICES = {
    "site": ("Сайт", "server.py", "OBSIDIAN_DATA_DIR", "OBSIDIAN_PORT", "/health"),
    "forum": ("Форум", "app.py", "OBFORUM_DATA_DIR", "OBFORUM_PORT", "/health"),
    "wiki": ("Вики", "app.py", "OBWIKI_DATA_DIR", "OBWIKI_PORT", "/api/stats"),
}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get(url):
    with urlopen(url, timeout=2) as response:
        return response.status, dict(response.headers), response.read()


class ServiceSmokeTest(unittest.TestCase):
    def test_site_forum_wiki_start_and_serve_http(self):
        for name, (folder, script, data_key, port_key, health) in SERVICES.items():
            with self.subTest(service=name), tempfile.TemporaryDirectory() as temp:
                env = os.environ.copy()
                port = free_port()
                env[data_key] = str(Path(temp) / "database")
                env[port_key] = str(port)
                env.pop("OBSIDIAN_BIND", None)
                env.pop("OBFORUM_BIND", None)
                env.pop("OBWIKI_BIND", None)
                env.pop("OBSIDIAN_SECURE_COOKIES", None)
                env.pop("OBFORUM_SECURE_COOKIE", None)
                env.pop("OBWIKI_SECURE_COOKIE", None)
                proc = subprocess.Popen(
                    [sys.executable, script],
                    cwd=ROOT / folder,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                )
                base = f"http://127.0.0.1:{port}"
                try:
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        self.assertIsNone(proc.poll(), f"{name} exited early: {proc.returncode}")
                        try:
                            status, _, raw = get(base + health)
                            if status == 200:
                                data = json.loads(raw)
                                self.assertTrue(
                                    data.get("ok") is True or data.get("brand") == "OBSIDIAN RUSSIA",
                                    f"Unexpected health response from {name}: {data}",
                                )
                                break
                        except (URLError, OSError, TimeoutError):
                            time.sleep(0.2)
                    else:
                        self.fail(f"{name} did not start within 20 seconds")

                    status, headers, html = get(base + "/")
                    self.assertEqual(status, 200)
                    self.assertIn(b"OBSIDIAN", html)
                    self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
                    self.assertIn("Content-Security-Policy", headers)

                    status, _, css = get(base + "/static/style.css")
                    self.assertEqual(status, 200)
                    self.assertGreater(len(css), 100)

                    if name == "site":
                        status, _, response = get(base + "/api/status")
                        self.assertEqual(status, 200)
                        self.assertIn("servers", json.loads(response))
                    if name == "wiki":
                        status, _, response = get(base + "/api/stats")
                        self.assertEqual(status, 200)
                        self.assertIn("categories", json.loads(response))

                finally:
                    if proc.poll() is None:
                        proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()


if __name__ == "__main__":
    unittest.main()
