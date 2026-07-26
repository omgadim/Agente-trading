"""Capa de persistencia (patrón Repository).

Una única interfaz `Repository` con dos backends sobre el mismo SQL:
- `SqliteRepository`: usa la librería estándar `sqlite3`; corre y se testea en
  cualquier entorno (por defecto en local/CI).
- `MySQLRepository`: usa PyMySQL (import perezoso); escribe en las **mismas
  tablas** que lee el dashboard PHP (`integrations/dashboard`).

Las tablas replican `integrations/dashboard/sql/schema.sql` para que el panel PHP
consuma exactamente lo que escribe el motor Python.
"""
from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.decision import SupervisorDecision
from ..core.exceptions import TradingSystemError


class PersistenceError(TradingSystemError):
    """Error de acceso a la base de datos."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Repository(ABC):
    """Contrato de persistencia de decisiones, operaciones y desempeño."""

    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def save_decision(self, decision: SupervisorDecision, symbol: str, regime: str = "") -> int: ...

    @abstractmethod
    def open_trade(self, symbol: str, direction: str, volume: float, entry_price: float,
                   stop_loss: Optional[float], take_profit: Optional[float],
                   decision_id: Optional[int] = None, ticket: Optional[int] = None) -> int: ...

    @abstractmethod
    def close_trade(self, trade_id: int, exit_price: float, pnl: float) -> None: ...

    @abstractmethod
    def update_agent_performance(self, agent_name: str, regime: str, correct: bool) -> None: ...

    @abstractmethod
    def save_weight_state(self, name: str, state: Dict[str, Any]) -> None: ...

    @abstractmethod
    def load_weight_state(self, name: str) -> Dict[str, Any]: ...

    @abstractmethod
    def recent_decisions(self, limit: int = 20) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def recent_trades(self, limit: int = 20) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def agent_performance(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def pnl_summary(self) -> Dict[str, Any]: ...

    def close(self) -> None:  # pragma: no cover - trivial
        pass


class SqlRepository(Repository):
    """Implementación SQL compartida; las subclases aportan conexión y dialecto."""

    # Placeholder de parámetros ('?' en sqlite, '%s' en MySQL).
    placeholder: str = "?"
    autoincrement: str = "INTEGER PRIMARY KEY AUTOINCREMENT"

    def __init__(self) -> None:
        self._conn = None

    # ---- a implementar por el backend ----
    def _connect(self):  # pragma: no cover - override
        raise NotImplementedError

    # ---- conexión ----
    def _cursor(self):
        if self._conn is None:
            self._conn = self._connect()
        return self._conn.cursor()

    def _q(self, sql: str) -> str:
        """Traduce el placeholder '?' del SQL al del backend."""
        if self.placeholder == "?":
            return sql
        return sql.replace("?", self.placeholder)

    def initialize(self) -> None:
        cur = self._cursor()
        for ddl in self._ddl():
            cur.execute(ddl)
        self._conn.commit()

    def _ddl(self) -> List[str]:
        ai = self.autoincrement
        return [
            f"""CREATE TABLE IF NOT EXISTS supervisor_decisions (
                id {ai},
                symbol VARCHAR(20) NOT NULL,
                signal_type VARCHAR(4) NOT NULL,
                confidence DECIMAL(5,2), score DECIMAL(6,4),
                estimated_risk DECIMAL(5,2),
                stop_loss DECIMAL(12,4), take_profit DECIMAL(12,4),
                position_size DECIMAL(10,2),
                conflict INTEGER DEFAULT 0, vetoed INTEGER DEFAULT 0,
                veto_reason VARCHAR(255), explanation TEXT, regime VARCHAR(40),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            f"""CREATE TABLE IF NOT EXISTS agent_decisions (
                id {ai},
                decision_id INTEGER NOT NULL,
                agent_name VARCHAR(50) NOT NULL,
                signal_type VARCHAR(4) NOT NULL,
                confidence DECIMAL(5,2), weight DECIMAL(6,4) DEFAULT 1,
                estimated_risk DECIMAL(5,2), explanation VARCHAR(500),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            f"""CREATE TABLE IF NOT EXISTS trades (
                id {ai},
                decision_id INTEGER,
                ticket BIGINT,
                symbol VARCHAR(20) NOT NULL,
                direction VARCHAR(4) NOT NULL,
                volume DECIMAL(10,2) NOT NULL,
                entry_price DECIMAL(12,4) NOT NULL,
                stop_loss DECIMAL(12,4), take_profit DECIMAL(12,4),
                exit_price DECIMAL(12,4), pnl DECIMAL(14,2),
                status VARCHAR(6) DEFAULT 'OPEN',
                opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                closed_at DATETIME
            )""",
            f"""CREATE TABLE IF NOT EXISTS agent_performance (
                id {ai},
                agent_name VARCHAR(50) NOT NULL,
                regime VARCHAR(40) NOT NULL,
                hits INTEGER DEFAULT 0, misses INTEGER DEFAULT 0,
                hit_rate DECIMAL(5,4) DEFAULT 0.5,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (agent_name, regime)
            )""",
            """CREATE TABLE IF NOT EXISTS weight_state (
                name VARCHAR(50) NOT NULL,
                state TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (name)
            )""",
        ]

    # ---- escritura ----
    def save_decision(self, decision: SupervisorDecision, symbol: str, regime: str = "") -> int:
        cur = self._cursor()
        cur.execute(self._q(
            """INSERT INTO supervisor_decisions
               (symbol, signal_type, confidence, score, estimated_risk, stop_loss,
                take_profit, position_size, conflict, vetoed, veto_reason, explanation, regime)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"""),
            (symbol, decision.signal.value, decision.confidence, decision.score,
             decision.estimated_risk, decision.stop_loss, decision.take_profit,
             decision.position_size, int(decision.conflict), int(decision.vetoed),
             decision.veto_reason, decision.explanation, regime))
        decision_id = cur.lastrowid
        for d in decision.contributing:
            cur.execute(self._q(
                """INSERT INTO agent_decisions
                   (decision_id, agent_name, signal_type, confidence, weight,
                    estimated_risk, explanation)
                   VALUES (?,?,?,?,?,?,?)"""),
                (decision_id, d.agent_name, d.signal.value, d.confidence,
                 decision.weights.get(d.agent_name, 1.0), d.estimated_risk,
                 d.explanation[:500]))
        self._conn.commit()
        return int(decision_id)

    def open_trade(self, symbol, direction, volume, entry_price, stop_loss, take_profit,
                   decision_id=None, ticket=None) -> int:
        cur = self._cursor()
        cur.execute(self._q(
            """INSERT INTO trades
               (decision_id, ticket, symbol, direction, volume, entry_price,
                stop_loss, take_profit, status)
               VALUES (?,?,?,?,?,?,?,?,'OPEN')"""),
            (decision_id, ticket, symbol, direction, volume, entry_price,
             stop_loss, take_profit))
        self._conn.commit()
        return int(cur.lastrowid)

    def close_trade(self, trade_id: int, exit_price: float, pnl: float) -> None:
        cur = self._cursor()
        cur.execute(self._q(
            """UPDATE trades SET exit_price=?, pnl=?, status='CLOSED', closed_at=?
               WHERE id=?"""),
            (exit_price, pnl, _now(), trade_id))
        self._conn.commit()

    def update_agent_performance(self, agent_name: str, regime: str, correct: bool) -> None:
        cur = self._cursor()
        cur.execute(self._q(
            "SELECT id, hits, misses FROM agent_performance WHERE agent_name=? AND regime=?"),
            (agent_name, regime))
        row = cur.fetchone()
        if row is None:
            hits = 1 if correct else 0
            misses = 0 if correct else 1
            rate = hits / (hits + misses) if (hits + misses) else 0.5
            cur.execute(self._q(
                """INSERT INTO agent_performance (agent_name, regime, hits, misses, hit_rate)
                   VALUES (?,?,?,?,?)"""),
                (agent_name, regime, hits, misses, rate))
        else:
            _id, hits, misses = row[0], row[1], row[2]
            hits += 1 if correct else 0
            misses += 0 if correct else 1
            rate = hits / (hits + misses) if (hits + misses) else 0.5
            cur.execute(self._q(
                "UPDATE agent_performance SET hits=?, misses=?, hit_rate=?, updated_at=? WHERE id=?"),
                (hits, misses, rate, _now(), _id))
        self._conn.commit()

    def save_weight_state(self, name: str, state: Dict[str, Any]) -> None:
        payload = json.dumps(state)
        cur = self._cursor()
        cur.execute(self._q("SELECT name FROM weight_state WHERE name=?"), (name,))
        row = cur.fetchone()
        if row is None:
            cur.execute(self._q(
                "INSERT INTO weight_state (name, state) VALUES (?,?)"), (name, payload))
        else:
            cur.execute(self._q(
                "UPDATE weight_state SET state=?, updated_at=? WHERE name=?"),
                (payload, _now(), name))
        self._conn.commit()

    def load_weight_state(self, name: str) -> Dict[str, Any]:
        cur = self._cursor()
        cur.execute(self._q("SELECT state FROM weight_state WHERE name=?"), (name,))
        row = cur.fetchone()
        if row is None or row[0] is None:
            return {}
        return json.loads(row[0])

    # ---- lectura ----
    def recent_decisions(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._select(
            "SELECT * FROM supervisor_decisions ORDER BY id DESC LIMIT ?", (limit,))

    def recent_trades(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._select(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))

    def agent_performance(self) -> List[Dict[str, Any]]:
        return self._select(
            "SELECT * FROM agent_performance ORDER BY hit_rate DESC", ())

    def pnl_summary(self) -> Dict[str, Any]:
        rows = self._select(
            """SELECT COUNT(*) AS trades,
                      SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
                      COALESCE(SUM(pnl), 0) AS net_pnl
               FROM trades WHERE status='CLOSED'""", ())
        r = rows[0] if rows else {"trades": 0, "wins": 0, "net_pnl": 0}
        trades = r.get("trades") or 0
        wins = r.get("wins") or 0
        winrate = round(wins / trades * 100.0, 2) if trades else 0.0
        return {"trades": trades, "wins": wins,
                "net_pnl": round(float(r.get("net_pnl") or 0.0), 2), "winrate": winrate}

    def _select(self, sql: str, params) -> List[Dict[str, Any]]:
        cur = self._cursor()
        cur.execute(self._q(sql), params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class SqliteRepository(SqlRepository):
    """Backend SQLite (por defecto; sin servidor)."""

    placeholder = "?"
    autoincrement = "INTEGER PRIMARY KEY AUTOINCREMENT"

    def __init__(self, path: str = ":memory:") -> None:
        super().__init__()
        self.path = path

    def _connect(self):
        # Crea la carpeta contenedora si no existe (SQLite no crea directorios).
        if self.path != ":memory:":
            parent = Path(self.path).parent
            if parent and not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)


class MySQLRepository(SqlRepository):
    """Backend MySQL (producción). Requiere PyMySQL; escribe donde lee el PHP."""

    placeholder = "%s"
    autoincrement = "BIGINT AUTO_INCREMENT PRIMARY KEY"

    def __init__(self, host: str = "localhost", port: int = 3306, database: str = "trading_system",
                 user: str = "root", password: str = "") -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password

    def _connect(self):  # pragma: no cover - requiere servidor MySQL
        try:
            import pymysql
        except ImportError as exc:
            raise PersistenceError(
                "PyMySQL no está instalado. `pip install pymysql` para el backend MySQL."
            ) from exc
        return pymysql.connect(
            host=self.host, port=self.port, database=self.database,
            user=self.user, password=self.password, autocommit=False,
        )
