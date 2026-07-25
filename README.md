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
├── risk/          # RiskManager (sizing + veto)
├── execution/     # broker interface, PaperBroker, MT5Broker (Fase 3)
├── backtest/      # backtester walk-forward + métricas
├── utils/         # logging, config
└── engine.py      # fachada TradingEngine
integrations/
├── pine/          # Pine Script v6 (visualización TradingView)
└── dashboard/     # PHP + MySQL (Fase 6)
```

## 🧠 Estado

- **Fase 1 ✅** — núcleo + 11 agentes reales + Supervisor con ponderación
  adaptativa + gestión de riesgo + tests.
- **Fase 2 ✅** — motor compartido de estructura/liquidez + 6 agentes Smart Money
  (SMC, Order Blocks, FVG, Liquidity Sweeps, Wyckoff, Harmonic) + backtester
  walk-forward con métricas (winrate, PF, expectancy, max drawdown, Sharpe).

**17 agentes reales** operativos y 4 scaffolds (Elliott, Correlación, Noticias,
ML) para fases posteriores. Los backtests actuales usan **datos simulados** —
validan la mecánica, no un *edge* real; la validación con datos reales llega en
la Fase 3. Ver [`docs/ROADMAP.md`](docs/ROADMAP.md).

## ⚠️ Aviso

Software educativo/experimental. El trading con apalancamiento conlleva riesgo de
pérdida. Pruébalo siempre en cuenta demo antes de cualquier uso real.
