"""Persistencia de decisiones, operaciones y desempeño (Repository)."""
from __future__ import annotations

from .repository import (
    MySQLRepository,
    PersistenceError,
    Repository,
    SqliteRepository,
    SqlRepository,
)

__all__ = [
    "Repository",
    "SqlRepository",
    "SqliteRepository",
    "MySQLRepository",
    "PersistenceError",
]
