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

## 🔜 Fase 3 — Conexión real MetaTrader 5

- [ ] `MT5Connector` (adapter) con reconexión y control de errores.
- [ ] `MT5Broker` (envío de órdenes, SL/TP, trailing, cierre parcial).
- [ ] Gestión de sesión, spread y horario; modo *live* vs *paper*.
- [ ] Pruebas en cuenta demo.

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
