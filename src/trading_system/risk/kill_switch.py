"""Kill switch / watchdog: corta la operativa ante condiciones de riesgo.

Vigila pérdida diaria, drawdown de la equity realizada, rachas de pérdidas y un
flag manual (fichero). Cuando se dispara, el `LiveTrader` deja de abrir nuevas
operaciones. Complementa al `RiskManager` (que dimensiona y veta por operación).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


@dataclass
class KillSwitchConfig:
    max_daily_loss: Optional[float] = None        # pérdida diaria máxima (dinero, valor positivo)
    max_drawdown: Optional[float] = None          # drawdown máximo de equity realizada (dinero)
    max_consecutive_losses: Optional[int] = None  # rachas de pérdidas consecutivas
    flag_file: Optional[str] = None               # si existe, dispara el corte manual


class KillSwitch:
    """Estado de corte de emergencia basado en condiciones de riesgo."""

    def __init__(self, config: Optional[KillSwitchConfig] = None) -> None:
        self.config = config or KillSwitchConfig()
        self.logger = logging.getLogger("kill_switch")
        self._daily_pnl = 0.0
        self._realized_equity = 0.0
        self._peak_equity = 0.0
        self._consecutive_losses = 0
        self._tripped = False
        self._reason: Optional[str] = None

    @property
    def tripped(self) -> bool:
        return self._tripped

    @property
    def reason(self) -> Optional[str]:
        return self._reason

    def record_trade(self, pnl: float) -> None:
        """Registra el resultado de una operación cerrada y reevalúa condiciones."""
        self._daily_pnl += pnl
        self._realized_equity += pnl
        self._peak_equity = max(self._peak_equity, self._realized_equity)
        self._consecutive_losses = self._consecutive_losses + 1 if pnl < 0 else 0
        self._evaluate()

    def _evaluate(self) -> None:
        c = self.config
        if c.max_daily_loss is not None and self._daily_pnl <= -abs(c.max_daily_loss):
            self.trip(f"Pérdida diaria {self._daily_pnl:.2f} supera el máximo {c.max_daily_loss}")
        drawdown = self._peak_equity - self._realized_equity
        if c.max_drawdown is not None and drawdown >= abs(c.max_drawdown):
            self.trip(f"Drawdown {drawdown:.2f} supera el máximo {c.max_drawdown}")
        if (c.max_consecutive_losses is not None
                and self._consecutive_losses >= c.max_consecutive_losses):
            self.trip(f"{self._consecutive_losses} pérdidas consecutivas")

    def check(self) -> Tuple[bool, str]:
        """Devuelve (operativa_permitida, motivo). Consulta también el flag manual."""
        if self.config.flag_file and Path(self.config.flag_file).exists():
            self.trip("Kill switch manual activado (flag file)")
        if self._tripped:
            return False, self._reason or "Kill switch activado"
        return True, "OK"

    def trip(self, reason: str) -> None:
        if not self._tripped:
            self.logger.error("KILL SWITCH: %s", reason)
        self._tripped = True
        self._reason = reason

    def reset(self) -> None:
        """Reinicia por completo (uso manual tras revisar)."""
        self._tripped = False
        self._reason = None
        self._consecutive_losses = 0

    def reset_daily(self) -> None:
        """Reinicia el contador de pérdida diaria (nuevo día de sesión)."""
        self._daily_pnl = 0.0
