"""Runner de producción: opera en vivo (o paper) desde la configuración.

Ensambla el sistema completo (feed + broker MT5, supervisor, riesgo, guardián,
kill switch, alertas, persistencia) y ejecuta el bucle de operación.

- Modo paper (por defecto): cliente MT5 simulado; corre en cualquier SO.
- Modo live: RealMT5Client (Windows + terminal MT5). Credenciales por variables
  de entorno MT5_LOGIN/MT5_PASSWORD/MT5_SERVER.

Uso:
    # Paper, unos pasos, sin depender del calendario (para probar el cableado):
    PYTHONPATH=src python -m examples.run_live --mode paper --max-steps 200 --relax-guard

    # Live en cuenta demo (en Windows), un ciclo cada 60 s:
    PYTHONPATH=src python -m examples.run_live --mode live --interval 60
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from trading_system.runtime import build_live_trader
from trading_system.utils import load_config, setup_logging

logger = logging.getLogger("run_live")


def main() -> None:
    ap = argparse.ArgumentParser(description="Runner en vivo / paper")
    ap.add_argument("--mode", choices=["paper", "live"], default="paper")
    ap.add_argument("--interval", type=float, default=60.0, help="Segundos entre ciclos (live)")
    ap.add_argument("--max-steps", type=int, default=0, help="0 = sin límite")
    ap.add_argument("--advance", type=int, default=6, help="Barras a avanzar por ciclo (paper)")
    ap.add_argument("--relax-guard", action="store_true",
                    help="Paper: ignora calendario/horario del guardián (para pruebas)")
    ap.add_argument("--instrument", default=None,
                    help="Perfil de instrumento (config.instruments); ej. NAS100. "
                         "Sin esto usa el símbolo base del config (Oro).")
    args = ap.parse_args()

    setup_logging("INFO")
    config = load_config(Path(__file__).resolve().parents[1] / "config" / "config.yaml")
    if args.instrument:
        from trading_system.runtime import apply_instrument
        config = apply_instrument(config, args.instrument)
        logger.info("Instrumento: %s", args.instrument)
    if args.relax_guard:
        g = config.setdefault("guards", {})
        g["allow_weekend"] = True
        g["trading_hours"] = []

    trader, client = build_live_trader(config, mode=args.mode)
    client.connect()
    logger.info("Conectado (%s). Símbolo=%s. Kill switch=%s. Persistencia=%s. Alertas=%s",
                args.mode, trader.symbol, trader.kill_switch is not None,
                trader.repository is not None, trader.notifier is not None)
    if trader.notifier is not None:
        trader.notifier.notify(
            f"Símbolo:  *{trader.symbol}*\nModo:  `{args.mode}`\n"
            f"Máx. posiciones:  `{trader.max_positions}`\nIntervalo:  `{args.interval:.0f}s`",
            "🚀 Bot iniciado", "info")

    steps = 0
    try:
        while True:
            result = trader.step()
            steps += 1
            _log_step(steps, result, client)

            if result.halted:
                logger.error("Kill switch activo — se detiene la apertura de nuevas operaciones.")
            if args.max_steps and steps >= args.max_steps:
                break

            if args.mode == "paper":
                if not client.has_next():
                    logger.info("Serie paper agotada.")
                    break
                client.advance(args.advance)
            else:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("Interrupción manual — cerrando de forma limpia.")
    finally:
        _shutdown(trader, client, steps)


def _log_step(n, result, client) -> None:
    parts = [f"#{n}"]
    if result.opened:
        parts.append(f"ABRE {result.opened.direction.value} @ {result.opened.price:.2f}")
    if result.closed:
        parts.append(f"cierra={len(result.closed)}")
    if result.management:
        parts.append(f"gestión={len(result.management)}")
    if result.decision and not result.opened:
        parts.append(f"señal={result.decision.signal.value}")
    if result.skipped_reason:
        parts.append(f"({result.skipped_reason})")
    try:
        acct = client.account()
        parts.append(f"eq={acct.equity:.2f}")
    except Exception:
        pass
    logger.info(" | ".join(parts))


def _shutdown(trader, client, steps) -> None:
    try:
        client.shutdown()
    except Exception:
        pass
    if trader.repository is not None:
        try:
            trader.repository.close()
        except Exception:
            pass
    logger.info("Detenido tras %d ciclos.", steps)


if __name__ == "__main__":
    main()
