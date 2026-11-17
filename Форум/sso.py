"""Forum client for OBSIDIAN RUSSIA's opt-in fixed-client SSO.

Only the website validates passwords. Existing forum accounts are never
automatically linked by email or username. New SSO accounts are members;
staff permissions must be assigned explicitly by a forum administrator.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import db

ISSUER = os.getenv("OBFORUM_SSO_ISSUER", "")
SECRET = os.getenv("OBFORUM_SSO_CLIENT_SECRET", "")
CLIENT = "forum"


def safe_issuer(url):
    try:
        p = urlsplit(url)
        if not p.hostname or p.username or p.password or p.query or p.fragment:
            return False
        if p.path not in ("", "/"):
            return False
        if p.scheme == "https":
            return True
        return p.scheme == "http" and p.hostname in ("localhost", "127.0.0.1", "::1")
    except ValueError:
        return False


def enabled():
    return len(SECRET) >= 32 and safe_issuer(ISSUER)


def valid_state(value):
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value))


def start(c, session_hash):
    state = secrets.token_urlsafe(36)
    digest = hashlib.sha256(state.encode("ascii")).hexdigest()
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec="seconds")
    c.execute("DELETE FROM sso_states WHERE expires_at<=?", (db.now(),))
    c.execute(
        "INSERT INTO sso_states(state_hash,session_hash,expires_at) VALUES(?,?,?)",
        (digest, session_hash, deadline),
    )
    url = ISSUER.rstrip("/") + "/sso/authorize?" + urlencode({"client": CLIENT, "state": state})
    return url


def consume_state(c, state, session_hash):
    if not valid_state(state):
        return False
    digest = hashlib.sha256(state.encode("ascii")).hexdigest()
    row = c.execute(
        "DELETE FROM sso_states WHERE state_hash=? AND session_hash=? AND expires_at>? RETURNING state_hash",
        (digest, session_hash, db.now()),
    ).fetchone()
    return row is not None


def exchange(code):
    if not enabled() or not re.fullmatch(r"[A-Za-z0-9_-]{30,128}", code):
        return None
    data = urlencode({"client_id": CLIENT, "client_secret": SECRET, "code": code}).encode("ascii")
    req = Request(
        ISSUER.rstrip("/") + "/sso/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=4) as resp:
            if resp.status != 200:
                return None
            info = json.loads(resp.read(2048).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeError):
        return None
    sub = str(info.get("sub", ""))
    username = info.get("username", "")
    if not re.fullmatch(r"[1-9][0-9]{0,17}", sub):
        return None
    if not isinstance(username, str) or not 3 <= len(username) <= 24:
        return None
    return sub, username


def forum_user(c, sub, display_name):
    linked = c.execute(
        "SELECT u.id,u.banned FROM sso_accounts l JOIN users u ON u.id=l.user_id "
        "WHERE l.provider_sub=?", (sub,)
    ).fetchone()
    if linked:
        return None if linked["banned"] else linked["id"]

    # We do not link old accounts by email: site email addresses are not verified.
    # Any local collision is resolved by a generated handle, not account takeover.
    suggestion = display_name if re.fullmatch(r"[A-Za-z0-9_]{3,24}", display_name) else "or_" + sub
    for attempt in range(10):
        suffix = "" if attempt == 0 else "_" + secrets.token_hex(3)
        name = (suggestion[:24-len(suffix)] + suffix)
        email = f"or-{sub}-{secrets.token_hex(4)}@accounts.invalid"
        if c.execute("SELECT 1 FROM users WHERE username=?", (name,)).fetchone():
            continue
        user_id = c.execute(
            "INSERT INTO users(username,email,password_hash,role,joined_at) VALUES(?,?,?,?,?)",
            (name, email, db.hash_password(secrets.token_urlsafe(48)), "member", db.now()),
        ).lastrowid
        c.execute("INSERT INTO sso_accounts(provider_sub,user_id) VALUES(?,?)", (sub, user_id))
        db.audit(c, user_id, "sso_signup", "obsidian-website")
        return user_id
    return None
