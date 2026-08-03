"""Interfaz `MT5Client` y sus implementaciones (Adapter + DI).

Toda la API concreta de MetaTrader 5 queda aislada tras esta interfaz. Así el
resto del sistema (feed, broker, live trader) depende de una abstracción y puede
implementarse y testearse **sin el terminal MT5** (solo-Windows) mediante
`SimulatedMT5Client`. En producción se inyecta `RealMT5Client`.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

from ..core.enums import SignalType, Timeframe
from ..core.exceptions import ExecutionError


# --------------------------------------------------------------------------- #
#  Tipos de dominio (independientes de MT5)
# --------------------------------------------------------------------------- #
@dataclass
class AccountInfo:
    login: int
    balance: float
    equity: float
    currency: str = "USD"
    leverage: int = 100


@dataclass
class SymbolInfo:
    name: str
    point: float
    digits: int
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    stops_level: float  # distancia mínima (en precio) permitida para SL/TP
    bid: float
    ask: float

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass
class Tick:
    bid: float
    ask: float
    time: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


@dataclass
class Position:
    ticket: int
    symbol: str
    direction: SignalType  # BUY | SELL
    volume: float
    price_open: float
    price_current: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    profit: float = 0.0


@dataclass
class ClosedDeal:
    """Operación cerrada (por SL/TP en el broker o manualmente)."""

    ticket: int
    symbol: str
    exit_price: float
    pnl: float


@dataclass
class OrderRequest:
    symbol: str
    direction: SignalType  # BUY | SELL
    volume: float
    price: Optional[float] = None  # None => a mercado
    sl: Optional[float] = None
    tp: Optional[float] = None
    deviation: int = 20
    comment: str = ""
    magic: int = 0


@dataclass
class OrderResult:
    success: bool
    retcode: int
    ticket: Optional[int] = None
    price: Optional[float] = None
    comment: str = ""


# --------------------------------------------------------------------------- #
#  Interfaz
# --------------------------------------------------------------------------- #
class MT5Client(ABC):
    """Contrato de acceso a MetaTrader 5 (datos + trading)."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...

    @abstractmethod
    def account(self) -> AccountInfo: ...

    @abstractmethod
    def symbol_info(self, symbol: str) -> SymbolInfo: ...

    @abstractmethod
    def tick(self, symbol: str) -> Tick: ...

    @abstractmethod
    def rates(self, symbol: str, timeframe: Timeframe, count: int) -> pd.DataFrame: ...

    @abstractmethod
    def send_order(self, request: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def modify_position(
        self, ticket: int, sl: Optional[float], tp: Optional[float]
    ) -> OrderResult: ...

    @abstractmethod
    def close_position(self, ticket: int) -> OrderResult: ...

    @abstractmethod
    def positions(self, symbol: Optional[str] = None) -> List[Position]: ...

    def poll_closed_deals(self) -> List["ClosedDeal"]:
        """Operaciones cerradas desde la última consulta. Por defecto ninguna."""
        return []


# --------------------------------------------------------------------------- #
#  Adapter real (solo Windows con terminal MT5). Import perezoso.
# --------------------------------------------------------------------------- #
class RealMT5Client(MT5Client):
    """Implementación sobre el paquete `MetaTrader5`.

    El paquete solo existe en Windows con el terminal instalado, por lo que este
    entorno no puede ejecutar sus llamadas; las secciones que requieren el
    terminal están marcadas `# pragma: no cover`. La lógica de traducción
    (dominio <-> MT5) sí es código de producción real.
    """

    def __init__(
        self,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        path: Optional[str] = None,
        magic: int = 20250725,
        retries: int = 4,
        filling: str = "IOC",
    ) -> None:
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.magic = magic
        self.retries = retries
        self.filling = filling
        self._mt5 = None
        self._tf_map: Dict[Timeframe, int] = {}
        self._known_open: set = set()   # tickets de posiciones abiertas (para detectar cierres)
        self._known_init = False

    # ---- conexión ----
    def connect(self) -> None:  # pragma: no cover - requiere terminal MT5
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise ExecutionError(
                "El paquete MetaTrader5 no está instalado (solo Windows). "
                "Instálalo en el entorno de producción para el modo live."
            ) from exc

        base = {}
        if self.path:
            base["path"] = self.path
        login_kwargs = dict(base)
        if self.login:
            login_kwargs.update(login=self.login, password=self.password, server=self.server)

        last_err = None
        for attempt in range(1, self.retries + 1):
            # 1) ATTACH primero: adjuntarse a un terminal ya abierto y autorizado
            #    SIN re-loguear. Es clave para correr varias instancias (una por
            #    instrumento) contra el MISMO terminal/cuenta sin la carrera de
            #    logins que devuelve "-6 Authorization failed": solo la primera
            #    instancia (o el propio terminal) autentica; las demás se adjuntan.
            if mt5.initialize(**base):
                info = mt5.account_info()
                if info is not None and (not self.login or info.login == self.login):
                    self._finish_connect(mt5)
                    return
                mt5.shutdown()  # terminal abierto pero sin la sesión esperada
            # 2) LOGIN explícito (solo si tenemos credenciales): abre/autentica.
            if self.login and mt5.initialize(**login_kwargs):
                self._finish_connect(mt5)
                return
            last_err = mt5.last_error()
            time.sleep(2 ** attempt)
        raise ExecutionError(f"initialize() falló tras {self.retries} intentos: {last_err}")

    def _finish_connect(self, mt5) -> None:  # pragma: no cover - requiere terminal MT5
        self._mt5 = mt5
        self._tf_map = {
            Timeframe.M1: mt5.TIMEFRAME_M1,
            Timeframe.M5: mt5.TIMEFRAME_M5,
            Timeframe.M15: mt5.TIMEFRAME_M15,
            Timeframe.M30: mt5.TIMEFRAME_M30,
            Timeframe.H1: mt5.TIMEFRAME_H1,
            Timeframe.H4: mt5.TIMEFRAME_H4,
            Timeframe.D1: mt5.TIMEFRAME_D1,
        }

    def shutdown(self) -> None:  # pragma: no cover - requiere terminal MT5
        if self._mt5 is not None:
            self._mt5.shutdown()
            self._mt5 = None

    def _require(self):  # pragma: no cover - requiere terminal MT5
        if self._mt5 is None:
            raise ExecutionError("Cliente MT5 no conectado; llama a connect() primero")
        return self._mt5

    # ---- datos ----
    def account(self) -> AccountInfo:  # pragma: no cover - requiere terminal MT5
        mt5 = self._require()
        info = mt5.account_info()
        if info is None:
            raise ExecutionError(f"account_info() falló: {mt5.last_error()}")
        return AccountInfo(info.login, info.balance, info.equity, info.currency, info.leverage)

    def symbol_info(self, symbol: str) -> SymbolInfo:  # pragma: no cover
        mt5 = self._require()
        if not mt5.symbol_select(symbol, True):
            raise ExecutionError(f"symbol_select({symbol}) falló: {mt5.last_error()}")
        s = mt5.symbol_info(symbol)
        if s is None:
            raise ExecutionError(f"symbol_info({symbol}) devolvió None")
        return SymbolInfo(
            name=s.name, point=s.point, digits=s.digits,
            contract_size=s.trade_contract_size, volume_min=s.volume_min,
            volume_max=s.volume_max, volume_step=s.volume_step,
            stops_level=s.trade_stops_level * s.point, bid=s.bid, ask=s.ask,
        )

    def tick(self, symbol: str) -> Tick:  # pragma: no cover - requiere terminal MT5
        mt5 = self._require()
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            raise ExecutionError(f"symbol_info_tick({symbol}) devolvió None")
        return Tick(bid=t.bid, ask=t.ask, time=datetime.fromtimestamp(t.time, tz=timezone.utc))

    def rates(self, symbol: str, timeframe: Timeframe, count: int) -> pd.DataFrame:  # pragma: no cover
        mt5 = self._require()
        tf = self._tf_map[timeframe]
        arr = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if arr is None or len(arr) == 0:
            raise ExecutionError(f"copy_rates_from_pos({symbol}) falló: {mt5.last_error()}")
        df = pd.DataFrame(arr)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.set_index("time")
        df = df.rename(columns={"tick_volume": "volume"})
        return df[["open", "high", "low", "close", "volume"]].astype(float)

    # ---- trading ----
    def _filling_mode(self):  # pragma: no cover - requiere terminal MT5
        mt5 = self._mt5
        return mt5.ORDER_FILLING_FOK if self.filling.upper() == "FOK" else mt5.ORDER_FILLING_IOC

    def send_order(self, request: OrderRequest) -> OrderResult:  # pragma: no cover
        mt5 = self._require()
        tick = self.tick(request.symbol)
        is_buy = request.direction is SignalType.BUY
        price = request.price or (tick.ask if is_buy else tick.bid)
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": request.symbol,
            "volume": float(request.volume),
            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": request.deviation,
            "magic": request.magic or self.magic,
            "comment": request.comment or "multiagent",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(),
        }
        if request.sl:
            req["sl"] = float(request.sl)
        if request.tp:
            req["tp"] = float(request.tp)
        result = mt5.order_send(req)
        return self._to_result(result, mt5)

    def modify_position(self, ticket, sl, tp) -> OrderResult:  # pragma: no cover
        mt5 = self._require()
        pos = self._find_raw(ticket)
        if pos is None:
            return OrderResult(False, -1, ticket, None, "posición no encontrada")
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": float(sl) if sl else 0.0,
            "tp": float(tp) if tp else 0.0,
        }
        return self._to_result(mt5.order_send(req), mt5)

    def close_position(self, ticket: int) -> OrderResult:  # pragma: no cover
        mt5 = self._require()
        pos = self._find_raw(ticket)
        if pos is None:
            return OrderResult(False, -1, ticket, None, "posición no encontrada")
        is_buy = pos.type == mt5.POSITION_TYPE_BUY
        tick = self.tick(pos.symbol)
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "position": ticket,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "price": tick.bid if is_buy else tick.ask,
            "deviation": 20,
            "magic": self.magic,
            "comment": "close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(),
        }
        return self._to_result(mt5.order_send(req), mt5)

    def positions(self, symbol: Optional[str] = None) -> List[Position]:  # pragma: no cover
        mt5 = self._require()
        raw = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        out: List[Position] = []
        for p in raw or []:
            direction = SignalType.BUY if p.type == mt5.POSITION_TYPE_BUY else SignalType.SELL
            out.append(Position(
                ticket=p.ticket, symbol=p.symbol, direction=direction, volume=p.volume,
                price_open=p.price_open, price_current=p.price_current,
                sl=p.sl or None, tp=p.tp or None, profit=p.profit,
            ))
        return out

    def poll_closed_deals(self) -> List[ClosedDeal]:  # pragma: no cover - requiere terminal MT5
        """Detecta las posiciones que se han CERRADO desde la última consulta.

        Compara los tickets abiertos ahora contra los que estaban abiertos en la
        llamada anterior: los que desaparecieron se cerraron (SL/TP/trailing/manual).
        Para cada uno recupera el beneficio realizado y el precio de salida del
        historial de operaciones (deal de cierre). Devuelve la lista para que el
        LiveTrader marque el cierre en la base de datos, alimente el kill switch y
        el aprendizaje. La PRIMERA llamada solo memoriza (no cierra nada retroactivo).
        """
        mt5 = self._require()
        raw = mt5.positions_get() or []
        current = {p.ticket for p in raw}

        if not self._known_init:          # primera vez: solo sembrar, sin cierres
            self._known_open = current
            self._known_init = True
            return []

        closed_tickets = self._known_open - current
        self._known_open = current
        deals: List[ClosedDeal] = []
        for ticket in closed_tickets:
            exit_price, profit, symbol = self._closing_info(mt5, ticket)
            deals.append(ClosedDeal(ticket, symbol or "", exit_price, profit))
        return deals

    def _closing_info(self, mt5, ticket: int):  # pragma: no cover - requiere terminal MT5
        """Beneficio realizado (profit+swap+comisión) y precio de salida de una
        posición cerrada, desde su historial de deals (por position_id)."""
        try:
            hist = mt5.history_deals_get(position=ticket) or ()
        except Exception:
            hist = ()
        profit = 0.0; exit_price = 0.0; symbol = None
        out_type = getattr(mt5, "DEAL_ENTRY_OUT", 1)
        for d in hist:
            profit += float(getattr(d, "profit", 0.0)) + float(getattr(d, "swap", 0.0)) \
                + float(getattr(d, "commission", 0.0))
            symbol = getattr(d, "symbol", symbol)
            if getattr(d, "entry", None) == out_type:
                exit_price = float(getattr(d, "price", 0.0))
        return exit_price, profit, symbol

    def _find_raw(self, ticket: int):  # pragma: no cover - requiere terminal MT5
        raw = self._mt5.positions_get(ticket=ticket)
        return raw[0] if raw else None

    def _to_result(self, result, mt5) -> OrderResult:  # pragma: no cover
        if result is None:
            return OrderResult(False, -1, None, None, f"order_send None: {mt5.last_error()}")
        ok = result.retcode == mt5.TRADE_RETCODE_DONE
        return OrderResult(
            success=ok, retcode=result.retcode,
            ticket=getattr(result, "order", None) or None,
            price=getattr(result, "price", None), comment=result.comment,
        )


