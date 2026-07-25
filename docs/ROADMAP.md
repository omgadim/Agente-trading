# Roadmap por Fases

Desarrollo incremental estilo fondo de inversión. **Al cerrar cada fase**:
revisar código, optimizar, buscar errores, mejorar rendimiento, crear/ampliar
pruebas automáticas y documentar.

---

## ✅ Fase 1 — Núcleo y framework de agentes (ENTREGADA)

**Objetivo:** base modular sólida, testeable sin broker.

- [x] Contrato `AgentDecision` + `SignalType` (BUY/SELL/WAIT).
- [x] `MarketData` multi-timeframe y `MarketRegime`.
- [x] `BaseAgent` (Template Method: `run()` envuelve `analyze()` con manejo de
      errores/timing) + `AgentRegistry` (Registry/Factory).
- [x] Librería de indicadores (EMA, RSI, MACD, ATR, ADX) en pandas/numpy.
- [x] Agentes reales: Trend MTF, Technical, Momentum, Volatility, Volume,
      MarketStructure, Support/Resistance, Candlestick, Session, Risk,
      OpenTradesControl.
- [x] `Supervisor` con `WeightingStrategy` (Static + Adaptive) y detección de
      conflictos.
- [x] `RiskManager` con sizing por ATR y veto.
- [x] `DataFeed` (interface) + `SimulatedDataFeed` para tests/backtest.
- [x] Logging, configuración YAML, tests `pytest`.

## ✅ Fase 2 — Agentes Smart Money y Price Action (ENTREGADA)

- [x] Motor compartido de estructura y liquidez (`data/structure.py`): swings,
      estructura (BOS/CHoCH), FVG, Order Blocks, pools de liquidez, sweeps,
      zigzag alternado y zonas premium/discount.
- [x] 6 agentes reales que reemplazan sus scaffolds: `smart_money` (confluencia
      estructura + premium/discount), `order_blocks`, `fair_value_gap`,
      `liquidity_sweep`, `wyckoff` (spring/upthrust), `harmonic`
      (Gartley/Bat/Butterfly/Crab por ratios de Fibonacci).
- [x] Backtester walk-forward (`backtest/`) con SL/TP, sin *look-ahead*, y
      métricas: winrate, profit factor, expectancy, PnL neto, max drawdown,
      Sharpe. Soporta retroalimentar la ponderación adaptativa (`learn=True`).
- [x] Tests de cada detector con velas sintéticas de referencia + tests del
      backtester y las métricas (69 tests en total).

> Nota honesta: el backtest actual corre sobre **datos simulados**; sirve para
> validar la mecánica (ejecución, métricas, ausencia de look-ahead), NO para
> afirmar que existe *edge*. La validación con datos reales de MT5 llega en la
> Fase 3, y la robustez out-of-sample (walk-forward sobre histórico real) es un
> criterio de cierre transversal.

### Optimización pendiente (deuda técnica reconocida)
- El backtester reconstruye el `MarketData` por remuestreo en cada paso (O(n²)).
  Para históricos largos conviene un remuestreo incremental/cacheado (Fase 3).

## ✅ Fase 3 — Conexión MetaTrader 5 (ENTREGADA)

- [x] Interfaz `MT5Client` (Adapter + DI) que aísla toda la API de MT5, con dos
      implementaciones: `RealMT5Client` (adapter sobre el paquete `MetaTrader5`,
      import perezoso, reconexión con backoff) y `SimulatedMT5Client` (terminal
      en memoria que corre y se testea en cualquier SO).
- [x] `MT5Broker` (envío de órdenes a mercado, SL/TP, `modify` para
      trailing/break-even, cierre) y `MT5DataFeed` (velas multi-timeframe + tick),
      ambos sobre la interfaz.
- [x] `MarketGuard`: spread máximo, horario UTC (con ventanas que cruzan
      medianoche) y bloqueo de fin de semana.
- [x] `LiveTrader`: orquestador de un ciclo live/paper (gestión de abiertas →
      guardián → decisión → apertura dimensionada por riesgo). Regla de
      trailing/BE compartida (`risk/management.py`) entre agente y live trader.
- [x] Demo `examples/run_live_paper.py` (sesión paper reproducible sin terminal)
      y 24 tests nuevos (93 en total).

> Nota honesta: el paquete `MetaTrader5` es **solo-Windows** y no puede
> ejecutarse en este entorno Linux, así que las llamadas al terminal en
> `RealMT5Client` están marcadas `# pragma: no cover`. Toda la lógica (traducción
> dominio↔MT5, broker, feed, guardián, live trader, trailing) se valida con
> `SimulatedMT5Client`. **Pendiente en el usuario:** ejecutar el mismo código con
> `RealMT5Client.connect()` en una **cuenta demo** de Windows para validación
> end-to-end contra un broker real.

## 🔜 Fase 4 — Inteligencia (Machine Learning)

- [ ] `MachineLearningAgent`: features engineering + LSTM (secuencial) y XGBoost
      (tabular). Validación *walk-forward*, sin *look-ahead*.
- [ ] `MetaModelWeighting`: meta-modelo (stacking) que aprende qué agentes
      aciertan por régimen → pesos del Supervisor.
- [ ] Registro de features/decisiones para reentrenamiento continuo.

## 🔜 Fase 5 — Contexto externo

- [ ] `NewsAgent` (calendario económico, alto impacto → veto/timing).
- [ ] `CorrelationAgent` (DXY, US10Y, SPX).
- [ ] `SentimentAgent`.

## 🔜 Fase 6 — Persistencia y Dashboard

- [ ] Esquema MySQL + capa de persistencia de decisiones/operaciones.
- [ ] Dashboard PHP: estado en vivo, historial, desempeño por agente, PnL.
- [ ] Pine Script v6: indicadores de visualización sincronizados.

## 🔜 Fase 7 — Endurecimiento y despliegue

- [ ] CI (lint + tests), cobertura, contenedores.
- [ ] Alertas (Telegram/email), watchdog y *kill switch*.
- [ ] Documentación operativa y *runbooks*.

---

### Métricas de éxito (para todas las fases)
Winrate, Profit Factor, Expectancy, Sharpe, Max Drawdown, y **estabilidad
out-of-sample** (walk-forward). Ningún cambio se da por bueno sin backtest
reproducible.
