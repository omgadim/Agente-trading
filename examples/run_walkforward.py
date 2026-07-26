"""Rolling walk-forward: validación robusta a lo largo de varios tramos.

Desliza ventanas train->test por toda la serie. En cada tramo optimiza SL (por
ATR) en train y evalúa en el test inmediatamente siguiente (out-of-sample).
Reporta, por tramo, qué SL ganó y el desempeño OOS de la política fija
SL=1.0/TP=2.5, y agrega TODOS los tests en métricas globales — la prueba real de
robustez frente a un único split afortunado.

Uso:
    PYTHONPATH=src python -m examples.run_walkforward data/XAUUSD_M30.csv --base 30
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

from trading_system.backtest import Backtester
from trading_system.backtest.metrics import compute_metrics
from trading_system.data import load_ohlcv_csv, resample_ohlcv
from trading_system.engine import build_agents, build_weighting
from trading_system.supervisor import Supervisor
from trading_system.utils import load_config, setup_logging

import trading_system.agents  # noqa: F401

REF_SL, REF_TP = 1.0, 2.5  # política candidata a validar


def _run(df, config, base, step, warmup, max_window, sl, tp):
    sup = Supervisor(agents=build_agents(config), weighting=build_weighting(config))
    costs = config.get("costs", {}) or {}
    return Backtester(
        sup, base_minutes=base, warmup=warmup, step=step, learn=True,
        max_window=max_window, sl_atr_mult=sl, tp_atr_mult=tp,
        spread=costs.get("spread", 0.2), slippage=costs.get("slippage", 0.0),
        commission_per_lot=costs.get("commission_per_lot", 0.0),
    ).run(df)


def main() -> None:
    ap = argparse.ArgumentParser(description="Rolling walk-forward")
    ap.add_argument("csv")
    ap.add_argument("--base", type=int, default=30)
    ap.add_argument("--step", type=int, default=22)
    ap.add_argument("--warmup", type=int, default=400)
    ap.add_argument("--max-window", type=int, default=3000)
    ap.add_argument("--train-bars", type=int, default=16000)
    ap.add_argument("--test-bars", type=int, default=7000)
    args = ap.parse_args()

    setup_logging("ERROR")
    root = Path(__file__).resolve().parents[1]
    config = copy.deepcopy(load_config(root / "config" / "config.yaml"))
    config["agents"].setdefault("machine_learning", {})["enabled"] = False  # velocidad

    raw = load_ohlcv_csv(args.csv)
    df = raw if args.base <= 1 else resample_ohlcv(raw, args.base)
    n = len(df)
    sl_grid = [1.0, 1.5, 2.0]

    # Folds deslizantes.
    folds = []
    start = 0
    while start + args.train_bars + args.test_bars <= n:
        folds.append((start, start + args.train_bars,
                      start + args.train_bars + args.test_bars))
        start += args.test_bars
    print(f"Datos: {n} velas M{args.base} | {len(folds)} folds "
          f"(train={args.train_bars}, test={args.test_bars}, ML=no)\n")

    ref_pnls: list = []          # PnL OOS de la política fija, en orden cronológico
    header = f"{'fold':>4} {'test desde':>12} {'SL* train':>9} {'PF opt':>7} {'PF ref':>7} {'trades ref':>10}"
    print(header)
    print("-" * len(header))

    for k, (a, b, c) in enumerate(folds, 1):
        train, test = df.iloc[a:b], df.iloc[b:c]
        # Búsqueda de SL en train (TP fijo en REF_TP).
        best_sl, best_pf = None, -1.0
        for sl in sl_grid:
            m = _run(train, config, args.base, args.step, args.warmup, args.max_window,
                     sl, REF_TP).metrics
            pf = m["profit_factor"] if m["trades"] >= 20 else 0.0
            pf = 5.0 if pf == float("inf") else pf
            if pf > best_pf:
                best_pf, best_sl = pf, sl
        # OOS: mejor de train y política fija de referencia.
        opt = _run(test, config, args.base, args.step, args.warmup, args.max_window,
                   best_sl, REF_TP)
        ref = opt if best_sl == REF_SL else _run(
            test, config, args.base, args.step, args.warmup, args.max_window, REF_SL, REF_TP)
        ref_pnls.extend(t.pnl for t in ref.trades if t.pnl is not None)
        print(f"{k:>4} {str(test.index[0].date()):>12} {best_sl:>9} "
              f"{opt.metrics['profit_factor']:>7} {ref.metrics['profit_factor']:>7} "
              f"{ref.metrics['trades']:>10}")

    # Agregado OOS de la política fija (SL=1.0/TP=2.5) sobre todos los tests.
    equity = [10000.0]
    for p in ref_pnls:
        equity.append(equity[-1] + p)
    agg = compute_metrics(ref_pnls, equity)
    print("\n=== AGREGADO OUT-OF-SAMPLE (política fija SL=1.0/TP=2.5, todos los tests) ===")
    for key in ("trades", "wins", "losses", "winrate", "profit_factor",
                "expectancy", "net_pnl", "max_drawdown"):
        print(f"  {key:15s}: {agg[key]}")
    print("\nLectura: si el PF agregado > 1.1 y la mayoría de folds eligen SL=1.0,")
    print("la política es robusta a través de regímenes (no un split afortunado).")


if __name__ == "__main__":
    main()
