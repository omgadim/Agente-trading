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
from .context import MT5CorrelationProvider
from .core.enums import Timeframe
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
#  Multi-instrumento
# --------------------------------------------------------------------------- #
def apply_instrument(config: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Aplica el perfil de un instrumento (`instruments.<name>`) sobre el config.

    Cada instrumento corre en su propia instancia. El perfil sobreescribe lo que
    es específico del activo (símbolo del broker, tamaño de contrato, spread
    máximo del guardián, y ficheros propios de persistencia/fichas) SIN tocar la
    estrategia (agentes, pesos, riesgo %). Devuelve una copia; no muta el original.
    """
    import copy

    instruments = (config.get("instruments") or {})
    profile = instruments.get(name)
    if profile is None:
        raise ValueError(f"Instrumento '{name}' no está en config.instruments "
                         f"(disponibles: {list(instruments)})")
    cfg = copy.deepcopy(config)
    cfg["symbol"] = profile.get("symbol", name)
    if "contract_size" in profile:
        cfg.setdefault("risk", {})["contract_size"] = profile["contract_size"]
    if "max_spread" in profile:
        cfg.setdefault("guards", {})["max_spread"] = profile["max_spread"]
    if "sqlite_path" in profile:
        cfg.setdefault("persistence", {})["sqlite_path"] = profile["sqlite_path"]
    if "cards_path" in profile:
        cfg.setdefault("live", {})["cards_path"] = profile["cards_path"]
    # Gestión de posición por instrumento: permite un break-even/trailing propio
    # (p.ej. índices necesitan más aire que el Oro para no scratchear en pullbacks).
    if "be_trigger" in profile:
        cfg.setdefault("live", {})["be_trigger"] = profile["be_trigger"]
    if "trail_trigger" in profile:
        cfg.setdefault("live", {})["trail_trigger"] = profile["trail_trigger"]
    return cfg


def enabled_instruments(config: Dict[str, Any]) -> list:
    """Nombres de los instrumentos con `enabled: true` en config.instruments."""
    return [n for n, p in (config.get("instruments") or {}).items()
            if (p or {}).get("enabled", False)]


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
        insecure = os.getenv("TELEGRAM_INSECURE_SSL", "").lower() in ("1", "true", "yes")
        if token and chat:
            notifiers.append(TelegramNotifier(token, chat, insecure=insecure))
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
        regime_switch=config.get("regime_switch"),
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
    # Timeframe de análisis en vivo. Por defecto el más fino es M30 (coincide con
    # el backtest validado); el runner revisa cada `interval` seg pero decide con
    # velas M30 cerradas → misma calidad que lo validado, sin ruido de M5.
    tf_names = mt5_cfg.get("timeframes") or ["M30", "H1", "H4"]
    timeframes = tuple(Timeframe[name] for name in tf_names)
    feed = MT5DataFeed(
        client,
        timeframes=timeframes,
        bars=mt5_cfg.get("bars", 500),
        closed_bars_only=mt5_cfg.get("closed_bars_only", True),
    )
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
        cards_path=live_cfg.get("cards_path"),
    )
    _wire_correlation(trader, client, config)
    return trader, client


def _wire_correlation(trader: LiveTrader, client: MT5Client, config: Dict[str, Any]) -> None:
    """Inyecta un provider de correlación (símbolos MT5) al agente `correlation`.

    Los símbolos (USDCHF, AUDUSD...) se toman de `agents.correlation.symbols` y se
    bajan del broker vía el cliente. Sin símbolos configurados, el agente sigue
    inerte (WAIT). Es solo-live: en backtest no interviene.
    """
    corr_cfg = (config.get("agents", {}) or {}).get("correlation", {}) or {}
    symbols = corr_cfg.get("symbols")
    if not symbols:
        return
    tf = Timeframe[corr_cfg.get("timeframe", "H1")]
    provider = MT5CorrelationProvider(client, symbols, tf)
    for agent in trader.supervisor.agents:
        if agent.name == "correlation":
            agent.config["provider"] = provider
