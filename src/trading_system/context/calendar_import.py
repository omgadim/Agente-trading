"""Importa un calendario económico pegado desde investing.com a eventos del sistema.

Los "toritos" de importancia no se copian como texto, así que el impacto se
decide por el NOMBRE del evento (NFP, IPC, Fed, ISM, ADP, PIB...) — fiable para
las noticias USD que mueven el Oro. Las horas del export se convierten a UTC
según el huso indicado (Colombia = -5).
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Eventos que mueven el Oro (subcadenas en minúscula; el texto suele ser español).
HIGH_KEYWORDS = [
    "nóminas no agrícolas", "nominas no agricolas", "non-farm", "nfp",
    "nóminas privadas", "nominas privadas",
    "tasa de desempleo", "unemployment",
    "ingresos medios por hora", "average hourly",
    "ipc", "cpi", "ipp", "ppi", "pce",
    "decisión de tipos", "decision de tipos", "tipos de interés", "tipos de interes",
    "fomc", "reserva federal", "powell",
    "ism", "adp", "pib", "gdp",
    "ventas minoristas", "retail sales",
    "jolts", "ofertas de empleo",
    "confianza del consumidor de michigan", "michigan",
]

_DATE_RE = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", re.IGNORECASE)
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _impact(title: str) -> str | None:
    t = title.lower()
    return "high" if any(kw in t for kw in HIGH_KEYWORDS) else None


def parse_investing_calendar(
    text: str, utc_offset: float = -5.0, currency_code: str = "US"
) -> List[Dict[str, str]]:
    """Extrae eventos de alto impacto de `currency_code`, con `time` en UTC.

    `utc_offset` es el huso del export (Colombia=-5, México=-6, España=+1/+2, UTC=0),
    tal que hora_local = UTC + utc_offset.
    """
    lines = [ln.strip() for ln in text.splitlines()]
    cur_date = None
    out: List[Dict[str, str]] = []
    i = 0
    while i < len(lines):
        m = _DATE_RE.search(lines[i])
        if m and m.group(2).lower() in MONTHS:
            cur_date = (int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
            i += 1
            continue
        tm = _TIME_RE.match(lines[i])
        if tm and cur_date is not None and i + 2 < len(lines):
            code, title = lines[i + 1], lines[i + 2]
            if code.upper() == currency_code.upper() and _impact(title):
                hh, mm = int(tm.group(1)), int(tm.group(2))
                local = datetime(cur_date[0], cur_date[1], cur_date[2], hh, mm)
                utc = local - timedelta(hours=utc_offset)  # local = UTC + offset
                out.append({
                    "time": utc.strftime("%Y-%m-%d %H:%M:%S"),
                    "currency": "USD",
                    "impact": "high",
                    "title": re.sub(r"\s+", " ", title).strip(),
                })
            i += 3
            continue
        i += 1

    seen = set()
    unique: List[Dict[str, str]] = []
    for e in out:
        key = (e["time"], e["title"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    unique.sort(key=lambda e: e["time"])
    return unique


def write_calendar_csv(events: List[Dict[str, str]], path: str | Path) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["time", "currency", "impact", "title"])
        w.writeheader()
        w.writerows(events)
