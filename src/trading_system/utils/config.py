"""Carga de configuración desde YAML."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from ..core.exceptions import ConfigError


def load_config(path: str | Path) -> Dict[str, Any]:
    """Carga y valida mínimamente el fichero de configuración YAML."""
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"No existe el fichero de configuración: {p}")
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError("La configuración debe ser un mapeo YAML")
    if "agents" not in data:
        raise ConfigError("La configuración debe declarar la sección 'agents'")
    return data
