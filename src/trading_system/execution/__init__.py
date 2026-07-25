"""Capa de ejecución de órdenes (paper y MetaTrader 5)."""
from __future__ import annotations

from .broker import ExecutionBroker, Order, PaperBroker
from .guards import MarketGuard
from .mt5_client import (
    AccountInfo,
    MT5Client,
    OrderRequest,
    OrderResult,
    Position,
    RealMT5Client,
    SimulatedMT5Client,
    SymbolInfo,
    Tick,
)
from .mt5_connector import MT5Broker, MT5DataFeed, build_real_mt5

__all__ = [
    "ExecutionBroker",
    "Order",
    "PaperBroker",
    "MarketGuard",
    "MT5Client",
    "RealMT5Client",
    "SimulatedMT5Client",
    "MT5Broker",
    "MT5DataFeed",
    "build_real_mt5",
    "AccountInfo",
    "SymbolInfo",
    "Tick",
    "Position",
    "OrderRequest",
    "OrderResult",
]
