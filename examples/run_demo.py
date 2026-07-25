"""Demo: ejecuta un ciclo de decisión con datos simulados.

Uso:
    PYTHONPATH=src python -m examples.run_demo
"""
from __future__ import annotations

from pathlib import Path

from trading_system import TradingEngine
from trading_system.utils import load_config, setup_logging


def main() -> None:
    setup_logging("INFO")
    config_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    config = load_config(config_path)

    engine = TradingEngine(config)
    decision = engine.run_once(execute=True)

    print("\n=== DECISIÓN DEL SUPERVISOR ===")
    print(f"Señal:      {decision.signal.value}")
    print(f"Confianza:  {decision.confidence:.1f}/100")
    print(f"Score:      {decision.score:+.3f}")
    print(f"Riesgo:     {decision.estimated_risk:.1f}/100")
    print(f"SL/TP:      {decision.stop_loss} / {decision.take_profit}")
    print(f"Tamaño:     {decision.position_size}")
    print(f"Motivo:     {decision.explanation}")
    print("\n--- Aportes de los agentes ---")
    for d in sorted(decision.contributing, key=lambda x: -x.confidence):
        w = decision.weights.get(d.agent_name, 1.0)
        print(f"  {d.agent_name:20s} {d.signal.value:4s} conf={d.confidence:5.1f} "
              f"peso={w:.2f}  {d.explanation[:60]}")


if __name__ == "__main__":
    main()
