"""Demo: entrenamiento y validación walk-forward del agente de ML.

Compara la logística (numpy) con los modelos opcionales (GradientBoosting/XGBoost)
si están instalados, mediante validación walk-forward sin look-ahead.

Uso:
    PYTHONPATH=src python -m examples.run_ml_train
"""
from __future__ import annotations

from trading_system.core import AgentRegistry
from trading_system.data import SimulatedDataFeed
from trading_system.ml import ModelError, walk_forward_eval
from trading_system.utils import setup_logging

import trading_system.agents  # noqa: F401  (registro)


def main() -> None:
    setup_logging("WARNING")

    base = SimulatedDataFeed(base_price=2000.0, drift=0.06, volatility=1.0,
                             bars=2500, seed=2025).generate()

    print("=== Validación walk-forward (5 folds, horizonte=5 barras) ===")
    for model_name in ("logistic", "gboosting", "xgboost"):
        try:
            r = walk_forward_eval(base, model_name=model_name, horizon=5, folds=5)
            print(f"  {model_name:10s} accuracy={r['accuracy']:.3f} "
                  f"(baseline={r['baseline']:.3f}, n_test={r['n_test']})")
        except (ModelError, ImportError) as exc:
            print(f"  {model_name:10s} omitido: {exc}")

    print("\nNOTA: los datos son un *random walk* con deriva; sin edge real, la")
    print("accuracy queda cerca del baseline. Sobre datos de mercado reales con")
    print("microestructura los modelos pueden separar mejor. El objetivo aquí es")
    print("validar el pipeline (features sin look-ahead, entrenamiento, inferencia).")

    md = SimulatedDataFeed(base_price=2000, drift=0.2, volatility=0.8,
                           bars=900, seed=11).get_market_data("XAUUSD")
    decision = AgentRegistry.create("machine_learning", {"model": "logistic"}).run(md)
    print(f"\nDecisión del agente ML: {decision.signal.value} "
          f"(conf={decision.confidence:.1f}) -> {decision.explanation}")


if __name__ == "__main__":
    main()
