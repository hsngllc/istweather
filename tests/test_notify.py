"""Bildirimler ve tekrarlayan iş hatası dinleyicisi."""

import json
from email.message import EmailMessage
from types import SimpleNamespace
from typing import Any, ClassVar

import httpx
import pytest
from pydantic import SecretStr

from hava.ops.notify import notify
from hava.scheduler.__main__ import FailureWatch
from hava.settings import Settings

FAKE_TOKEN = "123456:TEST-ONLY-TOKEN"  # test değeri, gerçek değil


def _settings(**kw: Any) -> Settings:
    base: dict[str, Any] = {"database_url": "postgresql+psycopg://x@localhost/x"}
    base.update(kw)
    return Settings(**base)


def test_without_channels_only_logs() -> None:
    assert notify("Konu", "Gövde", settings=_settings()) == []


def test_telegram_message() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    s = _settings(telegram_bot_token=SecretStr(FAKE_TOKEN), telegram_chat_id="42")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert notify("Veri kaynağı durdu: metar:LTFM", "ayrıntı", settings=s, client=client) == [
            "telegram"
        ]
    assert seen[0].url.path == f"/bot{FAKE_TOKEN}/sendMessage"
    payload = json.loads(seen[0].content)
    assert payload["chat_id"] == "42"
    assert payload["text"] == "Veri kaynağı durdu: metar:LTFM\nayrıntı"


def test_telegram_failure_does_not_raise_or_log_token(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False})

    s = _settings(telegram_bot_token=SecretStr(FAKE_TOKEN), telegram_chat_id="42")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert notify("Konu", "Gövde", settings=s, client=client) == []
    assert FAKE_TOKEN not in capsys.readouterr().out


class FakeSMTP:
    sent: ClassVar[list[EmailMessage]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.calls: list[str] = []

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        assert password == "test-only-password"

    def send_message(self, msg: EmailMessage) -> None:
        FakeSMTP.sent.append(msg)


def test_email_message() -> None:
    s = _settings(
        smtp_host="smtp.example.test",
        smtp_user="bot@example.test",
        smtp_password=SecretStr("test-only-password"),
        alert_email_to="ops@example.test",
    )
    assert notify("Konu", "Gövde", settings=s, smtp_factory=FakeSMTP) == ["email"]
    msg = FakeSMTP.sent[-1]
    assert msg["Subject"] == "[istweather] Konu" and msg["From"] == "bot@example.test"
    assert msg.get_content().strip() == "Gövde"


def test_failure_watch_notifies_at_threshold_and_on_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []
    monkeypatch.setattr(
        "hava.scheduler.__main__.notify", lambda subject, body: sent.append(subject) or []
    )
    watch = FailureWatch(threshold=3)
    fail = SimpleNamespace(job_id="collect_metar", exception=RuntimeError("AWC 503"))
    ok = SimpleNamespace(job_id="collect_metar", exception=None)
    for _ in range(4):
        watch(fail)  # type: ignore[arg-type]
    assert sent == ["İş tekrar tekrar hata veriyor: collect_metar"]
    watch(ok)  # type: ignore[arg-type]
    assert sent[-1] == "İş düzeldi: collect_metar"
    watch(ok)  # type: ignore[arg-type]
    assert len(sent) == 2
