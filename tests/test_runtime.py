"""Tests del ensamblado en vivo (runtime builders)."""
from __future__ import annotations

from pathlib import Path

import pytest

from trading_system.alerts import Notifier
from trading_system.live import LiveStepResult, LiveTrader
from trading_system.risk import KillSwitch
from trading_system.runtime import (
    build_kill_switch,
    build_live_trader,
    build_notifier,
    build_repository,
)
from trading_system.utils import load_config

import trading_system.agents  # noqa: F401


@pytest.fixture
def config():
    return load_config(Path(__file__).resolve().parents[1] / "config" / "config.yaml")


def test_build_notifier_disabled_returns_none(config):
    config["alerts"] = {"enabled": False}
    assert build_notifier(config) is None


def test_build_notifier_logging(config):
    config["alerts"] = {"enabled": True, "channels": ["logging"]}
    n = build_notifier(config)
    assert isinstance(n, Notifier)
    assert n.notify("x") is True


def test_build_kill_switch_from_config(config):
    ks = build_kill_switch(config)  # config lo trae enabled: true
    assert isinstance(ks, KillSwitch)
    config["kill_switch"] = {"enabled": False}
    assert build_kill_switch(config) is None


def test_build_repository_sqlite(config, tmp_path):
    config["persistence"] = {"enabled": True, "backend": "sqlite",
                             "sqlite_path": str(tmp_path / "t.db")}
    repo = build_repository(config)
    assert repo is not None
    assert repo.pnl_summary()["trades"] == 0  # esquema inicializado
    repo.close()
    config["persistence"] = {"enabled": False}
    assert build_repository(config) is None


def test_build_live_trader_paper_runs(config):
    config["guards"] = {"allow_weekend": True, "trading_hours": [], "max_spread": None}
    trader, client = build_live_trader(config, mode="paper")
    assert isinstance(trader, LiveTrader)
    assert trader.kill_switch is not None       # config lo activa
    client.connect()
    result = trader.step()
    assert isinstance(result, LiveStepResult)
    # Avanza y da varios pasos sin romper.
    for _ in range(20):
        if not client.has_next():
            break
        client.advance(5)
        trader.step()
    client.shutdown()


def test_build_live_trader_live_mode_builds_real_client(config):
    # En modo live se construye RealMT5Client (sin conectar; connect fallaría sin MT5).
    from trading_system.execution import RealMT5Client
    trader, client = build_live_trader(config, mode="live")
    assert isinstance(client, RealMT5Client)
    assert isinstance(trader, LiveTrader)


def test_live_feed_uses_configured_timeframes(config):
    from trading_system.core.enums import Timeframe
    config.setdefault("mt5", {})["timeframes"] = ["M30", "H1", "H4"]
    trader, _client = build_live_trader(config, mode="paper")
    assert trader.feed.timeframes == (Timeframe.M30, Timeframe.H1, Timeframe.H4)
    # El primario (más fino) es M30 -> mismo timeframe de decisión que el backtest.
    assert min(trader.feed.timeframes, key=lambda t: t.minutes) is Timeframe.M30


def test_correlation_provider_wired_in_live(config):
    # Con symbols en config, el agente correlation recibe un provider MT5.
    # (El agente viene desactivado por defecto -A/B: -6% neto-; aquí lo reactivamos
    # explícitamente para probar el cableado del provider.)
    corr_cfg = config.setdefault("agents", {}).setdefault("correlation", {})
    corr_cfg["enabled"] = True
    corr_cfg["symbols"] = ["USDCHF", "AUDUSD"]
    trader, client = build_live_trader(config, mode="paper")
    corr = next(a for a in trader.supervisor.agents if a.name == "correlation")
    provider = corr.config.get("provider")
    assert provider is not None
    assert set(provider.symbols()) == {"USDCHF", "AUDUSD"}
    # El provider baja cierres reales del cliente simulado.
    client.connect()
    closes = provider.closes("AUDUSD", 30)
    assert closes is not None and len(closes) > 0
