"""Account security journal and best-effort notices for OBSIDIAN RUSSIA.

No IP, password, token, session cookie or email address is written to the
security journal. Notifications use only an already verified mailbox and
never determine whether the primary account operation succeeds.
"""
from email.message import EmailMessage
import logging
import smtplib
import ssl

import recovery
from db import now

EVENT_LABELS = {
    "password_changed": "Пароль изменён",
    "password_reset": "Пароль восстановлен",
    "email_change_requested": "Запрошена смена email",
    "email_changed": "Адрес email изменён",
    "email_verified": "Email подтверждён",
    "sessions_closed": "Остальные сеансы завершены",
    "sessions_closed_all": "Все сеансы завершены",
}
NOTIFIABLE = frozenset({
    "password_changed", "password_reset", "email_changed",
})


def record(c, user_id, event):
    """Append a privacy-minimal security event, keeping at most 100 per user."""
    if event not in EVENT_LABELS:
        raise ValueError("Unknown account security event")
    c.execute(
        "INSERT INTO account_security_events(user_id,event,created_at) VALUES(?,?,?)",
        (user_id, event, now()),
    )
    c.execute(
        "DELETE FROM account_security_events WHERE user_id=? AND id NOT IN "
        "(SELECT id FROM account_security_events WHERE user_id=? ORDER BY id DESC LIMIT 100)",
        (user_id, user_id),
    )


def recent(c, user_id, limit=8):
    limit=max(1,min(int(limit),20))
    return c.execute(
        "SELECT event,created_at FROM account_security_events WHERE user_id=? "
        "ORDER BY id DESC LIMIT ?", (user_id,limit),
    ).fetchall()


def send_notice(address, event):
    """Send a notice over the existing configured SSL/STARTTLS SMTP transport.

    Raises if SMTP is not configured or delivery failed. This is used only by
    best-effort wrappers, so no email failure can undo a committed change.
    """
    if event not in NOTIFIABLE or not recovery.EMAIL_PATTERN.fullmatch(address):
        raise ValueError("Invalid security notice")
    config=recovery.smtp_settings()
    if not config:
        raise ValueError("SMTP is not configured")
    message=EmailMessage()
    message["From"]=config["from_addr"]
    message["To"]=address
    message["Subject"]="OBSIDIAN RUSSIA — уведомление о безопасности"
    message["Auto-Submitted"]="auto-generated"
    description={
        "password_changed": "В твоём аккаунте OBSIDIAN RUSSIA изменён пароль.",
        "password_reset": "Пароль аккаунта OBSIDIAN RUSSIA восстановлен через подтверждённую почту.",
        "email_changed": "В аккаунте OBSIDIAN RUSSIA изменён адрес электронной почты.",
    }[event]
    message.set_content(
        description+"\n\nЕсли действие выполнено тобой, ничего делать не нужно.\n"
        "Если ты не выполнял это действие, свяжись с поддержкой OBSIDIAN RUSSIA.\n"
        "Не сообщай никому пароли, одноразовые коды и ссылки восстановления.\n",
        charset="utf-8",
    )
    context=ssl.create_default_context()
    if config["mode"]=="ssl":
        connection=smtplib.SMTP_SSL(
            config["host"],config["port"],timeout=5,context=context,
        )
    else:
        connection=smtplib.SMTP(config["host"],config["port"],timeout=5)
    with connection as smtp:
        if config["mode"]=="starttls":
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        if config["username"]:
            smtp.login(config["username"],config["password"])
        smtp.send_message(message)


def notify_address(address, event):
    """Never log recipient addresses or credentials; never propagate SMTP errors."""
    if not address or event not in NOTIFIABLE or not recovery.smtp_settings():
        return False
    try:
        send_notice(address,event)
        return True
    except Exception:
        # Network or SMTP failure never makes a password/email change fail.
        logging.warning("Account security notification failed (%s); check mail service",event)
        return False


def notify_verified(c,user_id,event):
    """Unverified historical email addresses cannot receive security notices."""
    row=c.execute(
        "SELECT email FROM users WHERE id=? AND email_verified_at IS NOT NULL",
        (user_id,),
    ).fetchone()
    return notify_address(row["email"],event) if row else False
