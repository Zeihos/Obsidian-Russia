"""Email password recovery for OBSIDIAN RUSSIA.

Opt-in: SMTP with TLS and a safe site URL are required. Password recovery
tokens are never logged or stored in plaintext. Nothing is mailed until the
operator configures the real SMTP environment.
"""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parseaddr
import hashlib
import os
import re
import secrets
import smtplib
import ssl
from urllib.parse import urlencode, urlsplit

from db import hash_password, now

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{40,128}\Z")
EMAIL_PATTERN = re.compile(r"[^\s@]{1,64}@[^\s@]{1,180}\.[^\s@]{2,}\Z")
TTL_MINUTES = 30


def site_base(url):
    """Only HTTPS origins, except for loopback HTTP development."""
    try:
        parsed = urlsplit(url)
        if (parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/") or not parsed.hostname):
            return None
        if parsed.scheme == "https":
            return url.rstrip("/")
        if parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1"):
            return url.rstrip("/")
    except ValueError:
        pass
    return None


def smtp_settings():
    host = os.getenv("OBSIDIAN_SMTP_HOST", "").strip()
    raw_port = os.getenv("OBSIDIAN_SMTP_PORT", "465")
    sender = os.getenv("OBSIDIAN_SMTP_FROM", "").strip()
    mode = os.getenv("OBSIDIAN_SMTP_SECURITY", "ssl").lower()
    username = os.getenv("OBSIDIAN_SMTP_USER", "")
    password = os.getenv("OBSIDIAN_SMTP_PASSWORD", "")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        return None
    if not (host and 1 <= port <= 65535 and mode in ("ssl", "starttls")):
        return None
    if not EMAIL_PATTERN.fullmatch(sender) or parseaddr(sender)[1] != sender:
        return None
    if bool(username) != bool(password):
        return None
    if any(ord(char) < 33 or ord(char) > 126 for char in host):
        return None
    return dict(host=host,port=port,from_addr=sender,mode=mode,username=username,password=password)


def enabled(site_url):
    return site_base(site_url) is not None and smtp_settings() is not None


def digest(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def valid_token(token):
    return isinstance(token, str) and bool(TOKEN_PATTERN.fullmatch(token))


def issue(c, user_id):
    """Create a one-time, hashed, short-lived token for an existing account."""
    token = secrets.token_urlsafe(36)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=TTL_MINUTES)).isoformat(timespec="seconds")
    c.execute("DELETE FROM password_resets WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM password_resets WHERE expires_at<=?", (now(),))
    c.execute("INSERT INTO password_resets(token_hash,user_id,expires_at) VALUES(?,?,?)",
              (digest(token), user_id, expires))
    return token


def cancel(c, token):
    if valid_token(token):
        c.execute("DELETE FROM password_resets WHERE token_hash=?", (digest(token),))


def exists(c, token):
    return (valid_token(token) and c.execute(
        "SELECT 1 FROM password_resets WHERE token_hash=? AND expires_at>?",
        (digest(token), now()),
    ).fetchone() is not None)


def redeem(c, token, new_password):
    """Consume a token exactly once, rotate credentials, revoke SSO and sessions."""
    if not valid_token(token) or not 10 <= len(new_password) <= 128:
        return False
    record = c.execute(
        "DELETE FROM password_resets WHERE token_hash=? AND expires_at>? RETURNING user_id",
        (digest(token), now()),
    ).fetchone()
    if not record:
        return False
    user_id = record["user_id"]
    c.execute("UPDATE users SET password_hash=?,auth_version=auth_version+1 WHERE id=?",
              (hash_password(new_password), user_id))
    c.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM sso_codes WHERE user_id=?", (user_id,))
    return True


def send_email(to_address, token, base_url):
    config = smtp_settings()
    base = site_base(base_url)
    if not config or not base or not EMAIL_PATTERN.fullmatch(to_address) or not valid_token(token):
        raise ValueError("Password recovery email is not configured correctly")

    url = base + "/reset?" + urlencode({"token": token})
    message = EmailMessage()
    message["From"] = config["from_addr"]
    message["To"] = to_address
    message["Subject"] = "OBSIDIAN RUSSIA — восстановление доступа"
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(
        "Получен запрос на восстановление пароля OBSIDIAN RUSSIA.\n\n"
        f"Для создания нового пароля открой ссылку:\n{url}\n\n"
        f"Ссылка действует {TTL_MINUTES} минут и работает только один раз.\n"
        "Если ты не запрашивал восстановление, просто проигнорируй письмо.\n"
        "Никому не пересылай эту ссылку.\n",
        charset="utf-8",
    )
    context = ssl.create_default_context()
    if config["mode"] == "ssl":
        server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=8, context=context)
    else:
        server = smtplib.SMTP(config["host"], config["port"], timeout=8)
    with server as smtp:
        if config["mode"] == "starttls":
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        if config["username"]:
            smtp.login(config["username"], config["password"])
        smtp.send_message(message)
