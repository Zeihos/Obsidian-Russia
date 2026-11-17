"""Live HTTP regressions for session revocation in site, forum and Wiki.

Every service uses an isolated temporary SQLite database and loopback port.
"""
import http.client
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]


def port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(p, path, method="GET", data=None, cookie=""):
    body = None if data is None else urlencode(data).encode("utf-8")
    headers = {}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if cookie:
        headers["Cookie"] = cookie
    connection = http.client.HTTPConnection("127.0.0.1", p, timeout=4)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        pairs = response.getheaders()
        return response.status, dict(pairs), raw, [
            v.split(";", 1)[0] for k, v in pairs if k.lower() == "set-cookie"
        ]
    finally:
        connection.close()


def csrf(html):
    match = re.search(rb'name="csrf"\s+value="([^"]+)"', html)
    if not match:
        raise AssertionError("CSRF field missing")
    return match.group(1).decode("ascii")


def cookie_of(jar, prefix):
    return next(x for x in jar if x.startswith(prefix + "="))


class StartedService:
    def __init__(self, name, folder, script, env):
        self.name = name
        self.folder = ROOT / folder
        self.script = script
        self.env = env
        self.process = None

    def __enter__(self):
        self.process = subprocess.Popen(
            [sys.executable, self.script],
            cwd=self.folder, env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        p = int(self.env[self.name])
        for _ in range(100):
            if self.process.poll() is not None:
                detail = self.process.stdout.read().decode("utf-8", "replace")[-4000:]
                raise AssertionError(f"{self.script} stopped: {detail}")
            try:
                status, _, _, _ = request(p, "/health" if self.script != "app.py" or self.folder.name != "Вики" else "/api/stats")
                if status == 200:
                    return self
            except OSError:
                pass
            time.sleep(0.15)
        raise AssertionError(f"{self.script} failed to start")

    def __exit__(self, *args):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            if self.process.stdout:
                self.process.stdout.close()


class SessionSecurityTest(unittest.TestCase):
    def test_site_and_forum_revoke_sessions(self):
        cases = (
            ("Сайт", "server.py", "OBSIDIAN_PORT", "OBSIDIAN_DATA_DIR", "or_session",
             {"username":"SiteUser","email":"siteuser@example.invalid",
              "password":"SitePassword123!","password2":"SitePassword123!"},
             {"identity":"SiteUser","password":"SitePassword123!"}),
            ("Форум", "app.py", "OBFORUM_PORT", "OBFORUM_DATA_DIR", "obforum_session",
             {"username":"ForumUser","email":"forumuser@example.invalid",
              "password":"ForumPassword123!","confirm":"ForumPassword123!"},
             {"identity":"ForumUser","password":"ForumPassword123!"}),
        )
        for folder, script, port_key, data_key, cookie_name, register, login in cases:
            with self.subTest(service=folder), tempfile.TemporaryDirectory() as temp:
                p = port()
                env = os.environ.copy()
                env[port_key] = str(p)
                env[data_key] = str(Path(temp) / "data")
                with StartedService(port_key, folder, script, env):
                    # First browser registers.
                    status, _, body, cookies = request(p, "/register")
                    self.assertEqual(status, 200)
                    anonymous = cookie_of(cookies, cookie_name)
                    status, _, _, cookies = request(
                        p, "/register", "POST",
                        {"csrf":csrf(body), **register}, anonymous,
                    )
                    self.assertEqual(status, 303)
                    first = cookie_of(cookies, cookie_name)

                    # Second browser logs into the same account.
                    status, _, body, cookies = request(p, "/login")
                    self.assertEqual(status, 200)
                    guest = cookie_of(cookies, cookie_name)
                    status, _, _, cookies = request(
                        p, "/login", "POST", {"csrf":csrf(body), **login}, guest,
                    )
                    self.assertEqual(status, 303)
                    second = cookie_of(cookies, cookie_name)

                    status, _, body, _ = request(p, "/account", cookie=first)
                    self.assertEqual(status, 200)
                    self.assertIn("Завершить другие сеансы".encode("utf-8"), body)
                    first_csrf = csrf(body)

                    # CSRF protects destructive session operations.
                    status, _, _, _ = request(
                        p, "/account/sessions/logout-all", "POST",
                        {"csrf":"invalid"}, first,
                    )
                    self.assertEqual(status, 400)
                    self.assertEqual(request(p, "/account", cookie=first)[0], 200)

                    status, _, _, _ = request(
                        p, "/account/sessions/close-others", "POST",
                        {"csrf":first_csrf}, first,
                    )
                    self.assertEqual(status, 303)
                    self.assertEqual(request(p, "/account", cookie=first)[0], 200)
                    status, headers, _, _ = request(p, "/account", cookie=second)
                    self.assertEqual(status, 303)
                    self.assertTrue(headers["Location"].startswith("/login"))

                    status, _, body, _ = request(p, "/account", cookie=first)
                    self.assertEqual(status, 200)
                    status, _, _, _ = request(
                        p, "/account/sessions/logout-all", "POST",
                        {"csrf":csrf(body)}, first,
                    )
                    self.assertEqual(status, 303)
                    self.assertEqual(request(p, "/account", cookie=first)[0], 303)

    def test_wiki_editor_revoke_sessions(self):
        with tempfile.TemporaryDirectory() as temp:
            p = port()
            env = os.environ.copy()
            env.update({"OBWIKI_PORT": str(p), "OBWIKI_DATA_DIR": str(Path(temp) / "data")})
            # Test fixtures are provisioned directly; authentication itself uses HTTP.
            setup = ("import db; db.init_db(); c=db.connect(); "
                     "c.execute('INSERT INTO users(username,pass_hash,role,created_at) "
                     "VALUES(?,?,?,?)', ('WikiAdmin', db.hash_password('WikiPassword123!'), "
                     "'admin', db.now())); c.commit(); c.close()")
            subprocess.run([sys.executable, "-c", setup], env=env,
                           cwd=ROOT / "Вики", check=True, capture_output=True)
            with StartedService("OBWIKI_PORT", "Вики", "app.py", env):
                active = []
                for _ in range(2):
                    status, _, body, cookies = request(p, "/login")
                    self.assertEqual(status, 200)
                    guest = cookie_of(cookies, "obwiki_guest")
                    status, headers, _, cookies = request(
                        p, "/login", "POST",
                        {"csrf":csrf(body),"username":"WikiAdmin","password":"WikiPassword123!"}, guest,
                    )
                    self.assertEqual(status, 303)
                    active.append(cookie_of(cookies, "obwiki_session"))

                status, _, body, _ = request(p, "/admin", cookie=active[0])
                self.assertEqual(status, 200)
                self.assertIn("Завершить другие сеансы".encode("utf-8"), body)
                status, _, _, _ = request(
                    p, "/sessions/close-others", "POST",
                    {"csrf":csrf(body)}, active[0],
                )
                self.assertEqual(status, 303)
                self.assertEqual(request(p, "/admin", cookie=active[0])[0], 200)
                self.assertEqual(request(p, "/admin", cookie=active[1])[0], 303)

                status, _, body, _ = request(p, "/admin", cookie=active[0])
                self.assertEqual(status, 200)
                status, _, _, _ = request(
                    p, "/sessions/logout-all", "POST", {"csrf":csrf(body)}, active[0],
                )
                self.assertEqual(status, 303)
                self.assertEqual(request(p, "/admin", cookie=active[0])[0], 303)


if __name__ == "__main__":
    unittest.main()
