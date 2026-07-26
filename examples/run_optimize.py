"""Optimización walk-forward honesta (train/test) de la política de salida.

Divide la serie en train (in-sample) y test (out-of-sample) cronológicos, busca
en train los mejores multiplicadores de SL/TP (por ATR) y evalúa esos parámetros
—y los por defecto— en test. Así se mide si la mejora es real o *overfitting*.

Para mantener el coste acotado, por defecto desactiva el agente de ML (el más
lento); la optimización se centra en la política de salida, común a todos.

Uso:
    PYTHONPATH=src python -m examples.run_optimize data/XAUUSD_M15.csv --base 15
"""
from __future__ import annotations

import argparse
import copy
from itertools import product
from pathlib import Path

from trading_system.backtest import Backtester
from trading_system.data import load_ohlcv_csv, resample_ohlcv
from trading_system.engine import build_agents, build_weighting
from trading_system.supervisor import Supervisor
from trading_system.utils import load_config, setup_logging

import trading_system.agents  # noqa: F401


def _run(base_df, config, base, step, warmup, max_window, sl, tp):
    supervisor = Supervisor(agents=build_agents(config), weighting=build_weighting(config))
    bt = Backtester(supervisor, base_minutes=base, warmup=warmup, step=step,
                    learn=True, max_window=max_window, sl_atr_mult=sl, tp_atr_mult=tp)
    return bt.run(base_df)


def _objective(m, min_trades=30):
    """Objetivo robusto: profit factor si hay operaciones suficientes."""
    if m["trades"] < min_trades:
        return 0.0
    pf = m["profit_factor"]
    return pf if pf != float("inf") else 5.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimización walk-forward SL/TP")
    parser.add_argument("csv")
    parser.add_argument("--base", type=int, default=15)
    parser.add_argument("--step", type=int, default=14)
    parser.add_argument("--warmup", type=int, default=500)
    parser.add_argument("--max-window", type=int, default=5000)
    parser.add_argument("--split", type=float, default=0.65, help="Fracción de train")
    parser.add_argument("--with-ml", action="store_true", help="Incluir el agente ML (lento)")
    args = parser.parse_args()

    setup_logging("ERROR")
    root = Path(__file__).resolve().parents[1]
    config = copy.deepcopy(load_config(root / "config" / "config.yaml"))
    if not args.with_ml:
        config["agents"].setdefault("machine_learning", {})["enabled"] = False

    raw = load_ohlcv_csv(args.csv)
    base_df = raw if args.base <= 1 else resample_ohlcv(raw, args.base)
    split = int(len(base_df) * args.split)
    train, test = base_df.iloc[:split], base_df.iloc[split:]
    print(f"Datos: {len(base_df)} velas M{args.base} | train={len(train)} test={len(test)}")
    print(f"Train: {train.index[0]} -> {train.index[-1]}")
    print(f"Test:  {test.index[0]} -> {test.index[-1]}  (ML={'sí' if args.with_ml else 'no'})\n")

    sl_grid = [1.0, 1.5, 2.0]
    tp_grid = [2.0, 2.5, 3.0]

    print("=== Búsqueda en TRAIN (objetivo: profit factor) ===")
    best = None
    for sl, tp in product(sl_grid, tp_grid):
        m = _run(train, config, args.base, args.step, args.warmup, args.max_window, sl, tp).metrics
        obj = _objective(m)
        flag = ""
        if best is None or obj > best[0]:
            best = (obj, sl, tp)
            flag = "  <- mejor"
        print(f"  SL={sl} TP={tp}: PF={m['profit_factor']} trades={m['trades']} "
              f"netPnL={m['net_pnl']}{flag}")

    _, bsl, btp = best
    print(f"\nMejor en train: SL={bsl} TP={btp}\n")

    print("=== Evaluación OUT-OF-SAMPLE (TEST) ===")
    opt = _run(test, config, args.base, args.step, args.warmup, args.max_window, bsl, btp)
    base = _run(test, config, args.base, args.step, args.warmup, args.max_window, 1.5, 2.5)
    print(f"  Optimizado (SL={bsl} TP={btp}): {opt.summary()}")
    print(f"  Baseline   (SL=1.5 TP=2.5):    {base.summary()}")
    bh = (test['close'].iloc[-1] / test['close'].iloc[0] - 1) * 100
    print(f"  Buy & hold en test: {bh:+.2f}%")

    print("\nNOTA: si el optimizado NO supera claramente al baseline en test, la")
    print("mejora en train era overfitting. La honestidad está en el test, no en train.")


if __name__ == "__main__":
    main()
