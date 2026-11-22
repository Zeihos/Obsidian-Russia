"""Real HTTP checks for verified email, legacy safety and mailbox changes.

Only loopback servers and temporary SQLite databases are used. SMTP is mocked
inside the child test server and writes tokens to a temporary test mailbox.
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
from unittest.mock import patch
from test_sso import ROOT, port, http, cookie_of, csrf_from


def last_mail(path):
    lines=path.read_text(encoding="utf-8").splitlines()
    purpose,address,token=lines[-1].split("|",2)
    return purpose,address,token


class EmailVerificationTests(unittest.TestCase):
    def test_verify_register_and_protected_email_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=port()
            dbdir=Path(tmp)/"data"
            mailbox=Path(tmp)/"mail.txt"
            failflag=Path(tmp)/"fail.txt"
            env=os.environ.copy()
            env.update({
                "OBSIDIAN_BIND":"127.0.0.1",
                "OBSIDIAN_PORT":str(p),
                "OBSIDIAN_BASE_URL":f"http://127.0.0.1:{p}",
                "OBSIDIAN_DATA_DIR":str(dbdir),
                "OBSIDIAN_SMTP_HOST":"smtp.example.invalid",
                "OBSIDIAN_SMTP_PORT":"465",
                "OBSIDIAN_SMTP_FROM":"notice@example.invalid",
                "OBSIDIAN_SMTP_SECURITY":"ssl",
                "OBSIDIAN_MAILBOX_TEST":str(mailbox),
                "OBSIDIAN_MAIL_FAIL_TEST":str(failflag),
            })
            launcher="""
from pathlib import Path
import os
import email_verify
import server
def fake_mail(address,token,base,purpose):
    if Path(os.environ["OBSIDIAN_MAIL_FAIL_TEST"]).exists():
        raise RuntimeError("Simulated failed delivery")
    with open(os.environ["OBSIDIAN_MAILBOX_TEST"],"a",encoding="utf-8") as out:
        out.write(purpose+"|"+address+"|"+token+"\n")
