"""Tüm testler için ortak koruma.

Testler gerçek bildirim kanallarına asla ulaşmamalı: yerel ``.env``'deki Telegram/SMTP ayarları
ortam değişkenleriyle boşaltılır (pydantic-settings'te ortam değişkeni ``.env``'den önce gelir).
"""

from collections.abc import Iterator

import pytest

from hava.settings import get_settings

NOTIFY_KEYS = (
    "HAVA_TELEGRAM_BOT_TOKEN",
    "HAVA_TELEGRAM_CHAT_ID",
    "HAVA_SMTP_HOST",
    "HAVA_SMTP_USER",
    "HAVA_SMTP_PASSWORD",
    "HAVA_SMTP_FROM",
    "HAVA_ALERT_EMAIL_TO",
)


@pytest.fixture(autouse=True)
def _no_real_notifications(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in NOTIFY_KEYS:
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
