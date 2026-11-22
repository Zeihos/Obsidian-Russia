"""Website password recovery: HTTP, SQLite, and mock SMTP transport.

All HTTP traffic is loopback, all accounts are test-only, and email delivery
is replaced *only inside this test process*. Production SMTP is never used.
"""
from contextlib import closing
from email.message import EmailMessage
from pathlib import Path
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_sso import ROOT, port, http, cookie_of, csrf_from


class PasswordRecoveryTests(unittest.TestCase):
    def test_http_recovery_revokes_sessions_and_rejects_replays(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = port()
            dbdir = Path(tmp) / "site"
            mailbox = Path(tmp) / "delivered.txt"
            failflag = Path(tmp) / "smtp-failure.txt"
            env = os.environ.copy()
            env.update({
                "OBSIDIAN_BIND":"127.0.0.1", "OBSIDIAN_PORT":str(p),
                "OBSIDIAN_BASE_URL":f"http://127.0.0.1:{p}",
                "OBSIDIAN_DATA_DIR":str(dbdir),
                "OBSIDIAN_SMTP_HOST":"smtp.example.invalid",
                "OBSIDIAN_SMTP_PORT":"465",
                "OBSIDIAN_SMTP_FROM":"notice@example.invalid",
                "OBSIDIAN_SMTP_SECURITY":"ssl",
                "OBSIDIAN_TEST_MAIL_FILE":str(mailbox),
                "OBSIDIAN_TEST_VERIFY_FILE":str(Path(tmp) / "verify.txt"),
                "OBSIDIAN_TEST_FAIL_FLAG":str(failflag),
            })
            launcher = """
import os
from pathlib import Path
import recovery
import email_verify
import server
def fake_verify(to_address, token, base_url, purpose):
    Path(os.environ["OBSIDIAN_TEST_VERIFY_FILE"]).write_text(token, encoding="ascii")
email_verify.send_email = fake_verify
def fake_email(to_address, token, base_url):
    if Path(os.environ["OBSIDIAN_TEST_FAIL_FLAG"]).exists():
        raise RuntimeError("Simulated SMTP connection failure")
    Path(os.environ["OBSIDIAN_TEST_MAIL_FILE"]).write_text(token, encoding="ascii")
recovery.send_email = fake_email
server.main()
"""
            process = subprocess.Popen(
                [sys.executable,"-c",launcher],cwd=ROOT/"Сайт",env=env,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(100):
                    try:
                        if http(p,"/health")[0]==200:
                            break
                    except OSError:
                        if process.poll() is not None:
                            err=process.stdout.read().decode("utf-8","replace")[-5000:]
                            self.fail("Recovery test server did not start: "+err)
                        time.sleep(0.15)
                else:
                    self.fail("Recovery server not reachable")

                # Registration creates an authenticated session for later revocation.
                status,headers,body=http(p,"/register")
                self.assertEqual(status,200)
                guest=cookie_of(headers)
                status,headers,_=http(p,"/register","POST",{
                    "csrf":csrf_from(body),"username":"RecoveryUser",
                    "email":"recovery@example.invalid",
                    "password":"PreviousPassword123!","password2":"PreviousPassword123!",
                },guest)
                self.assertEqual(status,303)
                original_cookie=cookie_of(headers)
                self.assertEqual(http(p,"/account",cookie=original_cookie)[0],200)
                # Recovery is intentionally disabled for unverified addresses.
                verify_token=(Path(tmp) / "verify.txt").read_text(encoding="ascii")
                status,headers,body=http(p,"/verify-email?token="+verify_token)
                self.assertEqual(status,200)
                verify_guest=cookie_of(headers)
                status,_,_=http(p,"/verify-email","POST",{
                    "csrf":csrf_from(body),"token":verify_token,
                },verify_guest)
                self.assertEqual(status,303)
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    self.assertIsNotNone(c.execute(
                        "SELECT email_verified_at FROM users WHERE username='RecoveryUser'"
                    ).fetchone()[0])
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    uid=c.execute("SELECT id FROM users WHERE username='RecoveryUser'").fetchone()[0]
                    c.execute("INSERT INTO sso_codes(code_hash,client_id,user_id,expires_at) "
                              "VALUES('fake-test-hash','forum',?,'2099-01-01T00:00:00+00:00')",(uid,))
                    c.commit()

                status,_,body=http(p,"/login")
                self.assertIn(b'href="/forgot"',body)

                # Form is CSRF-protected and anonymous, even for unknown users.
                status,headers,body=http(p,"/forgot")
                self.assertEqual(status,200)
                self.assertIn("Отправить ссылку".encode("utf-8"),body)
                anon_cookie=cookie_of(headers)
                csrf=csrf_from(body)
                self.assertEqual(http(p,"/forgot","POST",{
                    "csrf":"invalid","email":"recovery@example.invalid",
                },anon_cookie)[0],400)

                status,headers,_=http(p,"/forgot","POST",{
                    "csrf":csrf,"email":"unknown@example.invalid",
                },anon_cookie)
                self.assertEqual(status,303)
                self.assertEqual(headers["Location"],"/forgot?message=sent")
                self.assertFalse(mailbox.exists())

                status,headers,_=http(p,"/forgot","POST",{
                    "csrf":csrf,"email":"recovery@example.invalid",
                },anon_cookie)
                self.assertEqual(status,303)
                self.assertEqual(headers["Location"],"/forgot?message=sent")
                token=mailbox.read_text(encoding="ascii")
                self.assertGreaterEqual(len(token),40)
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    record=c.execute("SELECT token_hash FROM password_resets WHERE user_id=?",(uid,)).fetchone()
                    self.assertIsNotNone(record)
                    self.assertNotEqual(record[0],token)

                self.assertEqual(http(p,"/reset?token=invalid")[0],400)
                status,headers,body=http(p,"/reset?token="+token)
                self.assertEqual(status,200)
                self.assertEqual(headers.get("Referrer-Policy"),"no-referrer")
                self.assertEqual(headers.get("Cache-Control"),"no-store")
                csrf=csrf_from(body)
                reset_guest=cookie_of(headers)

                self.assertEqual(http(p,"/reset","POST",{
                    "csrf":"bad","token":token,
                    "password":"BrandNewPassword123!","confirm":"BrandNewPassword123!",
                },reset_guest)[0],400)
                self.assertEqual(http(p,"/reset","POST",{
                    "csrf":csrf,"token":token,
                    "password":"BrandNewPassword123!","confirm":"mismatching",
                },reset_guest)[0],400)

                status,headers,_=http(p,"/reset","POST",{
                    "csrf":csrf,"token":token,
                    "password":"BrandNewPassword123!","confirm":"BrandNewPassword123!",
                },reset_guest)
                self.assertEqual(status,303)
                self.assertEqual(headers["Location"],"/login?message=reset")
                self.assertEqual(http(p,"/account",cookie=original_cookie)[0],303)
                self.assertEqual(http(p,"/reset?token="+token)[0],400)
                status,headers,_=http(p,"/reset","POST",{
                    "csrf":csrf,"token":token,
                    "password":"BrandNewPassword123!","confirm":"BrandNewPassword123!",
                },reset_guest)
                self.assertEqual(status,303)
                self.assertIn("invalid",headers["Location"])

                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    self.assertEqual(c.execute("SELECT auth_version FROM users WHERE id=?",(uid,)).fetchone()[0],1)
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM sessions WHERE user_id=?",(uid,)).fetchone()[0],0)
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM sso_codes WHERE user_id=?",(uid,)).fetchone()[0],0)
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM password_resets WHERE user_id=?",(uid,)).fetchone()[0],0)

                # Previous password no longer logs in; new password does.
                status,headers,body=http(p,"/login")
                guest=cookie_of(headers)
                status,headers,_=http(p,"/login","POST",{
                    "csrf":csrf_from(body),"identity":"RecoveryUser",
                    "password":"PreviousPassword123!",
                },guest)
                self.assertEqual(status,303)
                self.assertIn("message=error",headers["Location"])
                status,headers,_=http(p,"/login","POST",{
                    "csrf":csrf_from(body),"identity":"RecoveryUser",
                    "password":"BrandNewPassword123!",
                },guest)
                self.assertEqual(status,303)
                self.assertEqual(http(p,"/account",cookie=cookie_of(headers))[0],200)

                # Token expired in DB cannot be redeemed.
                status,headers,_=http(p,"/forgot","POST",{
                    "csrf":csrf_from(http(p,"/forgot",cookie=anon_cookie)[2]),
                    "email":"recovery@example.invalid",
                },anon_cookie)
                self.assertEqual(status,303)
                expired=mailbox.read_text(encoding="ascii")
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    c.execute("UPDATE password_resets SET expires_at='2000-01-01T00:00:00+00:00' WHERE user_id=?",(uid,))
                    c.commit()
                self.assertEqual(http(p,"/reset?token="+expired)[0],400)

                # Simulated SMTP failure never leaves a usable reset token.
                failflag.touch()
                status,headers,_=http(p,"/forgot","POST",{
                    "csrf":csrf_from(http(p,"/forgot",cookie=anon_cookie)[2]),
                    "email":"recovery@example.invalid",
                },anon_cookie)
                self.assertEqual(status,303)
                self.assertEqual(headers["Location"],"/forgot?message=sent")
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM password_resets WHERE user_id=?",(uid,)).fetchone()[0],0)
            finally:
                if process.poll() is None:process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                if process.stdout:process.stdout.close()

    def test_email_transport_requires_tls_configuration(self):
        # Test the actual production sender with a fake TLS-aware SMTP object.
        import importlib.util
        import sys as runtime
        module_dir=str(ROOT/"Сайт")
        with patch.dict(os.environ,{
            "OBSIDIAN_SMTP_HOST":"smtp.example.org",
            "OBSIDIAN_SMTP_PORT":"465",
            "OBSIDIAN_SMTP_FROM":"notice@example.org",
            "OBSIDIAN_SMTP_SECURITY":"ssl",
            "OBSIDIAN_SMTP_USER":"smtp-user",
            "OBSIDIAN_SMTP_PASSWORD":"app-password",
        }):
            runtime.path.insert(0,module_dir)
            try:
                import recovery
                sent=[]
                class FakeSMTP:
                    def __init__(self,*args,**kwargs):
                        self.args=args
                        self.kwargs=kwargs
                    def __enter__(self):return self
                    def __exit__(self,*args):pass
                    def login(self,user,password):sent.append(("login",user,password))
                    def send_message(self,msg):sent.append(("mail",msg))
                with patch.object(recovery.smtplib,"SMTP_SSL",FakeSMTP):
                    recovery.send_email("person@example.org","A"*48,"https://example.org")
                self.assertEqual(sent[0],("login","smtp-user","app-password"))
                self.assertIsInstance(sent[1][1],EmailMessage)
                self.assertIn("https://example.org/reset?token=",sent[1][1].get_content())
                self.assertIsNone(recovery.site_base("http://example.org"))
            finally:
                runtime.path.remove(module_dir)


if __name__=="__main__":
    unittest.main()