email_verify.send_email=fake_mail
server.main()
"""
            process=subprocess.Popen(
                [sys.executable,"-c",launcher],cwd=ROOT/"Сайт",env=env,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        details=process.stdout.read().decode("utf-8","replace")[-5000:]
                        self.fail("Test server stopped: "+details)
                    try:
                        if http(p,"/health")[0]==200:
                            break
                    except OSError:
                        pass
                    time.sleep(0.12)
                else:
                    self.fail("Site did not start")

                def register(username,address,password):
                    status,headers,body=http(p,"/register")
                    self.assertEqual(status,200)
                    guest=cookie_of(headers)
                    status,headers,_=http(p,"/register","POST",{
                        "csrf":csrf_from(body),"username":username,
                        "email":address,"password":password,"password2":password,
                    },guest)
                    self.assertEqual(status,303)
                    return cookie_of(headers)

                def csrf_for(path,cookie):
                    status,headers,html=http(p,path,cookie=cookie)
                    self.assertEqual(status,200)
                    return csrf_from(html)

                account=register("FirstMember","first@example.invalid","FirstPassword123!")
                proof,address,token=last_mail(mailbox)
                self.assertEqual((proof,address),("verify","first@example.invalid"))
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    self.assertIsNone(c.execute(
                        "SELECT email_verified_at FROM users WHERE username='FirstMember'"
                    ).fetchone()[0])
                    self.assertNotEqual(c.execute(
                        "SELECT token_hash FROM email_tokens WHERE purpose='verify'"
                    ).fetchone()[0],token)

                # Unverified emails cannot obtain reset tokens, despite enabled SMTP.
                status,headers,body=http(p,"/forgot")
                anon=cookie_of(headers)
                status,headers,_=http(p,"/forgot","POST",{
                    "csrf":csrf_from(body),"email":"first@example.invalid",
                },anon)
                self.assertEqual(status,303)
                self.assertEqual(headers["Location"],"/forgot?message=sent")
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM password_resets").fetchone()[0],0)

                # The link is only consumed by a CSRF-protected POST, not GET.
                status,headers,body=http(p,"/verify-email?token="+token)
                self.assertEqual(status,200)
                self.assertEqual(headers.get("Referrer-Policy"),"no-referrer")
                self.assertEqual(headers.get("Cache-Control"),"no-store")
                confirmation_guest=cookie_of(headers)
                self.assertEqual(http(p,"/verify-email","POST",{
                    "csrf":"bad","token":token,
                },confirmation_guest)[0],400)
                status,headers,_=http(p,"/verify-email","POST",{
                    "csrf":csrf_from(body),"token":token,
                },confirmation_guest)
                self.assertEqual(status,303)
                self.assertEqual(http(p,"/verify-email?token="+token)[0],400)
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    self.assertIsNotNone(c.execute(
                        "SELECT email_verified_at FROM users WHERE username='FirstMember'"
                    ).fetchone()[0])

                status,_,html=http(p,"/account",cookie=account)
                self.assertEqual(status,200)
                self.assertIn("Адрес подтверждён".encode("utf-8"),html)
                profile_csrf=csrf_from(html)

                # Password proof and destination uniqueness are mandatory.
                status,headers,_=http(p,"/account/email/change","POST",{
                    "csrf":profile_csrf,"email":"next@example.invalid","password":"bad",
                },account)
                self.assertEqual(status,303)
                self.assertIn("email_password",headers["Location"])

                another=register("OtherMember","reserved@example.invalid","OtherPassword123!")
                status,headers,_=http(p,"/account/email/change","POST",{
                    "csrf":profile_csrf,"email":"reserved@example.invalid",
                    "password":"FirstPassword123!",
                },account)
                self.assertEqual(status,303)
                self.assertIn("email_invalid",headers["Location"])

                status,headers,_=http(p,"/account/email/change","POST",{
                    "csrf":profile_csrf,"email":"next@example.invalid",
                    "password":"FirstPassword123!",
                },account)
                self.assertEqual(status,303)
                purpose,destination,change_token=last_mail(mailbox)
                self.assertEqual((purpose,destination),("change","next@example.invalid"))
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    self.assertEqual(c.execute("SELECT email FROM users WHERE username='FirstMember'").fetchone()[0],
                                     "first@example.invalid")

                # Anyone with the link but not the original authenticated account
                # is unable to change the address.
                status,headers,html=http(p,"/verify-email?token="+change_token)
                self.assertEqual(status,200)
                self.assertIn("сначала войди".encode("utf-8"),html)
                guest=cookie_of(headers)
                self.assertEqual(http(p,"/verify-email","POST",{
                    "csrf":csrf_from(html),"token":change_token,
                },guest)[0],303)
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    self.assertEqual(c.execute("SELECT email FROM users WHERE username='FirstMember'").fetchone()[0],
                                     "first@example.invalid")

                status,headers,html=http(p,"/verify-email?token="+change_token,cookie=account)
                self.assertEqual(status,200)
                status,headers,_=http(p,"/verify-email","POST",{
                    "csrf":csrf_from(html),"token":change_token,
                },account)
                self.assertEqual(status,303)
                self.assertIn("/login?message=email_changed",headers["Location"])
                self.assertEqual(http(p,"/account",cookie=account)[0],303)
                self.assertEqual(http(p,"/verify-email?token="+change_token)[0],400)
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    email,verified,version=c.execute(
                        "SELECT email,email_verified_at,auth_version FROM users WHERE username='FirstMember'"
                    ).fetchone()
                    self.assertEqual(email,"next@example.invalid")
                    self.assertIsNotNone(verified)
                    self.assertEqual(version,1)
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM email_tokens WHERE purpose='change'").fetchone()[0],0)

                # New email can log in; old email cannot.
                status,headers,body=http(p,"/login")
                login_guest=cookie_of(headers)
                status,headers,_=http(p,"/login","POST",{
                    "csrf":csrf_from(body),"identity":"next@example.invalid",
                    "password":"FirstPassword123!",
                },login_guest)
                self.assertEqual(status,303)
                self.assertEqual(http(p,"/account",cookie=cookie_of(headers))[0],200)

                # The other registered account may request verification but a
                # simulated SMTP failure cancels its un-delivered token.
                failflag.touch()
                csrf=csrf_for("/account",another)
                status,headers,_=http(p,"/account/email/resend","POST",{
                    "csrf":csrf,
                },another)
                self.assertEqual(status,303)
                self.assertIn("email_error",headers["Location"])
                with closing(sqlite3.connect(dbdir/"obsidian.sqlite3")) as c:
                    id2=c.execute("SELECT id FROM users WHERE username='OtherMember'").fetchone()[0]
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM email_tokens WHERE user_id=?",(id2,)).fetchone()[0],0)
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                if process.stdout:
                    process.stdout.close()


if __name__=="__main__":
    unittest.main()
