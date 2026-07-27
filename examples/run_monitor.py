"""Monitor sin Docker: genera un dashboard HTML desde la persistencia (SQLite/MySQL).

Pensado para VPS SIN Docker/MySQL: lee `data/trading.db` (u otro backend de
`config.yaml`) y escribe un `dashboard.html` autocontenido que abres en el
navegador. Se regenera cada `--interval` segundos y la página se auto-refresca.

Uso:
    # Genera dashboard.html y lo abre en el navegador; se actualiza cada 30 s:
    python -m examples.run_monitor --open

    # Una sola vez (p. ej. para un vistazo puntual):
    python -m examples.run_monitor --once

    # Ruta de salida personalizada:
    python -m examples.run_monitor --output C:\\Agente-trading\\dashboard.html
"""
from __future__ import annotations

import argparse
import logging
import time
import webbrowser
from pathlib import Path

from trading_system.monitor import collect_dashboard_data, render_dashboard_html
from trading_system.persistence import SqliteRepository
from trading_system.runtime import build_repository
from trading_system.utils import load_config, setup_logging

logger = logging.getLogger("run_monitor")


def _open_repository(config):
    """Devuelve un repositorio de lectura desde config (o SQLite por defecto)."""
    repo = build_repository(config)
    if repo is not None:
        return repo
    # Persistencia desactivada en config: abrimos el SQLite por defecto igualmente.
    path = (config.get("persistence", {}) or {}).get("sqlite_path", "data/trading.db")
    repo = SqliteRepository(path)
    repo.initialize()
    return repo


def _db_label(config) -> str:
    cfg = config.get("persistence", {}) or {}
    if cfg.get("backend") == "mysql":
        return "MySQL"
    return str(cfg.get("sqlite_path", "data/trading.db"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Monitor HTML del sistema (sin Docker)")
    ap.add_argument("--config", default=None, help="Ruta a config.yaml")
    ap.add_argument("--output", default="dashboard.html", help="Archivo HTML de salida")
    ap.add_argument("--interval", type=float, default=30.0, help="Segundos entre refrescos")
    ap.add_argument("--once", action="store_true", help="Genera una sola vez y termina")
    ap.add_argument("--open", action="store_true", help="Abre el HTML en el navegador al arrancar")
    args = ap.parse_args()

    setup_logging("INFO")
    config_path = args.config or (Path(__file__).resolve().parents[1] / "config" / "config.yaml")
    config = load_config(config_path)
    repo = _open_repository(config)
    output = Path(args.output).resolve()
    label = _db_label(config)

    refresh = max(1, int(args.interval))
    opened = False
    try:
        while True:
            data = collect_dashboard_data(repo)
            html = render_dashboard_html(data, refresh=refresh, db_label=label)
            output.write_text(html, encoding="utf-8")
            kpi = data["kpi"]
            logger.info("Dashboard actualizado: %s | ops=%s winrate=%.1f%% pnl=%.2f",
                        output, kpi.get("trades", 0), kpi.get("winrate", 0.0),
                        kpi.get("net_pnl", 0.0))
            if args.open and not opened:
                webbrowser.open(output.as_uri())
                opened = True
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("Monitor detenido.")
    finally:
        try:
            repo.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
