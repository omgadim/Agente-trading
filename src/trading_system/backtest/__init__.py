"""Backtesting walk-forward y métricas de desempeño."""
from __future__ import annotations

from .engine import Backtester, BacktestResult, Trade
from .metrics import compute_metrics

__all__ = ["Backtester", "BacktestResult", "Trade", "compute_metrics"]
