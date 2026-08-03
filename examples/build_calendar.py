"""Conversor de calendario económico: pega el texto de investing.com -> CSV del sistema.

Uso semanal (3 pasos):
  1) En investing.com abres el calendario, copias TODO y lo pegas en un archivo
     de texto (por defecto `config/calendar_raw.txt`).
  2) Ejecutas:  python -m examples.build_calendar
  3) Genera `config/calendar_econ.csv` con las noticias USD de alto impacto,
     convertidas a UTC. El NewsAgent ya lo lee.

La hora del export se asume de Colombia (UTC-5). Cámbiala con --utc-offset si tu
investing.com muestra otra zona (p. ej. -6 México, +1/+2 España, 0 UTC).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from trading_system.context.calendar_import import parse_investing_calendar, write_calendar_csv


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description="Convierte el calendario de investing.com a CSV")
    ap.add_argument("input", nargs="?", default=str(root / "config" / "calendar_raw.txt"),
                    help="Archivo de texto con el calendario pegado")
    ap.add_argument("-o", "--output", default=str(root / "config" / "calendar_econ.csv"))
    ap.add_argument("--utc-offset", type=float, default=-5.0,
                    help="Huso del export (Colombia=-5, México=-6, España=+1/+2, UTC=0)")
    ap.add_argument("--currency", default="US", help="Código de divisa en la página (US)")
    args = ap.parse_args()

    text = Path(args.input).read_text(encoding="utf-8")
    events = parse_investing_calendar(text, args.utc_offset, args.currency)
    write_calendar_csv(events, args.output)
    print(f"{len(events)} noticias USD de alto impacto -> {args.output}")
    for e in events:
        print(f"  {e['time']} UTC  {e['title']}")
    if not events:
        print("(No se detectó ninguna. ¿Pegaste el texto y es la divisa correcta?)")


if __name__ == "__main__":
    main()
