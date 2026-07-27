"""Tests de los agentes Smart Money / Price Action (Fase 2)."""
from __future__ import annotations

import pandas as pd
import pytest

from trading_system.agents.smart_money_agents import HarmonicPatternAgent
from trading_system.core import AgentDecision, AgentRegistry, MarketData, SignalType, Timeframe
from trading_system.core.market_data import MarketRegime

import trading_system.agents  # noqa: F401  (registro)

SMART_MONEY_AGENTS = [
    "smart_money", "order_blocks", "fair_value_gap",
    "liquidity_sweep", "wyckoff", "harmonic",
]


@pytest.mark.parametrize("name", SMART_MONEY_AGENTS)
def test_agent_returns_valid_decision(name, market_data):
    decision = AgentRegistry.create(name, {}).run(market_data)
    assert isinstance(decision, AgentDecision)
    assert decision.agent_name == name
    assert 0.0 <= decision.confidence <= 100.0
    assert decision.signal in (SignalType.BUY, SignalType.SELL, SignalType.WAIT)


@pytest.mark.parametrize("name", SMART_MONEY_AGENTS)
def test_agent_handles_tiny_dataset(name):
    """Con muy pocos datos, el agente responde WAIT sin lanzar excepción."""
    idx = pd.date_range("2024-01-01", periods=5, freq="5min")
    df = pd.DataFrame(
        {"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1000.0},
        index=idx,
    )
    md = MarketData("XAUUSD", {Timeframe.M5: df}, price=100.0, regime=MarketRegime(atr=1.0))
    decision = AgentRegistry.create(name, {}).run(md)
    assert decision.signal is SignalType.WAIT


def test_fvg_agent_buys_inside_bullish_gap():
    """Precio dentro de un FVG alcista reciente -> BUY."""
    rows = [(100.0, 100.5, 99.5, 100.0)] * 20
    rows += [
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 106.0, 100.0, 105.5),
        (105.0, 106.0, 104.0, 105.5),
    ]
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="5min")
    df = pd.DataFrame(
        {
            "open": [r[0] for r in rows], "high": [r[1] for r in rows],
            "low": [r[2] for r in rows], "close": [r[3] for r in rows],
            "volume": [1000.0] * len(rows),
        },
        index=idx, dtype=float,
    )
    # Precio 102 cae dentro del hueco [100.5, 104].
    md = MarketData("XAUUSD", {Timeframe.M5: df}, price=102.0, regime=MarketRegime(atr=2.0))
    decision = AgentRegistry.create("fair_value_gap", {"min_atr_frac": 0.0}).run(md)
    assert decision.signal is SignalType.BUY


# ---- Reconocedor de patrones armónicos (unidad) -----------------------------
def _xabcd(ab_r, bc_r, ad_r, xa=100.0):
    """Construye precios X,A,B,C,D alcistas con los ratios AB/XA, BC/AB y AD/XA."""
    x, a = 0.0, xa
    ab = ab_r * xa
    b = a - ab
    c = b + bc_r * ab
    d = a - ad_r * xa
    return x, a, b, c, d


def _classify(prices):
    return HarmonicPatternAgent._classify(*prices, tol=0.05)


def test_harmonic_gartley():
    assert _classify(_xabcd(0.618, 0.50, 0.786))[0] == "Gartley"


def test_harmonic_bat():
    assert _classify(_xabcd(0.45, 0.50, 0.886))[0] == "Bat"


def test_harmonic_butterfly():
    assert _classify(_xabcd(0.786, 0.50, 1.27))[0] == "Butterfly"


def test_harmonic_crab():
    assert _classify(_xabcd(0.50, 0.50, 1.618))[0] == "Crab"


def test_harmonic_deep_crab():
    assert _classify(_xabcd(0.886, 0.50, 1.618))[0] == "Deep Crab"


def test_harmonic_abcd():
    # bc/ab en 0.618-0.786 y cd/ab ≈ 1.0 -> AB=CD (prioritario)
    x, a, b = 0.0, 100.0, 30.0        # ab = 70
    c = b + 0.70 * 70                  # bc/ab = 0.70
    d = c - 70                         # cd/ab = 1.0
    assert _classify((x, a, b, c, d))[0] == "AB=CD"


def test_harmonic_5_0():
    x, a, b = 0.0, 100.0, -30.0       # ab = 130 -> ab/xa = 1.3
    c = b + 2.0 * 130                  # bc/ab = 2.0
    d = c - 0.50 * (c - b)            # cd/bc = 0.5
    assert _classify((x, a, b, c, d))[0] == "5-0"


def test_harmonic_shark():
    # shk_ab=bc/xa=1.3, shk_cd=cd/ab=2.0, shk_ext=|d-x|/xa=1.3
    assert _classify((0.0, 100.0, 200.0, 330.0, 130.0))[0] == "Shark"


def test_harmonic_rejects_unstructured_ratios():
    assert _classify((0.0, 100.0, 90.0, 95.0, 93.0)) is None


# ---- Elliott: impulso 1-5 + corrección ABC ----------------------------------
from trading_system.agents.smart_money_agents import ElliottWaveAgent  # noqa: E402
from trading_system.data.structure import Swing  # noqa: E402


def _swings(prices):
    """Construye pivotes alternados low/high a partir de precios (empieza en low)."""
    return [Swing(pos=i, price=p, kind=("low" if i % 2 == 0 else "high"))
            for i, p in enumerate(prices)]


# Precios de un impulso alcista limpio (0..5) + corrección ABC (5..8):
# 0(low) 1(high) 2(low) 3(high) 4(low) 5(high) 6(low=A) 7(high=B) 8(low=C)
_BULL = [100, 120, 110, 150, 135, 175, 150, 165, 152]


def test_elliott_bull_impulse_then_abc_is_buy():
    sig = ElliottWaveAgent._detect(_swings(_BULL), tol=0.05)
    assert sig is not None and sig[0] is SignalType.BUY


def test_elliott_bear_is_sell():
    # Espejo: se empieza en 'high' y los precios van invertidos.
    prices = [200 - p for p in _BULL]
    swings = [Swing(pos=i, price=p, kind=("high" if i % 2 == 0 else "low"))
              for i, p in enumerate(prices)]
    sig = ElliottWaveAgent._detect(swings, tol=0.05)
    assert sig is not None and sig[0] is SignalType.SELL


def test_elliott_rejects_wave4_overlap():
    # Onda 4 (índice 4) por debajo del techo de la onda 1 (índice 1) -> inválido.
    bad = [100, 120, 110, 150, 115, 175, 150, 165, 152]  # p4=115 < p1=120
    assert ElliottWaveAgent._detect(_swings(bad), tol=0.05) is None


def test_elliott_rejects_correction_erasing_impulse():
    # C (índice 8) por debajo del inicio del impulso (índice 0) -> inválido.
    bad = _BULL[:8] + [95]  # p8=95 < p0=100
    assert ElliottWaveAgent._detect(_swings(bad), tol=0.05) is None
