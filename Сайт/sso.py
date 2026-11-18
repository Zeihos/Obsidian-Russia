"""Small opt-in SSO provider for the forum.

No user passwords leave the website. Codes last 90 seconds and are stored as
SHA-256 digests; the forum exchanges them using a server-side client secret.
This is an internal fixed-client protocol, not a general OAuth 2 provider.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import re
import secrets
from urllib.parse import parse_qs, urlencode, urlsplit

from db import now

CLIENT = "forum"
SECRET = os.getenv("OBSIDIAN_SSO_FORUM_SECRET", "")
CALLBACK = os.getenv("OBSIDIAN_SSO_FORUM_CALLBACK", "")


def safe_callback(url):
    try:
        p = urlsplit(url)
        if p.username or p.password or p.query or p.fragment:
            return False
        if p.path != "/sso/callback" or not p.hostname:
            return False
        if p.scheme == "https":
            return True
        return p.scheme == "http" and p.hostname in ("localhost", "127.0.0.1", "::1")
    except ValueError:
        return False


def enabled():
    return len(SECRET) >= 32 and safe_callback(CALLBACK)


def valid_state(value):
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value))


def authorization_path(client, state):
    if client != CLIENT or not valid_state(state):
        return ""
    return "/sso/authorize?" + urlencode({"client": client, "state": state})


def login_return(value):
    """Only the registered forum authorization flow is a valid login return."""
    if not value or len(value) > 280:
        return ""
    p = urlsplit(value)
    if p.path != "/sso/authorize" or p.scheme or p.netloc or p.fragment:
        return ""
    params = parse_qs(p.query)
    if len(params) != 2 or len(params.get("client", [])) != 1 or len(params.get("state", [])) != 1:
        return ""
    return authorization_path(params["client"][0], params["state"][0])


def issue_code(c, user_id):
    code = secrets.token_urlsafe(36)
    digest = hashlib.sha256(code.encode("ascii")).hexdigest()
    deadline = (datetime.now(timezone.utc) + timedelta(seconds=90)).isoformat(timespec="seconds")
    c.execute("DELETE FROM sso_codes WHERE expires_at<=?", (now(),))
    c.execute(
        "INSERT INTO sso_codes(code_hash,client_id,user_id,expires_at) VALUES(?,?,?,?)",
        (digest, CLIENT, user_id, deadline),
    )
    return code


def valid_client(client, secret):
    return (enabled() and client == CLIENT and isinstance(secret, str)
            and hmac.compare_digest(secret, SECRET))


def identity_version(c, client, secret, sub):
    """Authenticate server-to-server requests for the linked user's version."""
    if not valid_client(client, secret) or not isinstance(sub, str):
        return None
    if not re.fullmatch(r"[1-9][0-9]{0,17}", sub):
        return None
    row = c.execute('SELECT auth_version FROM users WHERE id=?', (int(sub),)).fetchone()
    return int(row['auth_version']) if row else None


def redeem_code(c, client, secret, code):
    if not valid_client(client, secret):
        return None
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{30,128}", code):
        return None
    digest = hashlib.sha256(code.encode("ascii")).hexdigest()
    row = c.execute(
        "DELETE FROM sso_codes WHERE code_hash=? AND client_id=? AND expires_at>? RETURNING user_id",
        (digest, CLIENT, now()),
    ).fetchone()
    if not row:
        return None
    user = c.execute("SELECT id,username,auth_version FROM users WHERE id=?", (row["user_id"],)).fetchone()
    if not user:
        return None
    return {"sub": str(user["id"]), "username": user["username"], "auth_version": int(user["auth_version"])}
