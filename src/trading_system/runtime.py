"""Ensamblado del sistema en vivo desde configuración (builders).

Construye el `LiveTrader` completo —feed, broker, supervisor, riesgo, guardián,
kill switch, alertas y persistencia— a partir del `config` y del entorno. La misma
función sirve para modo *paper* (cliente MT5 simulado, corre en cualquier SO) y
*live* (RealMT5Client, solo Windows con terminal MT5), cambiando `mode`.

Credenciales y secretos SIEMPRE por variables de entorno (nunca en el config).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

from .alerts import CompositeNotifier, EmailNotifier, LoggingNotifier, Notifier, TelegramNotifier
from .data import SimulatedDataFeed
from .engine import build_agents, build_weighting
from .execution import (
    MarketGuard,
    MT5Broker,
    MT5Client,
    MT5DataFeed,
    RealMT5Client,
    SimulatedMT5Client,
)
from .live import LiveTrader
from .persistence import MySQLRepository, Repository, SqliteRepository
from .risk import KillSwitch, KillSwitchConfig, RiskManager, RiskParameters
from .supervisor import Supervisor

logger = logging.getLogger("runtime")


# --------------------------------------------------------------------------- #
#  Componentes individuales
# --------------------------------------------------------------------------- #
def build_notifier(config: Dict[str, Any]) -> Optional[Notifier]:
    cfg = config.get("alerts", {}) or {}
    if not cfg.get("enabled", False):
        return None
    channels = [c.lower() for c in cfg.get("channels", ["logging"])]
    notifiers = []
    if "logging" in channels:
        notifiers.append(LoggingNotifier())
    if "telegram" in channels:
        token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        if token and chat:
            notifiers.append(TelegramNotifier(token, chat))
        else:
            logger.warning("Telegram activado pero faltan TELEGRAM_TOKEN/TELEGRAM_CHAT_ID")
    if "email" in channels:
        host, user, pw = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
        to_addr = os.getenv("ALERT_TO")
        if host and user and pw and to_addr:
            notifiers.append(EmailNotifier(host, int(os.getenv("SMTP_PORT", "587")),
                                           user, pw, to_addr))
        else:
            logger.warning("Email activado pero faltan variables SMTP_*/ALERT_TO")
    if not notifiers:
        return None
    return notifiers[0] if len(notifiers) == 1 else CompositeNotifier(notifiers)


def build_kill_switch(config: Dict[str, Any]) -> Optional[KillSwitch]:
    cfg = config.get("kill_switch", {}) or {}
    if not cfg.get("enabled", False):
        return None
    return KillSwitch(KillSwitchConfig(
        max_daily_loss=cfg.get("max_daily_loss"),
        max_drawdown=cfg.get("max_drawdown"),
        max_consecutive_losses=cfg.get("max_consecutive_losses"),
        flag_file=cfg.get("flag_file"),
    ))


def build_repository(config: Dict[str, Any]) -> Optional[Repository]:
    cfg = config.get("persistence", {}) or {}
    if not cfg.get("enabled", False):
        return None
    backend = cfg.get("backend", "sqlite")
    if backend == "mysql":
        repo: Repository = MySQLRepository(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("DB_NAME", "trading_system"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
        )
    else:
        repo = SqliteRepository(cfg.get("sqlite_path", "data/trading.db"))
    repo.initialize()
    return repo


def build_market_guard(config: Dict[str, Any]) -> MarketGuard:
    cfg = config.get("guards", {}) or {}
    return MarketGuard(
        max_spread=cfg.get("max_spread"),
        trading_hours=[tuple(w) for w in cfg.get("trading_hours", [])],
        allow_weekend=cfg.get("allow_weekend", False),
    )


def build_supervisor(config: Dict[str, Any], risk_manager: RiskManager) -> Supervisor:
    sup_cfg = config.get("supervisor", {}) or {}
    return Supervisor(
        agents=build_agents(config),
        weighting=build_weighting(config),
        risk_manager=risk_manager,
        buy_threshold=sup_cfg.get("buy_threshold", 0.15),
        conflict_threshold=sup_cfg.get("conflict_threshold", 0.5),
    )


def build_mt5_client(
    config: Dict[str, Any], mode: str = "paper", base_df=None
) -> MT5Client:
    """Crea el cliente MT5 (sin conectar). paper -> simulado; live -> real."""
    if mode == "live":
        mt5_cfg = config.get("mt5", {}) or {}
        return RealMT5Client(
            login=int(os.getenv("MT5_LOGIN")) if os.getenv("MT5_LOGIN") else None,
            password=os.getenv("MT5_PASSWORD"),
            server=os.getenv("MT5_SERVER"),
            path=mt5_cfg.get("path"),
            magic=mt5_cfg.get("magic", 20250725),
            filling=mt5_cfg.get("filling", "IOC"),
        )
    # paper: serie simulada reproducible.
    if base_df is None:
        base_df = SimulatedDataFeed(base_price=2000.0, drift=0.05, volatility=1.2,
                                    bars=3000, seed=777).generate()
    return SimulatedMT5Client(base_df, symbol=config.get("symbol", "XAUUSD"),
                              start=500, spread=(config.get("costs", {}) or {}).get("spread", 0.2))


# --------------------------------------------------------------------------- #
#  Ensamblado completo
# --------------------------------------------------------------------------- #
def build_live_trader(
    config: Dict[str, Any], mode: str = "paper", client: Optional[MT5Client] = None
) -> Tuple[LiveTrader, MT5Client]:
    """Ensambla el LiveTrader completo desde config. Devuelve (trader, client).

    El cliente se devuelve SIN conectar: el runner llama a `client.connect()`.
    """
    client = client or build_mt5_client(config, mode)
    mt5_cfg = config.get("mt5", {}) or {}
    live_cfg = config.get("live", {}) or {}

    risk = RiskManager(RiskParameters(**(config.get("risk", {}) or {})))
    feed = MT5DataFeed(client, bars=mt5_cfg.get("bars", 500))
    broker = MT5Broker(client, magic=mt5_cfg.get("magic", 20250725))

    trader = LiveTrader(
        feed=feed,
        broker=broker,
        supervisor=build_supervisor(config, risk),
        risk_manager=risk,
        guard=build_market_guard(config),
        symbol=config.get("symbol", "XAUUSD"),
        max_positions=live_cfg.get("max_positions", 1),
        be_trigger=live_cfg.get("be_trigger", 1.0),
        trail_trigger=live_cfg.get("trail_trigger", 2.0),
        repository=build_repository(config),
        kill_switch=build_kill_switch(config),
        notifier=build_notifier(config),
    )
    return trader, client
