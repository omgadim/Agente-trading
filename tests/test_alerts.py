"""Tests del sistema de alertas/notificaciones."""
from __future__ import annotations

from trading_system.alerts import (
    CompositeNotifier,
    EmailNotifier,
    LoggingNotifier,
    Notifier,
    TelegramNotifier,
)


def test_logging_notifier_succeeds():
    assert LoggingNotifier().notify("hola", "test", "info") is True


def test_composite_fan_out_all_success():
    comp = CompositeNotifier([LoggingNotifier(), LoggingNotifier()])
    assert comp.notify("x") is True


class _FailingNotifier(Notifier):
    def notify(self, message, subject="Trading System", level="info"):
        return False


class _RaisingNotifier(Notifier):
    def notify(self, message, subject="Trading System", level="info"):
        raise RuntimeError("canal caído")


def test_composite_reports_failure_but_isolates_exceptions():
    comp = CompositeNotifier([LoggingNotifier(), _FailingNotifier()])
    assert comp.notify("x") is False
    # Una excepción en un canal no debe propagarse.
    comp2 = CompositeNotifier([LoggingNotifier(), _RaisingNotifier()])
    assert comp2.notify("x") is False


def test_telegram_uses_transport():
    captured = {}

    def fake_transport(url, data):
        captured["url"] = url
        captured["data"] = data
        return True

    notifier = TelegramNotifier("TOKEN123", "CHAT456", transport=fake_transport)
    assert notifier.notify("mensaje", "Alerta", "error") is True
    assert "TOKEN123" in captured["url"]
    assert captured["data"]["chat_id"] == "CHAT456"
    assert "mensaje" in captured["data"]["text"]


def test_telegram_transport_failure_returns_false():
    def boom(url, data):
        raise ConnectionError("sin red")

    assert TelegramNotifier("t", "c", transport=boom).notify("x") is False


def test_email_uses_injected_transport():
    sent = {}

    def fake_transport(envelope):
        sent.update(envelope)
        return True

    notifier = EmailNotifier("smtp", 587, "u@x.com", "pw", "to@x.com",
                             transport=fake_transport)
    assert notifier.notify("cuerpo", "Asunto", "warning") is True
    assert sent["to"] == "to@x.com"
    assert "WARNING" in sent["subject"]
    assert sent["body"] == "cuerpo"
