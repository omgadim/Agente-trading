"""Tests del guardián de mercado y de las reglas de gestión de posiciones."""
from __future__ import annotations

from datetime import datetime, timezone

from trading_system.execution import MarketGuard
from trading_system.risk import trailing_actions


# ---- MarketGuard ------------------------------------------------------------
def test_guard_blocks_weekend():
    guard = MarketGuard(allow_weekend=False)
    saturday = datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc)  # sábado
    ok, reason = guard.check(spread=0.2, now=saturday)
    assert ok is False and "semana" in reason.lower()


def test_guard_blocks_wide_spread():
    guard = MarketGuard(max_spread=0.5, allow_weekend=True)
    wednesday = datetime(2024, 1, 3, 12, 0, tzinfo=timezone.utc)
    ok, reason = guard.check(spread=1.2, now=wednesday)
    assert ok is False and "spread" in reason.lower()


def test_guard_allows_within_hours():
    guard = MarketGuard(trading_hours=[(7, 16)], allow_weekend=True)
    inside = datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc)
    outside = datetime(2024, 1, 3, 20, 0, tzinfo=timezone.utc)
    assert guard.check(0.2, inside)[0] is True
    assert guard.check(0.2, outside)[0] is False


def test_guard_hours_wrapping_midnight():
    guard = MarketGuard(trading_hours=[(22, 3)], allow_weekend=True)
    assert guard.check(0.2, datetime(2024, 1, 3, 23, 0, tzinfo=timezone.utc))[0] is True
    assert guard.check(0.2, datetime(2024, 1, 3, 1, 0, tzinfo=timezone.utc))[0] is True
    assert guard.check(0.2, datetime(2024, 1, 3, 12, 0, tzinfo=timezone.utc))[0] is False


# ---- trailing_actions -------------------------------------------------------
def test_no_actions_when_atr_zero():
    positions = [{"ticket": 1, "entry_price": 2000, "direction": "BUY"}]
    assert trailing_actions(positions, price=2050, atr=0.0) == []


def test_break_even_triggers_for_buy():
    positions = [{"ticket": 1, "entry_price": 2000, "direction": "BUY"}]
    # +1.5 ATR de beneficio -> break-even (>=1) pero no trailing (<2).
    actions = trailing_actions(positions, price=2015, atr=10.0)
    kinds = {a["action"] for a in actions}
    assert "move_to_break_even" in kinds
    assert "trailing_stop" not in kinds
    be = next(a for a in actions if a["action"] == "move_to_break_even")
    assert be["new_sl"] == 2000


def test_trailing_triggers_for_sell():
    positions = [{"ticket": 9, "entry_price": 2000, "direction": "SELL"}]
    # Precio 1975 => +2.5 ATR de beneficio (ATR=10) -> BE + trailing.
    actions = trailing_actions(positions, price=1975, atr=10.0)
    trail = [a for a in actions if a["action"] == "trailing_stop"]
    assert trail and trail[0]["new_sl"] == 1975 + 10  # a un ATR por encima
