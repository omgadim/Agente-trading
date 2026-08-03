"""Tests del cargador de CSV OHLCV."""
from __future__ import annotations

import pytest

from trading_system.core.exceptions import DataError
from trading_system.data import load_ohlcv_csv


def test_loads_mt5_format_with_tick_volume(tmp_path):
    # Formato MT5: Volume=0, se debe usar Tick_Volume.
    csv = tmp_path / "xau.csv"
    csv.write_text(
        "Date,Open,High,Low,Close,Volume,Spread,Tick_Volume\n"
        "2025-10-03 20:30:00,3883.79,3885.3,3883.24,3883.24,0,7,233\n"
        "2025-10-03 20:31:00,3883.24,3883.74,3881.9,3882.52,0,7,305\n"
    )
    df = load_ohlcv_csv(csv)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    # Volume era 0 -> se usa Tick_Volume.
    assert df["volume"].iloc[0] == 233.0
    assert str(df.index.dtype).startswith("datetime64")


def test_loads_standard_ohlcv(tmp_path):
    csv = tmp_path / "std.csv"
    csv.write_text(
        "time,open,high,low,close,volume\n"
        "2024-01-01 00:00:00,100,101,99,100.5,1500\n"
        "2024-01-01 00:05:00,100.5,102,100,101.5,1800\n"
    )
    df = load_ohlcv_csv(csv)
    assert df["volume"].iloc[1] == 1800.0
    assert df["close"].iloc[0] == 100.5


def test_sorts_and_deduplicates(tmp_path):
    csv = tmp_path / "unsorted.csv"
    csv.write_text(
        "time,open,high,low,close,volume\n"
        "2024-01-01 00:05:00,2,2,2,2,10\n"
        "2024-01-01 00:00:00,1,1,1,1,10\n"
        "2024-01-01 00:05:00,3,3,3,3,10\n"  # duplicado -> se queda el último
    )
    df = load_ohlcv_csv(csv)
    assert len(df) == 2
    assert df["close"].iloc[0] == 1.0   # ordenado
    assert df["close"].iloc[1] == 3.0   # último del duplicado


def test_missing_columns_raise(tmp_path):
    csv = tmp_path / "bad.csv"
    csv.write_text("time,open,close\n2024-01-01,100,101\n")
    with pytest.raises(DataError):
        load_ohlcv_csv(csv)


def test_missing_file_raises():
    with pytest.raises(DataError):
        load_ohlcv_csv("/no/existe/x.csv")
