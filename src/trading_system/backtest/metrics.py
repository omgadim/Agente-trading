"""Cálculo de métricas de desempeño de una estrategia."""
from __future__ import annotations

import math
from typing import Dict, Sequence


def compute_metrics(pnls: Sequence[float], equity_curve: Sequence[float]) -> Dict[str, float]:
    """Métricas estándar a partir de los PnL por operación y la curva de equity.

    Devuelve: nº de operaciones, ganadoras/perdedoras, winrate, profit factor,
    expectancy, PnL neto, drawdown máximo y un Sharpe aproximado sobre operaciones.
    """
    n = len(pnls)
    if n == 0:
        return {
            "trades": 0, "wins": 0, "losses": 0, "winrate": 0.0,
            "profit_factor": 0.0, "expectancy": 0.0, "net_pnl": 0.0,
            "max_drawdown": 0.0, "sharpe": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
        }

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net = sum(pnls)

    winrate = len(wins) / n * 100.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
    expectancy = net / n

    mean = net / n
    if n > 1:
        variance = sum((p - mean) ** 2 for p in pnls) / (n - 1)
        std = math.sqrt(variance)
        sharpe = (mean / std * math.sqrt(n)) if std > 0 else 0.0
    else:
        sharpe = 0.0

    max_dd = _max_drawdown(equity_curve)

    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "winrate": round(winrate, 2),
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else float("inf"),
        "expectancy": round(expectancy, 2),
        "net_pnl": round(net, 2),
        "max_drawdown": round(max_dd, 2),
        "sharpe": round(sharpe, 3),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
    }


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    """Máxima caída pico-valle (en unidades de la curva)."""
    peak = -math.inf
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    return max_dd
