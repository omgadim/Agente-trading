"""Notificaciones/alertas (Adapter + DI).

Interfaz `Notifier` con implementaciones intercambiables. Telegram y Email usan un
`transport` inyectable para ser testeables sin red; por defecto emplean la
librería estándar (urllib / smtplib) con import perezoso.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable, List, Optional
from urllib import parse, request

logger = logging.getLogger("alerts")


class Notifier(ABC):
    """Contrato de un canal de notificación."""

    @abstractmethod
    def notify(self, message: str, subject: str = "Trading System",
               level: str = "info") -> bool:
        """Envía una notificación. Devuelve True si tuvo éxito."""


class LoggingNotifier(Notifier):
    """Notificador que escribe en el log (siempre disponible; útil de fallback)."""

    def notify(self, message: str, subject: str = "Trading System",
               level: str = "info") -> bool:
        log = getattr(logger, level if level in ("info", "warning", "error") else "info")
        log("[%s] %s", subject, message)
        return True


class CompositeNotifier(Notifier):
    """Reenvía a varios canales (fan-out). Éxito si todos tuvieron éxito."""

    def __init__(self, notifiers: List[Notifier]) -> None:
        self.notifiers = list(notifiers)

    def notify(self, message: str, subject: str = "Trading System",
               level: str = "info") -> bool:
        results = []
        for n in self.notifiers:
            try:
                results.append(n.notify(message, subject, level))
            except Exception as exc:  # un canal caído no debe tumbar los demás
                logger.warning("Canal de alerta falló: %s", exc)
                results.append(False)
        return all(results) if results else False


# Transporte HTTP por defecto (urllib). Se puede inyectar uno falso en tests.
def _default_http_post(url: str, data: dict, insecure: bool = False) -> bool:  # pragma: no cover
    import ssl
    from urllib.error import HTTPError
    payload = parse.urlencode(data).encode()
    req = request.Request(url, data=payload, method="POST")
    # `insecure`: para VPS con inspección SSL (antivirus/firewall que inyecta su
    # certificado). No verifica el certificado del servidor. Solo el token/mensaje
    # salen; úsalo solo si confías en la red del VPS (p. ej. tu propio EC2).
    ctx = ssl._create_unverified_context() if insecure else None
    try:
        with request.urlopen(req, timeout=10, context=ctx) as resp:
            return 200 <= resp.status < 300
    except HTTPError as exc:  # muestra el motivo real de Telegram (chat not found, etc.)
        body = exc.read().decode("utf-8", "replace")
        logger.warning("Telegram rechazó (HTTP %s): %s", exc.code, body)
        return False


class TelegramNotifier(Notifier):
    """Envía mensajes a un chat de Telegram vía Bot API."""

    def __init__(self, token: str, chat_id: str,
                 transport: Optional[Callable[[str, dict], bool]] = None,
                 insecure: bool = False) -> None:
        self.token = token
        self.chat_id = chat_id
        self.insecure = insecure
        self._transport = transport or (lambda url, data: _default_http_post(url, data, insecure))

    def notify(self, message: str, subject: str = "Trading System",
               level: str = "info") -> bool:
        icon = {"info": "ℹ️", "warning": "⚠️", "error": "🚨"}.get(level, "ℹ️")
        text = f"{icon} *{subject}*\n{message}"
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            return bool(self._transport(url, {
                "chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}))
        except Exception as exc:
            logger.warning("Telegram falló: %s", exc)
            return False


class EmailNotifier(Notifier):
    """Envía alertas por email (SMTP). `transport(msg) -> bool` inyectable."""

    def __init__(self, host: str, port: int, user: str, password: str,
                 to_addr: str, from_addr: Optional[str] = None,
                 transport: Optional[Callable[[dict], bool]] = None) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.to_addr = to_addr
        self.from_addr = from_addr or user
        self._transport = transport

    def notify(self, message: str, subject: str = "Trading System",
               level: str = "info") -> bool:
        envelope = {"from": self.from_addr, "to": self.to_addr,
                    "subject": f"[{level.upper()}] {subject}", "body": message}
        if self._transport is not None:
            return bool(self._transport(envelope))
        return self._smtp_send(envelope)

    def _smtp_send(self, envelope: dict) -> bool:  # pragma: no cover - usa red/SMTP
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(envelope["body"])
        msg["Subject"] = envelope["subject"]
        msg["From"] = envelope["from"]
        msg["To"] = envelope["to"]
        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.send_message(msg)
            return True
        except Exception as exc:
            logger.warning("Email falló: %s", exc)
            return False
