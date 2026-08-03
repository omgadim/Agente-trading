"""Tests de los proveedores de contexto externo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from trading_system.context import (
    CsvNewsProvider,
    EconomicEvent,
    InMemoryCorrelationProvider,
    InMemoryNewsProvider,
    InMemorySentimentProvider,
)


def test_event_normalizes_tz_and_impact():
    ev = EconomicEvent(time=datetime(2024, 1, 1, 12, 0), currency="usd", impact="HIGH", title="x")
    assert ev.time.tzinfo is not None
    assert ev.impact == "high" and ev.currency == "USD"
    assert ev.is_high is True


def test_news_events_between_filters_and_tz():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    evs = [
        EconomicEvent(now - timedelta(hours=2), "USD", "high", "old"),
        EconomicEvent(now + timedelta(minutes=10), "USD", "high", "soon"),
        EconomicEvent(now + timedelta(hours=5), "USD", "high", "later"),
    ]
    prov = InMemoryNewsProvider(evs)
    # Ventana [now, now+30min]; entrada naive se normaliza a UTC.
    got = prov.events_between(datetime(2024, 1, 1, 12, 0), now + timedelta(minutes=30))
    assert [e.title for e in got] == ["soon"]


def test_csv_news_provider(tmp_path):
    csv = tmp_path / "cal.csv"
    csv.write_text(
        "time,currency,impact,title\n"
        "2024-01-01T12:30:00,USD,high,NFP\n"
        "2024-01-01T14:00:00,EUR,low,Speech\n"
    )
    prov = CsvNewsProvider(csv)
    got = prov.events_between(
        datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 0, 0, tzinfo=timezone.utc),
    )
    assert len(got) == 2
    assert got[0].title == "NFP" and got[0].is_high


def test_correlation_provider_returns_lookback():
    s = pd.Series(range(100), dtype=float)
    prov = InMemoryCorrelationProvider({"DXY": s})
    assert prov.symbols() == ["DXY"]
    assert len(prov.closes("DXY", 20)) == 20
    assert prov.closes("SPX", 20) is None


def test_sentiment_provider_default_and_symbol():
    prov = InMemorySentimentProvider({"XAUUSD": 75.0}, default=50.0)
    assert prov.net_long("XAUUSD") == 75.0
    assert prov.net_long("EURUSD") == 50.0
