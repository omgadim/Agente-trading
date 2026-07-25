# 🥇 Sistema de Trading Institucional Multiagente — XAUUSD

Ecosistema de **agentes especializados** que analizan el Oro de forma
independiente y reportan a un **Supervisor Central** que pondera dinámicamente
cada opinión y decide **BUY / SELL / WAIT**, gestionando el riesgo y registrando
el porqué de cada decisión.

> Diseñado como software profesional para un fondo de inversión: modular,
> testeable, con logging, patrones de diseño y desarrollo por fases.

## 📚 Documentación

- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) — diseño completo del sistema.
- [`docs/AGENTES.md`](docs/AGENTES.md) — catálogo de agentes (20+).
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — plan por fases.

## 🧱 Arquitectura en una imagen

```
Datos (MT5/Sim) → [20+ Agentes → AgentDecision] → Supervisor (pesos dinámicos,
conflictos, score, riesgo) → RiskManager (veto+sizing) → Ejecución (Paper/MT5)
→ Persistencia MySQL + Dashboard PHP + Pine Script v6
```

Todos los agentes implementan `BaseAgent` y devuelven el mismo contrato
`AgentDecision` (señal, confianza 0-100, explicación, riesgo, SL, TP). Añadir un
agente nuevo no requiere tocar el Supervisor.

## 🚀 Inicio rápido

```bash
pip install -r requirements.txt

# Ejecuta un ciclo de decisión con datos simulados
PYTHONPATH=src python -m examples.run_demo

# Backtest walk-forward del sistema completo (con métricas)
PYTHONPATH=src python -m examples.run_backtest
```

```python
from trading_system.utils import load_config
from trading_system import TradingEngine

config = load_config("config/config.yaml")
engine = TradingEngine(config)          # usa datos simulados por defecto
decision = engine.run_once()
print(decision.signal, decision.confidence, decision.explanation)
```

## 🧪 Tests

```bash
pip install pytest
PYTHONPATH=src pytest        # o simplemente: pytest (configurado en pyproject)
```

## 🗂️ Estructura

```
src/trading_system/
├── core/          # contratos: AgentDecision, BaseAgent, registry, enums
├── data/          # indicadores + motor de estructura/liquidez + feeds
├── agents/        # agentes especializados (+ scaffolds de fases futuras)
├── supervisor/    # Supervisor + estrategias de ponderación
├── risk/          # RiskManager (sizing + veto) + gestión de posiciones
├── execution/     # broker/feed MT5 (interfaz MT5Client), guards, PaperBroker
├── ml/            # features, modelos (logística/GB/XGBoost), walk-forward
├── context/       # proveedores externos: noticias, correlación, sentimiento
├── persistence/   # Repository (SQLite/MySQL) de decisiones/operaciones
├── alerts/        # notificaciones: Logging/Telegram/Email/Composite
├── backtest/      # backtester walk-forward + métricas
├── utils/         # logging, config
├── engine.py      # fachada TradingEngine (backtest/decisión)
└── live.py        # LiveTrader (live/paper + kill switch + conciliación)
integrations/
├── pine/          # Pine Script v6 (visualización TradingView)
└── dashboard/     # PHP + MySQL (Fase 6)
.github/workflows/ # CI (lint + tests + cobertura)
Dockerfile · docker-compose.yml   # despliegue (Fase 7)
```

## 🧠 Estado

- **Fase 1 ✅** — núcleo + 11 agentes reales + Supervisor con ponderación
  adaptativa + gestión de riesgo + tests.
- **Fase 2 ✅** — motor compartido de estructura/liquidez + 6 agentes Smart Money
  (SMC, Order Blocks, FVG, Liquidity Sweeps, Wyckoff, Harmonic) + backtester
  walk-forward con métricas (winrate, PF, expectancy, max drawdown, Sharpe).
- **Fase 3 ✅** — conexión MetaTrader 5 vía interfaz `MT5Client` (adapter real +
  cliente simulado), `MT5Broker`/`MT5DataFeed`, `MarketGuard` (spread/horario) y
  `LiveTrader` (gestión de posiciones + trailing/break-even). Sesión paper
  reproducible: `python -m examples.run_live_paper`.
- **Fase 4 ✅** — Machine Learning: features sin look-ahead, modelos
  (logística en numpy + GradientBoosting/XGBoost opcionales), validación
  walk-forward, `MachineLearningAgent` y `MetaModelWeighting` (meta-modelo de
  stacking que aprende el peso de cada agente por régimen). Demo:
  `python -m examples.run_ml_train`.
- **Fase 5 ✅** — Contexto externo con proveedores inyectables: `NewsAgent`
  (veto por calendario económico), `CorrelationAgent` (DXY/US10Y/SPX) y
  `SentimentAgent` (contrarian retail). Demo: `python -m examples.run_context_demo`.
- **Fase 6 ✅** — Persistencia (patrón Repository, SQLite/MySQL) de decisiones,
  operaciones y desempeño por agente/régimen; dashboard PHP con KPIs y desempeño.
  Demo: `python -m examples.run_persistence_demo`.
- **Fase 7 ✅** — Endurecimiento y despliegue: CI (lint + tests + cobertura ~92%),
  alertas (Telegram/Email/Composite), `KillSwitch` (pérdida diaria/drawdown/
  rachas/flag manual), conciliación de cierres en vivo, Docker y runbook
  operativo (`docs/OPERACIONES.md`).

**Roadmap completo (Fases 1-7).** **21 agentes reales** operativos y 1 scaffold
(Elliott). Backtests, sesión paper y ML usan **datos simulados** — validan la
mecánica y el pipeline, no un *edge* real. La operativa real requiere
`RealMT5Client` en una **cuenta demo** de Windows (el paquete `MetaTrader5` es
solo-Windows) y proveedores de contexto reales conectados a las interfaces de
`context/`. Ver [`docs/ROADMAP.md`](docs/ROADMAP.md) y
[`docs/OPERACIONES.md`](docs/OPERACIONES.md).

## ⚠️ Aviso

Software educativo/experimental. El trading con apalancamiento conlleva riesgo de
pérdida. Pruébalo siempre en cuenta demo antes de cualquier uso real.
