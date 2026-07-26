"""Backtester walk-forward para el sistema multiagente.

Recorre una serie histórica barra a barra, reconstruye el `MarketData`
multi-timeframe hasta cada barra, pide la decisión al Supervisor y simula la
operación con SL/TP. Gestiona una posición a la vez (modelo simple y honesto) y
evita *look-ahead*: la decisión en la barra i solo usa datos hasta i.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from ..core import SignalType, Timeframe
from ..data import build_market_data
from ..supervisor import Supervisor
from .metrics import compute_metrics


@dataclass
class Trade:
    direction: SignalType
    entry_price: float
    entry_pos: int
    stop_loss: float
    take_profit: float
    size: float
    exit_price: Optional[float] = None
    exit_pos: Optional[int] = None
    pnl: Optional[float] = None
    reason: Optional[str] = None
    db_id: Optional[int] = None  # id en la base de datos (si hay persistencia)


@dataclass
class BacktestResult:
    trades: List[Trade]
    equity_curve: List[float]
    metrics: Dict[str, float]
    initial_equity: float

    def summary(self) -> str:
        m = self.metrics
        return (
            f"Operaciones: {m['trades']} | Winrate: {m['winrate']}% | "
            f"PF: {m['profit_factor']} | Expectancy: {m['expectancy']} | "
            f"PnL neto: {m['net_pnl']} | MaxDD: {m['max_drawdown']} | "
            f"Sharpe: {m['sharpe']}"
        )


class Backtester:
    """Motor de backtesting walk-forward sobre una serie del timeframe base."""

    def __init__(
        self,
        supervisor: Supervisor,
        symbol: str = "XAUUSD",
        contract_size: float = 100.0,
        base_minutes: int = 5,
        warmup: int = 200,
        step: int = 3,
        timeframes=(Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4),
        initial_equity: float = 10_000.0,
        spread: float = 0.2,
        learn: bool = False,
        repository=None,
        max_window: Optional[int] = None,
        sl_atr_mult: Optional[float] = None,
        tp_atr_mult: Optional[float] = None,
    ) -> None:
        self.supervisor = supervisor
        self.symbol = symbol
        self.contract_size = contract_size
        self.base_minutes = base_minutes
        self.warmup = warmup
        self.step = max(1, step)
        self.timeframes = timeframes
        self.initial_equity = initial_equity
        self.spread = spread
        self.learn = learn
        self.repository = repository
        # Ventana máxima de histórico remuestreado por paso (coste acotado en
        # series largas). None = todo el histórico (comportamiento original).
        self.max_window = max_window
        # Si se fijan, recalculan SL/TP desde el ATR del régimen (para optimizar
        # la política de salida sin tocar cada agente). None = usar niveles de los
        # agentes consolidados por el Supervisor.
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.logger = logging.getLogger("backtest")

    def run(self, base_df: pd.DataFrame) -> BacktestResult:
        n = len(base_df)
        if n <= self.warmup + self.step:
            raise ValueError("Serie demasiado corta para el warmup indicado")

        high = base_df["high"].to_numpy()
        low = base_df["low"].to_numpy()
        close = base_df["close"].to_numpy()

        equity = self.initial_equity
        equity_curve: List[float] = [equity]
        trades: List[Trade] = []
        open_trade: Optional[Trade] = None
        pending_feedback: List = []

        i = self.warmup
        while i < n:
            price = float(close[i])

            # 1) Gestionar posición abierta: ¿toca SL/TP en esta barra?
            if open_trade is not None:
                closed = self._try_close(open_trade, high[i], low[i], i)
                if closed:
                    trades.append(open_trade)
                    equity += open_trade.pnl
                    equity_curve.append(equity)
                    self._persist_close(open_trade)
                    if pending_feedback:
                        decisions, fb_md = pending_feedback.pop()
                        profitable = open_trade.pnl > 0
                        if self.learn:
                            self.supervisor.feedback(decisions, fb_md, profitable)
                        self._persist_performance(decisions, fb_md.regime.key, profitable)
                    open_trade = None

            # 2) Si estamos planos, evaluar una nueva decisión.
            if open_trade is None:
                lo = max(0, i + 1 - self.max_window) if self.max_window else 0
                window = base_df.iloc[lo : i + 1]
                md = build_market_data(
                    window, self.symbol, self.base_minutes, self.timeframes, self.spread
                )
                decision = self.supervisor.decide(md)
                sl, tp = self._resolve_levels(decision, price, md.regime.atr)
                if (
                    decision.signal in (SignalType.BUY, SignalType.SELL)
                    and not decision.vetoed
                    and sl and tp
                ):
                    open_trade = Trade(
                        direction=decision.signal,
                        entry_price=price,
                        entry_pos=i,
                        stop_loss=sl,
                        take_profit=tp,
                        size=decision.position_size or 0.1,
                    )
                    self._persist_open(open_trade, decision, md.regime.key)
                    if self.learn or self.repository is not None:
                        pending_feedback.append((decision.contributing, md))

            i += self.step

        # Cerrar posición residual al último precio.
        if open_trade is not None:
            open_trade.exit_price = float(close[-1])
            open_trade.exit_pos = n - 1
            open_trade.pnl = self._pnl(open_trade, open_trade.exit_price)
            open_trade.reason = "fin de serie"
            trades.append(open_trade)
            equity += open_trade.pnl
            equity_curve.append(equity)
            self._persist_close(open_trade)

        pnls = [t.pnl for t in trades if t.pnl is not None]
        metrics = compute_metrics(pnls, equity_curve)
        return BacktestResult(trades, equity_curve, metrics, self.initial_equity)

    def _resolve_levels(self, decision, price: float, atr: float):
        """SL/TP a usar: override por ATR si se configuró, si no los del Supervisor."""
        if self.sl_atr_mult is None and self.tp_atr_mult is None:
            return decision.stop_loss, decision.take_profit
        if atr <= 0 or decision.signal is SignalType.WAIT:
            return None, None
        sl_mult = self.sl_atr_mult if self.sl_atr_mult is not None else 1.5
        tp_mult = self.tp_atr_mult if self.tp_atr_mult is not None else 2.5
        if decision.signal is SignalType.BUY:
            return price - sl_mult * atr, price + tp_mult * atr
        return price + sl_mult * atr, price - tp_mult * atr

    # ---- persistencia (opcional) ----------------------------------------
    def _persist_open(self, trade: Trade, decision, regime: str) -> None:
        if self.repository is None:
            return
        decision_id = self.repository.save_decision(decision, self.symbol, regime)
        trade.db_id = self.repository.open_trade(
            self.symbol, trade.direction.value, trade.size, trade.entry_price,
            trade.stop_loss, trade.take_profit, decision_id=decision_id,
        )

    def _persist_close(self, trade: Trade) -> None:
        if self.repository is None or trade.db_id is None:
            return
        self.repository.close_trade(trade.db_id, trade.exit_price, trade.pnl)

    def _persist_performance(self, decisions, regime: str, profitable: bool) -> None:
        if self.repository is None:
            return
        for d in decisions:
            if d.signal is not SignalType.WAIT:
                self.repository.update_agent_performance(d.agent_name, regime, profitable)

    # ---- internos --------------------------------------------------------
    def _try_close(self, trade: Trade, bar_high: float, bar_low: float, pos: int) -> bool:
        """Cierra la operación si la barra alcanza SL o TP. SL tiene prioridad."""
        if trade.direction is SignalType.BUY:
            if bar_low <= trade.stop_loss:
                return self._close(trade, trade.stop_loss, pos, "SL")
            if bar_high >= trade.take_profit:
                return self._close(trade, trade.take_profit, pos, "TP")
        else:  # SELL
            if bar_high >= trade.stop_loss:
                return self._close(trade, trade.stop_loss, pos, "SL")
            if bar_low <= trade.take_profit:
                return self._close(trade, trade.take_profit, pos, "TP")
        return False

    def _close(self, trade: Trade, price: float, pos: int, reason: str) -> bool:
        trade.exit_price = price
        trade.exit_pos = pos
        trade.reason = reason
        trade.pnl = self._pnl(trade, price)
        return True

    def _pnl(self, trade: Trade, exit_price: float) -> float:
        direction = 1 if trade.direction is SignalType.BUY else -1
        return (exit_price - trade.entry_price) * direction * trade.size * self.contract_size
