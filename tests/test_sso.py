"""Real HTTP integration tests for optional website -> forum SSO.

Runs only against ephemeral loopback servers, with temporary databases.
No test users or tokens are written into the Git repository.
"""
import http.client as http_client
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import parse_qs, quote, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http(port_number, path, method="GET", data=None, cookie=""):
    headers = {}
    if data is not None:
        data = urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if cookie:
        headers["Cookie"] = cookie
    conn = http_client.HTTPConnection("127.0.0.1", port_number, timeout=8)
    try:
        conn.request(method, path, data, headers)
        resp = conn.getresponse()
        body = resp.read()
        return resp.status, dict(resp.getheaders()), body
    finally:
        conn.close()


def cookie_of(headers):
    return headers.get("Set-Cookie", "").split(";", 1)[0]


def csrf_from(body):
    hit = re.search(rb'name="csrf"\s+value="([^"]+)"', body)
    if not hit:
        raise AssertionError("CSRF field was not found")
    return hit.group(1).decode("ascii")


class ForumSSOTests(unittest.TestCase):
    def test_one_time_code_and_account_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            web_port, forum_port = port(), port()
            while forum_port == web_port:
                forum_port = port()
            shared = secrets.token_urlsafe(48)
            env = os.environ.copy()
            env.update({
                "OBSIDIAN_BIND": "127.0.0.1",
                "OBSIDIAN_PORT": str(web_port),
                "OBSIDIAN_DATA_DIR": str(Path(tmp) / "site"),
                "OBSIDIAN_SSO_FORUM_SECRET": shared,
                "OBSIDIAN_SSO_FORUM_CALLBACK": f"http://127.0.0.1:{forum_port}/sso/callback",
                "OBFORUM_BIND": "127.0.0.1",
                "OBFORUM_PORT": str(forum_port),
                "OBFORUM_DATA_DIR": str(Path(tmp) / "forum"),
                "OBFORUM_SSO_ISSUER": f"http://127.0.0.1:{web_port}",
                "OBFORUM_SSO_CLIENT_SECRET": shared,
            })
            processes = [
                subprocess.Popen([sys.executable, "server.py"], cwd=ROOT / "Сайт",
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT),
                subprocess.Popen([sys.executable, "app.py"], cwd=ROOT / "Форум",
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT),
            ]
            try:
                for server_port in (web_port, forum_port):
                    for _ in range(100):
                        try:
                            status, _, _ = http(server_port, "/health")
                            if status == 200:
                                break
                        except (OSError, TimeoutError):
                            if any(p.poll() is not None for p in processes):
                                exited = [p for p in processes if p.poll() is not None]
                                errors = [p.stdout.read().decode("utf-8", "replace")[-5000:] for p in exited]
                                self.fail("Site or forum exited unexpectedly: " + " | ".join(errors))
                            time.sleep(0.15)
                    else:
                        self.fail("Local service did not become healthy")

                # Forum creates state tied to its anonymous session cookie.
                code_status, forum_headers, _ = http(forum_port, "/sso/login")
                self.assertEqual(code_status, 303)
                forum_cookie = cookie_of(forum_headers)
                self.assertTrue(forum_cookie.startswith("obforum_session="))
                authorize = urlsplit(forum_headers["Location"])
                self.assertEqual(authorize.path, "/sso/authorize")
                state = parse_qs(authorize.query)["state"][0]

                # Anonymous authorization must require login at the website.
                status, headers, _ = http(web_port, authorize.path + "?" + authorize.query)
                self.assertEqual(status, 303)
                self.assertTrue(headers["Location"].startswith("/login?next="))
                web_cookie = cookie_of(headers)

                # Creating a website account preserves the authorization request.
                ret = authorize.path + "?" + authorize.query
                registration = "/register?next=" + quote(ret, safe="")
                status, headers, body = http(web_port, registration, cookie=web_cookie)
                self.assertEqual(status, 200)
                csrf = csrf_from(body)
                self.assertIn(b'name="next"', body)
                status, headers, _ = http(web_port, "/register", method="POST", cookie=web_cookie, data={
                    "csrf": csrf,
                    "next": ret,
                    "username": "SSOplayer",
                    "email": "sso-player@example.invalid",
                    "password": "SsoPasswordTest123!",
                    "password2": "SsoPasswordTest123!",
                })
                self.assertEqual(status, 303)
                self.assertEqual(headers["Location"], ret)
                web_cookie = cookie_of(headers)
                self.assertTrue(web_cookie.startswith("or_session="))

                # Site issues a short-lived code; forum exchanges it server-side.
                status, headers, _ = http(web_port, ret, cookie=web_cookie)
                self.assertEqual(status, 303)
                callback = urlsplit(headers["Location"])
                self.assertEqual(callback.path, "/sso/callback")
                params = parse_qs(callback.query)
                self.assertEqual(params["state"][0], state)
                issued_code = params["code"][0]
                status, headers, _ = http(forum_port, callback.path + "?" + callback.query, cookie=forum_cookie)
                self.assertEqual(status, 303)
                self.assertTrue(headers["Location"].startswith("/account"))
                active_cookie = cookie_of(headers)
                self.assertTrue(active_cookie.startswith("obforum_session="))

                status, _, body = http(forum_port, "/account", cookie=active_cookie)
                self.assertEqual(status, 200)
                self.assertIn(b"SSOplayer", body)

                # Replaying the callback and redeemed code is not allowed.
                status, _, _ = http(forum_port, callback.path + "?" + callback.query, cookie=active_cookie)
                self.assertEqual(status, 400)
                status, _, _ = http(web_port, "/sso/token", method="POST", data={
                    "client_id": "forum", "client_secret": shared, "code": issued_code,
                })
                self.assertEqual(status, 401)

                # An invalid client credential cannot exchange even a fresh code.
                status, headers, _ = http(web_port, ret, cookie=web_cookie)
                fresh_code = parse_qs(urlsplit(headers["Location"]).query)["code"][0]
                status, _, _ = http(web_port, "/sso/token", method="POST", data={
                    "client_id": "forum", "client_secret": "wrong", "code": fresh_code,
                })
                self.assertEqual(status, 401)

            finally:
                for proc in processes:
                    if proc.poll() is None:
                        proc.terminate()
                for proc in processes:
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()


if __name__ == "__main__":
    unittest.main()
