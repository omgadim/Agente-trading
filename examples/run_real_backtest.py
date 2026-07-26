"""Backtest del sistema multiagente sobre datos históricos REALES (CSV MT5).

Carga un CSV OHLCV (p. ej. XAUUSD M1 exportado de MetaTrader 5), lo remuestrea al
timeframe base de trabajo y ejecuta el backtester walk-forward con el roster
completo de agentes (aprendizaje activado). A diferencia de los demos con datos
simulados, aquí las métricas reflejan el comportamiento sobre mercado real.

Uso:
    PYTHONPATH=src python -m examples.run_real_backtest <ruta_csv> [--base 5] [--step 4]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from trading_system.backtest import Backtester
from trading_system.data import load_ohlcv_csv, resample_ohlcv
from trading_system.engine import build_agents, build_weighting
from trading_system.persistence import SqliteRepository
from trading_system.supervisor import Supervisor
from trading_system.utils import load_config, setup_logging

import trading_system.agents  # noqa: F401


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest sobre datos reales (CSV)")
    parser.add_argument("csv", help="Ruta al CSV OHLCV (formato MT5 u OHLCV estándar)")
    parser.add_argument("--base", type=int, default=5, help="Timeframe base en minutos")
    parser.add_argument("--step", type=int, default=4, help="Salto de barras entre decisiones")
    parser.add_argument("--warmup", type=int, default=500, help="Barras de calentamiento")
    parser.add_argument("--max-window", type=int, default=6000,
                        help="Ventana máxima de histórico por paso (0 = todo)")
    args = parser.parse_args()

    setup_logging("WARNING")
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config" / "config.yaml")

    # Carga M1 y remuestrea al timeframe base (para eficiencia y multi-TF).
    raw = load_ohlcv_csv(args.csv)
    base_df = raw if args.base <= 1 else resample_ohlcv(raw, args.base)
    print(f"Datos: {len(raw)} velas M1 -> {len(base_df)} velas base (M{args.base})")
    print(f"Rango: {base_df.index[0]}  ->  {base_df.index[-1]}")
    print(f"Precio: {base_df['low'].min():.2f} - {base_df['high'].max():.2f}\n")

    repo = SqliteRepository(":memory:")
    repo.initialize()
    supervisor = Supervisor(agents=build_agents(config), weighting=build_weighting(config))
    backtester = Backtester(
        supervisor, base_minutes=args.base, warmup=args.warmup, step=args.step,
        learn=True, repository=repo, max_window=args.max_window or None,
    )
    result = backtester.run(base_df)

    print("=== RESULTADO SOBRE DATOS REALES ===")
    print(result.summary())
    print("\nDetalle:")
    for k, v in result.metrics.items():
        print(f"  {k:15s}: {v}")

    # Comparación honesta: ¿bate a comprar-y-mantener en el periodo?
    ret_bh = (base_df["close"].iloc[-1] / base_df["close"].iloc[0] - 1) * 100
    print(f"\nBuy & hold del subyacente en el periodo: {ret_bh:+.2f}%")

    print("\nTop agentes por hit-rate (con >= 3 señales):")
    perf = [p for p in repo.agent_performance() if (p["hits"] + p["misses"]) >= 3]
    for p in perf[:10]:
        total = p["hits"] + p["misses"]
        print(f"  {p['agent_name']:18s} {p['regime']:14s} "
              f"{p['hits']}/{total}  hit-rate={float(p['hit_rate']):.2f}")


if __name__ == "__main__":
    main()
