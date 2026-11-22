"""HTTP regressions for account security notices and persistent event history.

The site uses an ephemeral SQLite database. Email delivery and SMTP failures
are replaced only inside the child test server; no real mail is sent.
"""
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from test_sso import ROOT, port, http, cookie_of, csrf_from


def lines(path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


class AccountSecurityEventsTests(unittest.TestCase):
    def test_audit_mailbox_notifications_and_failed_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=port()
            folder=Path(tmp)/"site"
            delivered=Path(tmp)/"messages.txt"
            notices=Path(tmp)/"alerts.txt"
            fail=Path(tmp)/"notify-failure"
            env=os.environ.copy()
            env.update({
                "OBSIDIAN_BIND":"127.0.0.1",
                "OBSIDIAN_PORT":str(p),
                "OBSIDIAN_BASE_URL":f"http://127.0.0.1:{p}",
                "OBSIDIAN_DATA_DIR":str(folder),
                "OBSIDIAN_SMTP_HOST":"smtp.example.invalid",
                "OBSIDIAN_SMTP_PORT":"465",
                "OBSIDIAN_SMTP_FROM":"notice@example.invalid",
                "OBSIDIAN_SMTP_SECURITY":"ssl",
                "OBSIDIAN_TEST_MAIL":str(delivered),
                "OBSIDIAN_TEST_NOTICES":str(notices),
                "OBSIDIAN_TEST_NOTICE_FAIL":str(fail),
            })
            launcher="""
import os
from pathlib import Path
import recovery
import email_verify
import security_events
import server
def append(path, value):
    with open(os.environ[path], "a", encoding="utf-8") as out:
        out.write(value+"\\n")
def verification(to, token, base, purpose):
    append("OBSIDIAN_TEST_MAIL", purpose+"|"+to+"|"+token)
def recover(to, token, base):
    append("OBSIDIAN_TEST_MAIL", "reset|"+to+"|"+token)
def alert(to, event):
    if Path(os.environ["OBSIDIAN_TEST_NOTICE_FAIL"]).exists():
        raise OSError("Simulated SMTP outage")
    append("OBSIDIAN_TEST_NOTICES", event+"|"+to)
email_verify.send_email=verification
recovery.send_email=recover
security_events.send_notice=alert
server.main()
"""
            proc=subprocess.Popen(
                [sys.executable,"-c",launcher],cwd=ROOT/"Сайт",env=env,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(100):
                    if proc.poll() is not None:
                        details=proc.stdout.read().decode("utf-8","replace")[-4500:]
                        self.fail("Website failed to start: "+details)
                    try:
                        if http(p,"/health")[0]==200:
                            break
                    except OSError:
                        pass
                    time.sleep(0.1)
                else:
                    self.fail("Website did not respond")

                def get_page(path,cookie=""):
                    status,headers,body=http(p,path,cookie=cookie)
                    self.assertEqual(status,200,(path,status))
                    return headers,body

                # Register and prove email ownership before any security mail.
                headers,body=get_page("/register")
                guest=cookie_of(headers)
                status,headers,_=http(p,"/register","POST",{
                    "csrf":csrf_from(body),"username":"SecureMember",
                    "email":"verified@example.invalid","password":"OriginalPassword123!",
                    "password2":"OriginalPassword123!",
                },guest)
                self.assertEqual(status,303)
                account=cookie_of(headers)
                kind,address,token=lines(delivered)[-1].split("|")
                self.assertEqual((kind,address),("verify","verified@example.invalid"))
                headers,body=get_page("/verify-email?token="+token)
                confirm_cookie=cookie_of(headers)
                self.assertEqual(http(p,"/verify-email","POST",{
                    "csrf":csrf_from(body),"token":token,
                },confirm_cookie)[0],303)
                headers,body=get_page("/account",account)
                self.assertIn("ИСТОРИЯ БЕЗОПАСНОСТИ".encode("utf-8"),body)
                self.assertIn("Email подтверждён".encode("utf-8"),body)

                # Password change is committed before its successful alert.
                status,headers,_=http(p,"/account/password","POST",{
                    "csrf":csrf_from(body),"old_password":"OriginalPassword123!",
                    "new_password":"FirstChangedPassword123!",
                },account)
                self.assertEqual(status,303)
                self.assertIn("password_changed|verified@example.invalid",lines(notices))

                # SMTP outage may suppress a notice but MUST NOT undo a password change.
                fail.touch()
                headers,body=get_page("/account",account)
                before_count=len(lines(notices))
                status,headers,_=http(p,"/account/password","POST",{
                    "csrf":csrf_from(body),"old_password":"FirstChangedPassword123!",
                    "new_password":"SecondChangedPassword123!",
                },account)
                self.assertEqual(status,303)
                self.assertIn("message=password",headers["Location"])
                self.assertEqual(len(lines(notices)),before_count)
                fail.unlink()
                with closing(sqlite3.connect(folder/"obsidian.sqlite3")) as c:
                    self.assertEqual(c.execute(
                        "SELECT COUNT(*) FROM account_security_events WHERE event='password_changed'"
                    ).fetchone()[0],2)

                # Password recovery appends a successful security notice too.
                headers,body=get_page("/forgot")
                reset_guest=cookie_of(headers)
                self.assertEqual(http(p,"/forgot","POST",{
                    "csrf":csrf_from(body),"email":"verified@example.invalid",
                },reset_guest)[0],303)
                purpose,to,reset_token=lines(delivered)[-1].split("|")
                self.assertEqual((purpose,to),("reset","verified@example.invalid"))
                headers,body=get_page("/reset?token="+reset_token)
                reset_page_cookie=cookie_of(headers)
                status,headers,_=http(p,"/reset","POST",{
                    "csrf":csrf_from(body),"token":reset_token,
                    "password":"RecoveredPassword123!",
                    "confirm":"RecoveredPassword123!",
                },reset_page_cookie)
                self.assertEqual(status,303)
                self.assertEqual(headers["Location"],"/login?message=reset")
                self.assertIn("password_reset|verified@example.invalid",lines(notices))

                # Log back in; the old authenticated cookie was revoked by recovery.
                self.assertEqual(http(p,"/account",cookie=account)[0],303)
                headers,body=get_page("/login")
                login_guest=cookie_of(headers)
                status,headers,_=http(p,"/login","POST",{
                    "csrf":csrf_from(body),"identity":"SecureMember",
                    "password":"RecoveredPassword123!",
                },login_guest)
                self.assertEqual(status,303)
                account=cookie_of(headers)

                # A request to change email warns the original verified mailbox.
                headers,body=get_page("/account",account)
                status,headers,_=http(p,"/account/email/change","POST",{
                    "csrf":csrf_from(body),"email":"new@example.invalid",
                    "password":"RecoveredPassword123!",
                },account)
                self.assertEqual(status,303)
                self.assertIn("email_change_requested|verified@example.invalid",lines(notices))
                purpose,to,change_token=lines(delivered)[-1].split("|")
                self.assertEqual((purpose,to),("change","new@example.invalid"))

                headers,body=get_page("/verify-email?token="+change_token,account)
                self.assertEqual(http(p,"/verify-email","POST",{
                    "csrf":csrf_from(body),"token":change_token,
                },account)[0],303)
                self.assertIn("email_changed|verified@example.invalid",lines(notices))
                self.assertEqual(http(p,"/account",cookie=account)[0],303)

                # Events survive logout and are visible only within the user's account.
                with closing(sqlite3.connect(folder/"obsidian.sqlite3")) as c:
                    c.row_factory=sqlite3.Row
                    data=c.execute(
                        "SELECT event,created_at FROM account_security_events ORDER BY id"
                    ).fetchall()
                    event_names=[item["event"] for item in data]
                    for expected in (
                        "email_verified","password_changed","password_reset",
                        "email_change_requested","email_changed",
                    ):
                        self.assertIn(expected,event_names)
                    self.assertNotIn("OriginalPassword123!",str(data))
                    self.assertNotIn(change_token,str(data))
                    self.assertNotIn("verified@example.invalid",str(data))
                    updated=c.execute("SELECT email,email_verified_at FROM users WHERE username='SecureMember'").fetchone()
                    self.assertEqual(updated["email"],"new@example.invalid")
                    self.assertIsNotNone(updated["email_verified_at"])

                # The updated email can sign in and read its own audit history.
                headers,body=get_page("/login")
                guest=cookie_of(headers)
                status,headers,_=http(p,"/login","POST",{
                    "csrf":csrf_from(body),"identity":"new@example.invalid",
                    "password":"RecoveredPassword123!",
                },guest)
                self.assertEqual(status,303)
                account=cookie_of(headers)
                _,body=get_page("/account",account)
                self.assertIn("Пароль восстановлен".encode("utf-8"),body)
                self.assertIn("Адрес email изменён".encode("utf-8"),body)

                # Sensitive event journal stays server-side: no secrets in tracked DB fields.
                with closing(sqlite3.connect(folder/"obsidian.sqlite3")) as c:
                    names={row[1] for row in c.execute("PRAGMA table_info(account_security_events)")}
                    self.assertEqual(names,{"id","user_id","event","created_at"})
            finally:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                if proc.stdout:
                    proc.stdout.close()


if __name__=="__main__":
    unittest.main()
