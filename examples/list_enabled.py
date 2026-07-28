"""Imprime los instrumentos con enabled:true (uno por línea). Lo usa start_all.ps1."""
from pathlib import Path
from trading_system.runtime import enabled_instruments
from trading_system.utils import load_config

cfg = load_config(Path(__file__).resolve().parents[1] / "config" / "config.yaml")
for name in enabled_instruments(cfg):
    print(name)
