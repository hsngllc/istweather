"""Bildirimler: Telegram ve/veya e-posta (spec §14).

Kanal ayarlanmamışsa bildirim yalnız loga yazılır. Gönderim hatası işi durdurmaz. Telegram bot
token'ı istek adresinde gittiği için hata mesajı (adresi içerebilir) loga yazılmaz; yalnız hata türü
ve durum kodu yazılır.
"""

from __future__ import annotations

import smtplib
from collections.abc import Callable
from email.message import EmailMessage

import httpx
import structlog

from hava.settings import Settings, get_settings

log = structlog.get_logger()
TELEGRAM_API = "https://api.telegram.org"


def _send_telegram(client: httpx.Client, settings: Settings, text: str) -> None:
    token = settings.telegram_bot_token.get_secret_value()
    resp = client.post(
        f"{TELEGRAM_API}/bot{token}/sendMessage",
        json={"chat_id": settings.telegram_chat_id, "text": text, "disable_web_page_preview": True},
    )
    if resp.status_code != 200 or not resp.json().get("ok"):
        raise RuntimeError(f"telegram HTTP {resp.status_code}")


def _send_email(
    settings: Settings, subject: str, body: str, smtp_factory: Callable[..., smtplib.SMTP]
) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"[istweather] {subject}"
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = settings.alert_email_to
    msg.set_content(body)
    with smtp_factory(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_port != 465:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(msg)


def notify(
    subject: str,
    body: str,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
    smtp_factory: Callable[..., smtplib.SMTP] | None = None,
) -> list[str]:
    """Bildirimi ayarlı kanallara gönderir; gönderilen kanalların adlarını döndürür."""
    settings = settings or get_settings()
    log.warning("notification", subject=subject, body=body)
    sent: list[str] = []
    if settings.telegram_bot_token.get_secret_value() and settings.telegram_chat_id:
        own = client is None
        http = client or httpx.Client(timeout=20.0)
        try:
            _send_telegram(http, settings, f"{subject}\n{body}")
            sent.append("telegram")
        except Exception as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            log.error(
                "notification_failed",
                channel="telegram",
                error=type(exc).__name__,
                status=status,
                detail=str(exc) if isinstance(exc, RuntimeError) else None,
            )
        finally:
            if own:
                http.close()
    if settings.smtp_host and settings.alert_email_to:
        default_factory: Callable[..., smtplib.SMTP] = (
            smtplib.SMTP_SSL if settings.smtp_port == 465 else smtplib.SMTP
        )
        try:
            _send_email(settings, subject, body, smtp_factory or default_factory)
            sent.append("email")
        except Exception as exc:
            log.error("notification_failed", channel="email", error=type(exc).__name__)
    return sent
