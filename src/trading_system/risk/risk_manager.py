"""Gestión de riesgo: sizing por ATR/porcentaje y validación (veto)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..core.enums import SignalType


@dataclass
class RiskParameters:
    account_balance: float = 10_000.0
    risk_per_trade_pct: float = 1.0  # % del balance arriesgado por operación
    max_daily_loss_pct: float = 5.0
    contract_size: float = 100.0  # XAUUSD: 100 oz por lote estándar
    min_lot: float = 0.01
    max_lot: float = 50.0
    lot_step: float = 0.01


@dataclass
class RiskDecision:
    approved: bool
    position_size: Optional[float]
    reason: str


class RiskManager:
    """Calcula tamaño de posición y aplica reglas de riesgo duras.

    Independiente de la dirección: recibe precio de entrada y stop y traduce el
    riesgo monetario objetivo en lotes. Tiene poder de veto (p. ej. si la pérdida
    diaria acumulada supera el máximo permitido).
    """

    def __init__(self, params: Optional[RiskParameters] = None) -> None:
        self.params = params or RiskParameters()
        self._daily_pnl: float = 0.0

    def register_pnl(self, pnl: float) -> None:
        self._daily_pnl += pnl

    def reset_daily(self) -> None:
        self._daily_pnl = 0.0

    def position_size(self, entry: float, stop_loss: float) -> float:
        """Lotes tales que la pérdida al tocar SL ≈ risk_per_trade_pct del balance."""
        p = self.params
        risk_amount = p.account_balance * (p.risk_per_trade_pct / 100.0)
        distance = abs(entry - stop_loss)
        if distance <= 0:
            return 0.0
        raw_lots = risk_amount / (distance * p.contract_size)
        # Redondeo al step y recorte a [min_lot, max_lot].
        stepped = round(raw_lots / p.lot_step) * p.lot_step
        return max(p.min_lot, min(p.max_lot, stepped))

    def evaluate(
        self,
        signal: SignalType,
        entry: float,
        stop_loss: Optional[float],
        agent_veto: bool = False,
        veto_reason: Optional[str] = None,
    ) -> RiskDecision:
        """Aprueba o rechaza una operación y calcula su tamaño."""
        p = self.params
        if signal is SignalType.WAIT:
            return RiskDecision(False, None, "Sin señal direccional")
        if agent_veto:
            return RiskDecision(False, None, veto_reason or "Veto de agente de riesgo")

        max_daily_loss = p.account_balance * (p.max_daily_loss_pct / 100.0)
        if self._daily_pnl <= -max_daily_loss:
            return RiskDecision(False, None, "Límite de pérdida diaria alcanzado")

        if stop_loss is None or stop_loss <= 0:
            return RiskDecision(False, None, "Sin stop loss válido para dimensionar")

        size = self.position_size(entry, stop_loss)
        if size <= 0:
            return RiskDecision(False, None, "Tamaño de posición nulo")
        return RiskDecision(True, size, f"Aprobado: {size:.2f} lotes")
