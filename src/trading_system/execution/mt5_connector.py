"""Broker y feed de MetaTrader 5, construidos sobre la interfaz `MT5Client`.

Ni `MT5Broker` ni `MT5DataFeed` conocen la API concreta de MT5: dependen de
`MT5Client`, por lo que funcionan igual con `RealMT5Client` (producción) o
`SimulatedMT5Client` (tests/paper en cualquier SO).
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

from ..core.enums import Timeframe
from ..core.exceptions import ExecutionError
from ..core.market_data import MarketData
from ..data.feed import DataFeed, compute_regime
from .broker import ExecutionBroker, Order
from .mt5_client import MT5Client, OrderRequest, RealMT5Client


class MT5Broker(ExecutionBroker):
    """Ejecución de órdenes en MetaTrader 5 vía `MT5Client`."""

    def __init__(self, client: MT5Client, magic: int = 20250725) -> None:
        self.client = client
        self.magic = magic
        self.logger = logging.getLogger("broker.mt5")

    def open(self, order: Order) -> Order:
        req = OrderRequest(
            symbol=order.symbol,
            direction=order.direction,
            volume=order.volume,
            price=None,  # a mercado
            sl=order.stop_loss,
            tp=order.take_profit,
            magic=self.magic,
        )
        result = self.client.send_order(req)
        if not result.success:
            raise ExecutionError(f"order_send falló ({result.retcode}): {result.comment}")
        order.ticket = result.ticket
        if result.price:
            order.price = result.price
        self.logger.info(
            "OPEN #%s %s %s vol=%.2f @ %.2f",
            order.ticket, order.direction.value, order.symbol, order.volume, order.price,
        )
        return order

    def modify(self, ticket: int, sl: Optional[float], tp: Optional[float]) -> bool:
        result = self.client.modify_position(ticket, sl, tp)
        if not result.success:
            self.logger.warning("modify #%s falló: %s", ticket, result.comment)
        return result.success

    def close(self, ticket: int, price: Optional[float] = None) -> float:
        # PnL flotante en el momento del cierre (aprox. del realizado).
        positions = {p.ticket: p for p in self.client.positions()}
        pos = positions.get(ticket)
        result = self.client.close_position(ticket)
        if not result.success:
            raise ExecutionError(f"cierre #{ticket} falló: {result.comment}")
        pnl = pos.profit if pos else 0.0
        self.logger.info("CLOSE #%s pnl=%.2f", ticket, pnl)
        return pnl

    def open_positions(self) -> List[Order]:
        orders: List[Order] = []
        for p in self.client.positions():
            orders.append(Order(
                symbol=p.symbol, direction=p.direction, volume=p.volume,
                price=p.price_open, stop_loss=p.sl, take_profit=p.tp, ticket=p.ticket,
            ))
        return orders

    def poll_closed_deals(self):
        """Delega en el cliente la lista de operaciones cerradas recientes."""
        return self.client.poll_closed_deals()


class MT5DataFeed(DataFeed):
    """Fuente de datos multi-timeframe en vivo desde MetaTrader 5."""

    def __init__(
        self,
        client: MT5Client,
        timeframes: Iterable[Timeframe] = (
            Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4,
        ),
        bars: int = 500,
    ) -> None:
        self.client = client
        self.timeframes = tuple(timeframes)
        self.bars = bars

    def get_market_data(self, symbol: str = "XAUUSD") -> MarketData:
        frames: Dict[Timeframe, "object"] = {}
        for tf in self.timeframes:
            df = self.client.rates(symbol, tf, self.bars)
            if df is not None and not df.empty:
                frames[tf] = df
        if not frames:
            raise ExecutionError(f"Sin datos de {symbol} desde MT5")

        tick = self.client.tick(symbol)
        primary = frames[min(frames, key=lambda t: t.minutes)]
        regime = compute_regime(frames.get(Timeframe.H1, primary))
        return MarketData(
            symbol=symbol,
            frames=frames,
            price=tick.mid,
            spread=max(0.0, tick.ask - tick.bid),
            regime=regime,
        )


def build_real_mt5(
    login: Optional[int] = None,
    password: Optional[str] = None,
    server: Optional[str] = None,
    path: Optional[str] = None,
    magic: int = 20250725,
) -> RealMT5Client:
    """Ayudante para crear (sin conectar) un cliente real de MT5."""
    return RealMT5Client(login=login, password=password, server=server, path=path, magic=magic)
