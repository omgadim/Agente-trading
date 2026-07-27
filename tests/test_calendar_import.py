"""Tests del conversor de calendario económico (investing.com -> CSV)."""
from __future__ import annotations

from trading_system.context.calendar_import import parse_investing_calendar, write_calendar_csv

RAW = """viernes, 7 de agosto de 2026
07:30
US
Nóminas no agrícolas  (Jul)
57K
07:30
US
Tasa de desempleo  (Jul)
4,2%
07:30
CA
Tasa de desempleo  (Jul)
6,5%
09:00
US
PMI manufacturero  (Jul)
53,8
"""


def test_parse_filters_and_converts_to_utc():
    events = parse_investing_calendar(RAW, utc_offset=-5.0, currency_code="US")
    titles = [e["title"] for e in events]
    # NFP y desempleo (USD, alto impacto) presentes; convertidos 07:30 -5 -> 12:30 UTC.
    nfp = [e for e in events if "Nóminas" in e["title"]][0]
    assert nfp["time"] == "2026-08-07 12:30:00"
    assert nfp["currency"] == "USD" and nfp["impact"] == "high"
    assert any("Tasa de desempleo" in t for t in titles)
    # Canadá se descarta (no es USD).
    assert all(e["currency"] == "USD" for e in events)
    # El PMI de S&P (no ISM) no es de alto impacto -> se omite.
    assert not any("PMI manufacturero (Jul)" == t for t in titles)


def test_utc_offset_zero_keeps_time():
    events = parse_investing_calendar(RAW, utc_offset=0.0, currency_code="US")
    nfp = [e for e in events if "Nóminas" in e["title"]][0]
    assert nfp["time"] == "2026-08-07 07:30:00"


def test_write_csv_roundtrip(tmp_path):
    events = parse_investing_calendar(RAW)
    out = tmp_path / "cal.csv"
    write_calendar_csv(events, out)
    content = out.read_text(encoding="utf-8")
    assert content.startswith("time,currency,impact,title")
    assert "Non" not in content  # títulos en español, tal cual la página
    assert "USD,high,Nóminas no agrícolas (Jul)" in content