# --------------------------------------------------------------------------- #
#  Cliente simulado (in-memory) — corre y se testea en cualquier SO
# --------------------------------------------------------------------------- #
class SimulatedMT5Client(MT5Client):
    """Simula el terminal MT5 sobre una serie histórica base (timeframe fino).

    Mantiene un cursor temporal (`advance()` avanza barras), sirve datos hasta el
    cursor (sin look-ahead), y ejecuta órdenes en memoria con spread. Al avanzar,
    cierra automáticamente las posiciones que tocan SL/TP (como haría el bróker).
    """

    def __init__(
        self,
        base_df: pd.DataFrame,
        symbol: str = "XAUUSD",
        base_minutes: int = 5,
        spread: float = 0.20,
        contract_size: float = 100.0,
        balance: float = 10_000.0,
        start: int = 300,
    ) -> None:
        from ..data import resample_ohlcv  # import local para evitar ciclos

        self._resample = resample_ohlcv
        self.base = base_df
        self.symbol = symbol
        self.base_minutes = base_minutes
        self.spread = spread
        self.contract_size = contract_size
        self.balance = balance
        self._cursor = min(start, len(base_df) - 1)
        self._positions: Dict[int, Position] = {}
        self._next_ticket = 1000
        self.realized_pnl = 0.0
        self.closed: List[Position] = []
        self._closed_cursor = 0
        self._connected = False

    # ---- ciclo de vida ----
    def connect(self) -> None:
        self._connected = True

    def shutdown(self) -> None:
        self._connected = False

    @property
    def cursor(self) -> int:
        return self._cursor

    def has_next(self) -> bool:
        return self._cursor < len(self.base) - 1

    def advance(self, steps: int = 1) -> None:
        """Avanza el cursor y resuelve SL/TP de las posiciones abiertas."""
        for _ in range(steps):
            if not self.has_next():
                break
            self._cursor += 1
            self._resolve_sl_tp()

    # ---- datos ----
    def _current_bar(self) -> pd.Series:
        return self.base.iloc[self._cursor]

    def _price(self) -> float:
        return float(self._current_bar()["close"])

    def account(self) -> AccountInfo:
        floating = sum(self._pnl(p, self._price()) for p in self._positions.values())
        return AccountInfo(login=0, balance=self.balance, equity=self.balance + floating)

    def symbol_info(self, symbol: str) -> SymbolInfo:
        price = self._price()
        half = self.spread / 2.0
        return SymbolInfo(
            name=symbol, point=0.01, digits=2, contract_size=self.contract_size,
            volume_min=0.01, volume_max=50.0, volume_step=0.01, stops_level=0.0,
            bid=price - half, ask=price + half,
        )

    def tick(self, symbol: str) -> Tick:
        price = self._price()
        half = self.spread / 2.0
        ts = self.base.index[self._cursor]
        return Tick(bid=price - half, ask=price + half, time=ts.to_pydatetime())

    def rates(self, symbol: str, timeframe: Timeframe, count: int) -> pd.DataFrame:
        window = self.base.iloc[: self._cursor + 1]
        if timeframe.minutes == self.base_minutes:
            df = window
        else:
            df = self._resample(window, timeframe.minutes)
        return df.iloc[-count:].astype(float)

    # ---- trading ----
    def send_order(self, request: OrderRequest) -> OrderResult:
        if not self._connected:
            return OrderResult(False, -1, None, None, "no conectado")
        tick = self.tick(request.symbol)
        is_buy = request.direction is SignalType.BUY
        fill = request.price or (tick.ask if is_buy else tick.bid)
        ticket = self._next_ticket
        self._next_ticket += 1
        self._positions[ticket] = Position(
            ticket=ticket, symbol=request.symbol, direction=request.direction,
            volume=request.volume, price_open=fill, price_current=fill,
            sl=request.sl, tp=request.tp,
        )
        return OrderResult(True, 10009, ticket, fill, "done")

    def modify_position(self, ticket, sl, tp) -> OrderResult:
        pos = self._positions.get(ticket)
        if pos is None:
            return OrderResult(False, -1, ticket, None, "no encontrada")
        if sl is not None:
            pos.sl = sl
        if tp is not None:
            pos.tp = tp
        return OrderResult(True, 10009, ticket, None, "modified")

    def close_position(self, ticket: int, price: Optional[float] = None) -> OrderResult:
        pos = self._positions.pop(ticket, None)
        if pos is None:
            return OrderResult(False, -1, ticket, None, "no encontrada")
        exit_price = price if price is not None else self._price()
        pnl = self._pnl(pos, exit_price)
        self.realized_pnl += pnl
        self.balance += pnl
        pos.price_current = exit_price
        pos.profit = pnl
        self.closed.append(pos)
        return OrderResult(True, 10009, ticket, exit_price, "closed")

    def positions(self, symbol: Optional[str] = None) -> List[Position]:
        price = self._price()
        result = []
        for p in self._positions.values():
            if symbol and p.symbol != symbol:
                continue
            p.price_current = price
            p.profit = self._pnl(p, price)
            result.append(p)
        return result

    def poll_closed_deals(self) -> List[ClosedDeal]:
        """Devuelve las posiciones cerradas (SL/TP/manual) desde la última consulta."""
        new = self.closed[self._closed_cursor:]
        self._closed_cursor = len(self.closed)
        return [ClosedDeal(p.ticket, p.symbol, p.price_current, p.profit) for p in new]

    # ---- internos ----
    def _pnl(self, pos: Position, exit_price: float) -> float:
        direction = 1 if pos.direction is SignalType.BUY else -1
        return (exit_price - pos.price_open) * direction * pos.volume * self.contract_size

    def _resolve_sl_tp(self) -> None:
        bar = self._current_bar()
        high, low = float(bar["high"]), float(bar["low"])
        for ticket, pos in list(self._positions.items()):
            if pos.direction is SignalType.BUY:
                if pos.sl is not None and low <= pos.sl:
                    self.close_position(ticket, pos.sl)
                elif pos.tp is not None and high >= pos.tp:
                    self.close_position(ticket, pos.tp)
            else:  # SELL
                if pos.sl is not None and high >= pos.sl:
                    self.close_position(ticket, pos.sl)
                elif pos.tp is not None and low <= pos.tp:
                    self.close_position(ticket, pos.tp)
