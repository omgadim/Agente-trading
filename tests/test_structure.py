"""Tests del motor de estructura y liquidez con velas sintéticas."""
from __future__ import annotations

import pandas as pd

from trading_system.data import structure as st


def make_df(rows):
    """rows: lista de (open, high, low, close). Volumen fijo."""
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="5min")
    data = {
        "open": [r[0] for r in rows],
        "high": [r[1] for r in rows],
        "low": [r[2] for r in rows],
        "close": [r[3] for r in rows],
        "volume": [1000.0] * len(rows),
    }
    return pd.DataFrame(data, index=idx, dtype=float)


def flat(n, price=100.0):
    return [(price, price + 0.5, price - 0.5, price)] * n


# ---- FVG --------------------------------------------------------------------
def test_bullish_fvg_detected():
    rows = flat(15, 100.0)
    # 3 velas que crean un hueco alcista: vela -3 high=100.5, vela -1 low=104.
    rows += [(100.0, 100.5, 99.5, 100.0), (100.0, 106.0, 100.0, 105.5), (105.0, 106.0, 104.0, 105.5)]
    df = make_df(rows)
    fvgs = st.find_fvgs(df, min_atr_frac=0.0)
    bull = [f for f in fvgs if f.kind == "bullish"]
    assert bull, "debería detectar un FVG alcista"
    assert bull[-1].bottom == 100.5 and bull[-1].top == 104.0


def test_bearish_fvg_detected():
    rows = flat(15, 100.0)
    rows += [(100.0, 100.5, 99.5, 100.0), (100.0, 100.0, 94.0, 94.5), (95.0, 96.0, 94.0, 94.5)]
    df = make_df(rows)
    fvgs = st.find_fvgs(df, min_atr_frac=0.0)
    bear = [f for f in fvgs if f.kind == "bearish"]
    assert bear, "debería detectar un FVG bajista"
    assert bear[-1].contains(96.0)


# ---- Order Blocks -----------------------------------------------------------
def test_bullish_order_block_detected():
    rows = flat(20, 100.0)
    # Vela bajista seguida de impulso alcista fuerte que rompe su máximo.
    rows += [(100.0, 100.2, 98.0, 98.5)]          # OB bajista (origen)
    rows += [(98.5, 108.0, 98.5, 107.5)]          # impulso alcista fuerte
    df = make_df(rows)
    obs = st.find_order_blocks(df, impulse_atr=0.5)
    bull = [o for o in obs if o.kind == "bullish"]
    assert bull, "debería detectar un Order Block alcista"


def test_order_block_mitigation_removes_broken():
    rows = flat(20, 100.0)
    rows += [(100.0, 100.2, 98.0, 98.5)]      # OB alcista (origen bajista) en pos 20
    rows += [(98.5, 108.0, 98.5, 107.5)]      # impulso alcista fuerte (rompe el máximo)
    rows += [(107.0, 107.5, 96.0, 96.5)]      # cierre 96.5 < base 98.0 -> mitiga el OB
    df = make_df(rows)
    con = [o for o in st.find_order_blocks(df, impulse_atr=0.5, mitigation=True) if o.kind == "bullish"]
    sin = [o for o in st.find_order_blocks(df, impulse_atr=0.5, mitigation=False) if o.kind == "bullish"]
    assert not con, "el OB mitigado no debe devolverse con mitigation=True"
    assert sin, "sin mitigación el OB sí aparece"


def test_market_structure_choch_on_trend_flip():
    # Baja (LL) y luego rompe al alza (HH) -> primer giro = CHoCH alcista.
    swings = [
        st.Swing(0, 110, "high"), st.Swing(1, 100, "low"),
        st.Swing(2, 108, "high"), st.Swing(3, 95, "low"),   # BOS bajista
        st.Swing(4, 105, "high"), st.Swing(5, 90, "low"),   # BOS bajista (continuación)
        st.Swing(6, 112, "high"),                            # rompe al alza -> CHoCH
    ]
    state = st.market_structure(swings)
    assert state.trend == "bullish" and state.event == "CHoCH"


def test_market_structure_bos_continuation():
    # Máximos y mínimos crecientes -> continuación alcista (BOS, no CHoCH).
    swings = [
        st.Swing(0, 100, "low"), st.Swing(1, 110, "high"),
        st.Swing(2, 105, "low"), st.Swing(3, 115, "high"),  # HH -> BOS alcista
    ]
    state = st.market_structure(swings)
    assert state.trend == "bullish" and state.event == "BOS"


# ---- Swings y estructura ----------------------------------------------------
def test_swings_and_bullish_structure():
    # Zigzag ascendente: mínimos y máximos crecientes.
    rows = [
        (100, 102, 99, 101), (101, 103, 100, 102), (102, 101, 98, 99),   # low1
        (99, 106, 99, 105), (105, 107, 104, 106),                        # high1
        (106, 105, 102, 103), (103, 104, 101, 102),                      # low2 (>low1)
        (102, 110, 102, 109), (109, 112, 108, 111),                      # high2 (>high1)
        (111, 110, 107, 108), (108, 109, 106, 107),
    ]
    df = make_df(rows)
    swings = st.find_swings(df, 1, 1)
    assert len(swings) >= 4
    state = st.market_structure(swings)
    assert state.trend in ("bullish", "undefined")


# ---- Liquidez ---------------------------------------------------------------
def test_liquidity_pool_clusters_equal_highs():
    swings = [
        st.Swing(1, 100.0, "high"),
        st.Swing(5, 100.05, "high"),
        st.Swing(9, 100.02, "high"),
        st.Swing(3, 90.0, "low"),
    ]
    pools = st.find_liquidity(swings, tolerance=0.2)
    buy_side = [p for p in pools if p.kind == "buy_side"]
    assert buy_side and buy_side[0].count == 3


# ---- Sweeps -----------------------------------------------------------------
def test_bearish_sweep_detected():
    rows = flat(5, 100.0)
    rows[2] = (100.0, 105.0, 100.0, 104.0)  # swing high previo en 105
    rows += flat(3, 101.0)
    # Última vela: mecha sobre 105 pero cierra debajo -> sweep bajista.
    rows += [(102.0, 106.0, 101.0, 101.5)]
    df = make_df(rows)
    swings = st.find_swings(df, 1, 1)
    sweep = st.detect_sweep(df, swings, tolerance=0.1)
    assert sweep is not None and sweep.kind == "bearish"


# ---- Premium / Discount -----------------------------------------------------
def test_premium_discount_equilibrium():
    rows = [(100, 110, 90, 100)] + flat(10, 100.0)
    df = make_df(rows)
    hi, lo, eq = st.premium_discount(df, lookback=20)
    assert hi >= 110 and lo <= 90
    assert lo < eq < hi


# ---- Zigzag alternado -------------------------------------------------------
def test_alternating_collapses_same_kind():
    swings = [
        st.Swing(0, 100, "high"),
        st.Swing(2, 105, "high"),   # mismo tipo, más alto -> reemplaza
        st.Swing(4, 90, "low"),
        st.Swing(6, 88, "low"),     # mismo tipo, más bajo -> reemplaza
        st.Swing(8, 110, "high"),
    ]
    alt = st.alternating_swings(swings)
    kinds = [s.kind for s in alt]
    assert kinds == ["high", "low", "high"]
    assert alt[0].price == 105 and alt[1].price == 88
