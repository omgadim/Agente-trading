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

## ✅ Fase 4 — Inteligencia (Machine Learning) (ENTREGADA)

- [x] Ingeniería de features backward-looking (`ml/features.py`): retornos, RSI,
      MACD, ATR%, ADX, distancias a EMA, volumen, cuerpo/rango — sin look-ahead.
      Etiqueta de retorno futuro con horizonte configurable.
- [x] Abstracción de modelos (`ml/model.py`): `LogisticRegressionModel` en numpy
      puro (por defecto, sin dependencias) + adapters opcionales `SklearnGBModel`
      (GradientBoosting) y `XGBoostModel`, con import perezoso.
- [x] Validación *walk-forward* con ventana expansiva (`ml/training.py`), sin
      look-ahead, con accuracy global, por fold y baseline.
- [x] `MachineLearningAgent` (reemplaza el scaffold): auto-entrena sobre el
      histórico, reentrena periódicamente y predice la dirección de la última
      barra.
- [x] `MetaModelWeighting`: meta-modelo de *stacking* (regresión logística online
      por régimen) que aprende, a partir de los votos de todos los agentes y el
      resultado real, qué agentes pesan más en cada régimen. Se conecta al
      Supervisor vía el hook `observe()` (usado por `feedback` y por el backtester
      con `learn=True`).
- [x] Demo `examples/run_ml_train.py` y 16 tests nuevos (109 en total).

> Nota honesta: sobre los **datos simulados** (un *random walk* con deriva) los
> modelos rinden en torno al *baseline* — no hay edge que aprender, y así debe
> ser. El valor entregado es el **pipeline correcto y sin look-ahead**; el edge
> real solo puede evaluarse con datos de mercado reales (Fase 3 con MT5). El LSTM
> secuencial queda como ruta opcional (requiere TensorFlow/torch, comentados en
> `requirements.txt`); el modelo tabular (XGBoost) ya está integrado.

## ✅ Fase 5 — Contexto externo (ENTREGADA)

- [x] Paquete `context/` con proveedores inyectables (Adapter + DI): calendario
      económico (`InMemoryNewsProvider`, `CsvNewsProvider`), activos
      correlacionados (`InMemoryCorrelationProvider`) y sentimiento retail
      (`InMemorySentimentProvider`), cada uno tras su interfaz.
- [x] `NewsAgent`: *blackout* configurable antes/después de eventos de alto
      impacto (por defecto USD) → veta la operación (el Supervisor lo respeta vía
      `metadata['veto']`).
- [x] `CorrelationAgent`: sesgo `Σ corr_i · momentum_i` sobre DXY/US10Y/SPX (u
      otros); filtra por correlación mínima significativa.
- [x] `SentimentAgent`: contrarian sobre el posicionamiento retail (extremos
      largo/corto → SELL/BUY).
- [x] Demo `examples/run_context_demo.py` (veto por noticia + aporte de
      correlación/sentimiento) y 18 tests nuevos (125 en total).

> Los agentes de contexto quedan *enabled pero inertes* (WAIT) hasta que se les
> inyecta un proveedor: el `NewsAgent` puede cargar un CSV (`calendar_csv`);
> `correlation`/`sentiment` reciben el objeto en `agent.config['provider']`. En
> producción, los adapters reales (API de calendario, feed multi-símbolo de MT5,
> COT/sentiment) se conectan a esas mismas interfaces. `SentimentAgent` se añade
> como agente extra (#22) más allá de los 20 originales.

## ✅ Fase 6 — Persistencia y Dashboard (ENTREGADA)

- [x] Capa de persistencia (`persistence/`) con patrón Repository: interfaz única
      y dos backends sobre el mismo SQL — `SqliteRepository` (stdlib, por defecto,
      testeable en cualquier entorno) y `MySQLRepository` (producción, PyMySQL con
      import perezoso) que escribe en las **mismas tablas** que lee el panel PHP.
- [x] Persistencia de decisiones del Supervisor, aportes por agente, operaciones
      (apertura/cierre) y desempeño por agente/régimen.
- [x] Integración: `Backtester(repository=...)` persiste el ciclo de vida completo
      (decisión → apertura → cierre → desempeño); `LiveTrader(repository=...)`
      persiste decisión y apertura en vivo.
- [x] Dashboard PHP ampliado (`integrations/dashboard`): KPIs de PnL, desempeño
      por agente con barras, últimas decisiones y operaciones, auto-refresco.
- [x] Demo `examples/run_persistence_demo.py` (puebla una BD SQLite) y 7 tests
      nuevos (132 en total).

> El backend SQLite hace la persistencia ejecutable y testeable aquí; el panel
> PHP consume MySQL en producción con las mismas tablas (`MySQLRepository`
> requiere `pip install pymysql` y un servidor MySQL). Pine Script v6 de
> visualización se entregó en la Fase 1 (`integrations/pine`); su sincronización
> en vivo (alertas/webhooks → backend) es un refinamiento de la Fase 7.

## ✅ Fase 7 — Endurecimiento y despliegue (ENTREGADA)

- [x] CI (GitHub Actions): lint con ruff + tests en Python 3.10/3.11/3.12 +
      cobertura (`pytest-cov`). Ruff configurado en `pyproject.toml`; código
      lint-clean. Cobertura ~92%.
- [x] Alertas (`alerts/`): interfaz `Notifier` con `LoggingNotifier`,
      `TelegramNotifier`, `EmailNotifier` y `CompositeNotifier` (fan-out con
      aislamiento de fallos). Transporte inyectable (testeable sin red).
- [x] `KillSwitch` (`risk/kill_switch.py`): corta nuevas entradas por pérdida
      diaria, drawdown, rachas de pérdidas o flag manual (fichero).
- [x] Conciliación de cierres en vivo: `MT5Client.poll_closed_deals()` +
      `ClosedDeal`; el `LiveTrader` registra cierres (persistencia, riesgo,
      kill switch) y notifica apertura/cierre — **completa la persistencia live**.
- [x] Contenedores: `Dockerfile` (motor) y `docker-compose.yml` (MySQL +
      dashboard PHP + motor), con esquema MySQL auto-inicializado.
- [x] Runbook operativo (`docs/OPERACIONES.md`): despliegue, controles de riesgo,
      parada de emergencia, monitorización, respuesta a incidentes y checklist
      pre-real. 17 tests nuevos (149 en total).

> Con la Fase 7 se cierra el roadmap planificado. El sistema es funcional,
> testeado y desplegable en modo backtest/paper; el modo **live real** requiere
> ejecutar `RealMT5Client` en Windows con el terminal MT5 y validación previa en
> **cuenta demo** (ver runbook).

---

### Métricas de éxito (para todas las fases)
Winrate, Profit Factor, Expectancy, Sharpe, Max Drawdown, y **estabilidad
out-of-sample** (walk-forward). Ningún cambio se da por bueno sin backtest
reproducible.
