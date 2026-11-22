"""Verified-email lifecycle for website accounts (no third-party packages).

Existing accounts are migrated as unverified. Each token is one-time and
stored only as a SHA-256 digest. Email change requires the site password,
then ownership of the replacement mailbox and the original browser session.
"""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import secrets
import smtplib
import ssl
from urllib.parse import urlencode

import recovery
from db import now

TTL_HOURS = 24


def valid_email(value):
    return isinstance(value,str) and 5 <= len(value) <= 120 and bool(
        recovery.EMAIL_PATTERN.fullmatch(value)
    )


def issue(c,user_id,address,purpose):
    if purpose not in ("verify","change") or not valid_email(address):
        raise ValueError("Invalid email verification request")
    token=secrets.token_urlsafe(36)
    expires=(datetime.now(timezone.utc)+timedelta(hours=TTL_HOURS)).isoformat(timespec="seconds")
    c.execute("DELETE FROM email_tokens WHERE user_id=? AND purpose=?",(user_id,purpose))
    c.execute("DELETE FROM email_tokens WHERE expires_at<=?",(now(),))
    c.execute("INSERT INTO email_tokens(token_hash,user_id,pending_email,purpose,expires_at) "
              "VALUES(?,?,?,?,?)",
              (hashlib.sha256(token.encode("ascii")).hexdigest(),user_id,address,purpose,expires))
    return token


def cancel(c,token):
    if recovery.valid_token(token):
        c.execute("DELETE FROM email_tokens WHERE token_hash=?",
                  (hashlib.sha256(token.encode("ascii")).hexdigest(),))


def get(c,token):
    if not recovery.valid_token(token):
        return None
    return c.execute(
        "SELECT token_hash,user_id,pending_email,purpose FROM email_tokens "
        "WHERE token_hash=? AND expires_at>?",
        (hashlib.sha256(token.encode("ascii")).hexdigest(),now()),
    ).fetchone()


def confirm(c,token,current_user_id=None):
    row=get(c,token)
    if not row:
        return "invalid"
    account=c.execute("SELECT id,email FROM users WHERE id=?",(row["user_id"],)).fetchone()
    if not account:
        return "invalid"
    if row["purpose"]=="change":
        if current_user_id!=row["user_id"]:
            return "login_required"
        # Do not overwrite somebody else's confirmed or unconfirmed email.
        conflict=c.execute("SELECT 1 FROM users WHERE email=? AND id<>?",
                           (row["pending_email"],row["user_id"])).fetchone()
        if conflict or account["email"].casefold()==row["pending_email"].casefold():
            return "invalid"
    elif (row["purpose"]!="verify" or
          account["email"].casefold()!=row["pending_email"].casefold()):
        return "invalid"
    consumed=c.execute(
        "DELETE FROM email_tokens WHERE token_hash=? AND expires_at>? RETURNING user_id",
        (row["token_hash"],now()),
    ).fetchone()
    if not consumed:
        return "invalid"
    if row["purpose"]=="change":
        c.execute("UPDATE users SET email=?,email_verified_at=?,auth_version=auth_version+1 "
                  "WHERE id=?",(row["pending_email"],now(),row["user_id"]))
        c.execute("DELETE FROM sessions WHERE user_id=?",(row["user_id"],))
        c.execute("DELETE FROM sso_codes WHERE user_id=?",(row["user_id"],))
        c.execute("DELETE FROM password_resets WHERE user_id=?",(row["user_id"],))
        c.execute("DELETE FROM email_tokens WHERE user_id=?",(row["user_id"],))
        return "changed"
    c.execute("UPDATE users SET email_verified_at=? WHERE id=?",(now(),row["user_id"]))
    return "verified"


def send_email(to_address,token,base_url,purpose):
    settings=recovery.smtp_settings()
    base=recovery.site_base(base_url)
    if not settings or not base or not valid_email(to_address) or not recovery.valid_token(token):
        raise ValueError("Email verification is not configured")
    if purpose not in ("verify","change"):
        raise ValueError("Unknown email verification purpose")
    url=base+"/verify-email?"+urlencode({"token":token})
    message=EmailMessage()
    message["From"]=settings["from_addr"]
    message["To"]=to_address
    message["Subject"]=("OBSIDIAN RUSSIA — подтверждение email" if purpose=="verify"
                        else "OBSIDIAN RUSSIA — подтверждение нового email")
    message["Auto-Submitted"]="auto-generated"
    operation=("Подтверди адрес электронной почты для аккаунта OBSIDIAN RUSSIA."
               if purpose=="verify" else
               "Подтверди новый адрес электронной почты для своего аккаунта OBSIDIAN RUSSIA.")
    message.set_content(
        operation+"\n\nОткрой ссылку:\n"+url+"\n\n"
        "Ссылка действует 24 часа и работает только один раз.\n"
        "Если ты не запрашивал эту операцию, проигнорируй письмо.\n"
        "Никому не пересылай ссылку.\n",charset="utf-8")
    context=ssl.create_default_context()
    if settings["mode"]=="ssl":
        connection=smtplib.SMTP_SSL(settings["host"],settings["port"],timeout=8,context=context)
    else:
        connection=smtplib.SMTP(settings["host"],settings["port"],timeout=8)
    with connection as smtp:
        if settings["mode"]=="starttls":
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        if settings["username"]:
            smtp.login(settings["username"],settings["password"])
        smtp.send_message(message)
