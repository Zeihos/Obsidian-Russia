"""HTTP tests for explicit linking of an existing forum account to a website identity.

The flow proves possession of a forum password and a website login. It
does not merge profiles, email addresses, or moderator permissions.
"""
import os
from pathlib import Path
from contextlib import closing
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlsplit

from test_sso import ROOT, port, http, cookie_of, csrf_from


class ExistingAccountLinkTests(unittest.TestCase):
    def test_link_preserves_forum_profile_and_rejects_conflicts(self):
        with tempfile.TemporaryDirectory() as temp:
            site_port, forum_port = port(), port()
            while forum_port == site_port:
                forum_port = port()
            site_dir = Path(temp) / "site"
            forum_dir = Path(temp) / "forum"
            shared = secrets.token_urlsafe(48)
            env = os.environ.copy()
            env.update({
                "OBSIDIAN_BIND": "127.0.0.1",
                "OBSIDIAN_PORT": str(site_port),
                "OBSIDIAN_DATA_DIR": str(site_dir),
                "OBSIDIAN_SSO_FORUM_SECRET": shared,
                "OBSIDIAN_SSO_FORUM_CALLBACK": f"http://127.0.0.1:{forum_port}/sso/callback",
                "OBFORUM_BIND": "127.0.0.1",
                "OBFORUM_PORT": str(forum_port),
                "OBFORUM_DATA_DIR": str(forum_dir),
                "OBFORUM_SSO_ISSUER": f"http://127.0.0.1:{site_port}",
                "OBFORUM_SSO_CLIENT_SECRET": shared,
            })
            processes = [
                subprocess.Popen([sys.executable,"server.py"],cwd=ROOT/"Сайт",env=env,
                                 stdout=subprocess.PIPE,stderr=subprocess.STDOUT),
                subprocess.Popen([sys.executable,"app.py"],cwd=ROOT/"Форум",env=env,
                                 stdout=subprocess.PIPE,stderr=subprocess.STDOUT),
            ]
            try:
                for service_port in (site_port,forum_port):
                    for _ in range(100):
                        try:
                            if http(service_port,"/health")[0] == 200:
                                break
                        except OSError:
                            if any(p.poll() is not None for p in processes):
                                failures=[p.stdout.read().decode("utf-8","replace")[-4000:]
                                          for p in processes if p.poll() is not None]
                                self.fail("Service failed: "+" | ".join(failures))
                            time.sleep(0.15)
                    else:
                        self.fail("Service unavailable")

                def register_forum(name, email, password):
                    status,headers,body=http(forum_port,"/register")
                    self.assertEqual(status,200)
                    guest=cookie_of(headers)
                    status,headers,_=http(forum_port,"/register","POST",{
                        "csrf":csrf_from(body),"username":name,"email":email,
                        "password":password,"confirm":password,
                    },guest)
                    self.assertEqual(status,303)
                    return cookie_of(headers)

                original=register_forum("ForumVeteran","veteran@example.invalid","ForumSecret123!")
                status,_,body=http(forum_port,"/account",cookie=original)
                self.assertEqual(status,200)
                self.assertIn("Привязать аккаунт сайта".encode("utf-8"),body)

                # Create an ordinary forum thread that must remain owned by this ID.
                with closing(sqlite3.connect(forum_dir/"forum.sqlite3")) as conn:
                    user_id=conn.execute("SELECT id FROM users WHERE username='ForumVeteran'").fetchone()[0]
                    forum_id=conn.execute("SELECT id FROM forums WHERE staff_only=0 LIMIT 1").fetchone()[0]
                status,_,_=http(forum_port,"/thread/new","POST",{
                    "csrf":csrf_from(body),"forum":str(forum_id),
                    "title":"До привязки аккаунта","body":"Старое сообщение должно сохраниться навсегда.",
                },original)
                self.assertEqual(status,303)

                # A site login proves ownership of a *different* website account.
                status,headers,body=http(site_port,"/register")
                self.assertEqual(status,200)
                site_guest=cookie_of(headers)
                status,headers,_=http(site_port,"/register","POST",{
                    "csrf":csrf_from(body),"username":"WebsiteMember",
                    "email":"site-member@example.invalid",
                    "password":"SiteSecret123!","password2":"SiteSecret123!",
                },site_guest)
                self.assertEqual(status,303)
                website=cookie_of(headers)

                # CSRF and forum password step-up are mandatory.
                self.assertEqual(http(forum_port,"/sso/link/start","POST",{
                    "csrf":"wrong","password":"ForumSecret123!",
                },original)[0],400)
                status,_,body=http(forum_port,"/account",cookie=original)
                self.assertEqual(status,200)
                csrf=csrf_from(body)
                status,headers,_=http(forum_port,"/sso/link/start","POST",{
                    "csrf":csrf,"password":"incorrect",
                },original)
                self.assertEqual(status,303)
                self.assertIn("link_password",headers["Location"])

                status,headers,_=http(forum_port,"/sso/link/start","POST",{
                    "csrf":csrf,"password":"ForumSecret123!",
                },original)
                self.assertEqual(status,303)
                target=urlsplit(headers["Location"])
                self.assertEqual(target.path,"/sso/authorize")
                status,headers,_=http(site_port,target.path+"?"+target.query,cookie=website)
                self.assertEqual(status,303)
                callback=urlsplit(headers["Location"])
                self.assertEqual(callback.path,"/sso/callback")
                callback_path=callback.path+"?"+callback.query

                # The callback cannot be stolen by another forum session.
                status,_,_=http(forum_port,callback_path)
                self.assertEqual(status,400)
                status,headers,_=http(forum_port,callback_path,cookie=original)
                self.assertEqual(status,303)
                self.assertEqual(headers["Location"],"/account?message=linked")
                self.assertEqual(http(forum_port,callback_path,cookie=original)[0],400)

                status,_,body=http(forum_port,"/account",cookie=original)
                self.assertEqual(status,200)
                self.assertIn(b"ForumVeteran",body)
                self.assertIn("До привязки аккаунта".encode("utf-8"),body)
                self.assertNotIn("Привязать аккаунт сайта".encode("utf-8"),body)
                with closing(sqlite3.connect(forum_dir/"forum.sqlite3")) as conn:
                    row=conn.execute(
                        "SELECT u.id,u.username,u.role,l.provider_sub FROM users u "
                        "JOIN sso_accounts l ON l.user_id=u.id WHERE u.id=?",(user_id,)
                    ).fetchone()
                    self.assertEqual(row[:3],(user_id,"ForumVeteran","member"))
                    self.assertEqual(conn.execute(
                        "SELECT COUNT(*) FROM threads WHERE user_id=?",(user_id,)
                    ).fetchone()[0],1)

                # The old local password is disabled after linking.
                status,headers,body=http(forum_port,"/login")
                self.assertEqual(status,200)
                guest=cookie_of(headers)
                status,headers,_=http(forum_port,"/login","POST",{
                    "csrf":csrf_from(body),"identity":"ForumVeteran",
                    "password":"ForumSecret123!",
                },guest)
                self.assertEqual(status,303)
                self.assertIn("message=password",headers["Location"])

                # SSO login must reuse the original forum account ID.
                status,headers,_=http(forum_port,"/sso/login")
                self.assertEqual(status,303)
                forum_guest=cookie_of(headers)
                dest=urlsplit(headers["Location"])
                status,headers,_=http(site_port,dest.path+"?"+dest.query,cookie=website)
                self.assertEqual(status,303)
                callback=urlsplit(headers["Location"])
                status,headers,_=http(forum_port,callback.path+"?"+callback.query,cookie=forum_guest)
                self.assertEqual(status,303)
                fresh=cookie_of(headers)
                self.assertEqual(http(forum_port,"/account",cookie=fresh)[0],200)
                with closing(sqlite3.connect(forum_dir/"forum.sqlite3")) as conn:
                    self.assertEqual(conn.execute(
                        "SELECT COUNT(*) FROM users WHERE username='ForumVeteran'"
                    ).fetchone()[0],1)
                    self.assertEqual(conn.execute("SELECT user_id FROM sso_accounts").fetchone()[0],user_id)

                # Another forum member cannot seize an already-bound site identity.
                other=register_forum("SecondMember","second@example.invalid","OtherPassword123!")
                status,_,body=http(forum_port,"/account",cookie=other)
                self.assertEqual(status,200)
                status,headers,_=http(forum_port,"/sso/link/start","POST",{
                    "csrf":csrf_from(body),"password":"OtherPassword123!",
                },other)
                self.assertEqual(status,303)
                dest=urlsplit(headers["Location"])
                status,headers,_=http(site_port,dest.path+"?"+dest.query,cookie=website)
                self.assertEqual(status,303)
                callback=urlsplit(headers["Location"])
                status,_,_=http(forum_port,callback.path+"?"+callback.query,cookie=other)
                self.assertEqual(status,409)
                self.assertEqual(http(forum_port,"/account",cookie=other)[0],200)
                with closing(sqlite3.connect(forum_dir/"forum.sqlite3")) as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM sso_accounts").fetchone()[0],1)
            finally:
                for p in processes:
                    if p.poll() is None:p.terminate()
                for p in processes:
                    try:p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait()
                    if p.stdout:p.stdout.close()


if __name__=="__main__":
    unittest.main()
