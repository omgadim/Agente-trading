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

## 🔜 Fase 2 — Agentes Smart Money y Price Action

- [ ] Implementar SMC, OrderBlocks, FVG, LiquiditySweeps, Wyckoff, Harmonic.
- [ ] Motor de detección de swings y liquidez compartido.
- [ ] Backtester con métricas (winrate, PF, expectancy, max drawdown).
- [ ] Tests de cada detector con velas sintéticas de referencia.

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
