# Arquitectura Multiagente — Sistema de Trading Institucional (XAUUSD)

> Documento de diseño. Escrito por el equipo: *trader institucional, quant,
> científico de datos, ingeniero de ML, desarrollador senior de Python/MT5/Pine
> y arquitecto de software.*

## 1. Visión

Un **ecosistema de agentes especializados** que analizan el mercado de forma
independiente y reportan su conclusión a un **Supervisor Central**. El Supervisor
pondera dinámicamente cada opinión (idealmente mediante un meta-modelo de IA que
aprende qué agente acierta en cada régimen de mercado) y decide **BUY / SELL /
WAIT**, gestionando el riesgo y registrando *por qué* tomó cada decisión.

Principios rectores:

- **Modularidad**: agregar un agente nuevo = crear una clase y registrarla. Cero
  cambios en el Supervisor.
- **Contrato único**: todos los agentes hablan el mismo lenguaje (`AgentDecision`).
- **Separación de responsabilidades**: datos ≠ análisis ≠ decisión ≠ riesgo ≠
  ejecución.
- **Testeable sin broker**: la lógica de análisis no depende de MetaTrader5; se
  prueba con datos simulados/históricos.
- **Observabilidad**: logging estructurado y trazabilidad de cada decisión.

## 2. Diagrama de alto nivel

```
                         ┌──────────────────────────┐
                         │      Fuentes de datos     │
                         │  MT5 (live) / CSV / Sim   │
                         └────────────┬─────────────┘
                                      │  MarketData (multi-timeframe OHLCV)
                                      ▼
        ┌───────────────────────────────────────────────────────────┐
        │                     Capa de Agentes                        │
        │   (todos implementan BaseAgent → devuelven AgentDecision)  │
        │                                                            │
        │  Trend · SMC · OrderBlocks · FVG · LiquiditySweeps ·       │
        │  Wyckoff · Elliott · MarketStructure · S/R · Volume ·      │
        │  Volatility · Momentum · TechnicalIndicators · Candles ·   │
        │  Harmonic · Correlation · News · Risk · ML · OpenTrades... │
        └───────────────────────────┬───────────────────────────────┘
                                     │  List[AgentDecision]
                                     ▼
        ┌───────────────────────────────────────────────────────────┐
        │                    Supervisor Central                      │
        │  1. Recolecta decisiones (en paralelo)                     │
        │  2. WeightingStrategy → peso dinámico por agente           │
        │  3. ConflictDetector → detecta desacuerdos                 │
        │  4. Agregación → puntuación global + SL/TP + riesgo        │
        │  5. RiskManager (poder de veto y sizing)                   │
        │  6. Registra el razonamiento (SupervisorDecision)          │
        └───────────────────────────┬───────────────────────────────┘
                                     │  SupervisorDecision
                                     ▼
        ┌───────────────────────────────────────────────────────────┐
        │                   Capa de Ejecución                        │
        │   ExecutionBroker (interface)                              │
        │   ├─ PaperBroker (simulado, para tests/backtest)           │
        │   └─ MT5Broker   (órdenes reales en MetaTrader 5)          │
        └───────────────────────────┬───────────────────────────────┘
                                     │  eventos / fills
                                     ▼
                 ┌──────────────────────────────────────┐
                 │  Persistencia (MySQL) + Dashboard PHP │
                 │  Pine Script v6 (visualización TV)    │
                 └──────────────────────────────────────┘
```

## 3. Contrato del sistema (el corazón)

Todo agente recibe un `MarketData` y devuelve un `AgentDecision`:

```python
AgentDecision(
    agent_name: str,
    signal: SignalType,        # BUY | SELL | WAIT
    confidence: float,         # 0-100
    explanation: str,          # por qué
    estimated_risk: float,     # 0-100 (riesgo percibido de la operación)
    stop_loss: float | None,   # precio sugerido
    take_profit: float | None, # precio sugerido
    metadata: dict,            # datos crudos para auditoría/ML
    timestamp: datetime,
)
```

Este contrato es la clave de la escalabilidad: el Supervisor no conoce la lógica
interna de ningún agente, solo el contrato. Añadir el agente #37 no rompe nada.

## 4. Patrones de diseño empleados

| Patrón | Dónde | Por qué |
|--------|-------|---------|
| **Strategy** | `BaseAgent`, `WeightingStrategy`, `ExecutionBroker` | Intercambiar algoritmos sin tocar el orquestador |
| **Registry + Factory** | `AgentRegistry` (`@register_agent`) | Alta de agentes por configuración, descubrimiento automático |
| **Template Method** | `BaseAgent.run()` → `analyze()` | `run()` envuelve con manejo de errores/timing; el agente solo implementa `analyze()` |
| **Facade** | `TradingEngine` | Un único punto de entrada que orquesta datos→agentes→supervisor→ejecución |
| **Observer / eventos** | logging y dashboard | Desacoplar la emisión de eventos de su consumo |
| **Dependency Injection** | Supervisor, Engine | Inyectar feed, brokers y estrategias (facilita tests) |
| **Adapter** | `MT5Connector` | Aislar la API concreta de MetaTrader5 |

## 5. Supervisor y aprendizaje

El Supervisor NO usa reglas fijas de pesos. Usa una `WeightingStrategy`
intercambiable:

1. **StaticWeighting** — pesos de configuración (punto de partida / fallback).
2. **AdaptiveWeighting** — mantiene el desempeño histórico de cada agente por
   **régimen de mercado** (tendencia alcista/bajista/rango, alta/baja
   volatilidad) y ajusta el peso según su *hit-rate* reciente (media móvil
   exponencial). Es un aprendizaje online, ligero y explicable.
3. **MetaModelWeighting** (Fase ML) — un **meta-modelo** (p. ej. gradient boosting
   / red ligera) toma como features las decisiones+confianzas de todos los
   agentes y el contexto de mercado, y predice la probabilidad de éxito. Es el
   "stacking" del ecosistema: aprende qué combinación de agentes funciona en cada
   condición.

La agregación produce una **puntuación global** en [-1, +1] (voto ponderado por
confianza y peso). Umbrales configurables deciden BUY/SELL/WAIT. El `RiskManager`
tiene poder de **veto** (p. ej. noticias de alto impacto inminentes, riesgo diario
excedido) y calcula el tamaño de posición.

## 6. Régimen de mercado

Un `MarketRegime` (tendencia + volatilidad) se calcula una sola vez por ciclo y se
pasa como contexto. Permite: (a) pesos condicionados al régimen, y (b) que cada
agente adapte su sensibilidad. Es la pieza que hace que "cada agente funcione
mejor en cada condición".

## 7. Flujo de un ciclo de decisión

1. `DataFeed` entrega `MarketData` multi-timeframe (M5, M15, H1, H4, D1).
2. Se calcula el `MarketRegime`.
3. El Supervisor ejecuta todos los agentes (`ThreadPool`, con timeout y
   aislamiento de fallos: un agente que lanza excepción devuelve WAIT y no tumba
   el sistema).
4. `WeightingStrategy` asigna pesos según agente + régimen + desempeño.
5. `ConflictDetector` marca desacuerdos fuertes (baja convicción del conjunto).
6. Agregación → `SupervisorDecision` (señal, score, SL/TP consolidado, riesgo).
7. `RiskManager` valida/veta y dimensiona la posición.
8. `ExecutionBroker` ejecuta (paper o MT5).
9. Persistencia + logging → Dashboard.

## 8. Calidad y operación

- **Logging** estructurado (JSON opcional) con `trading_system.utils.logger`.
- **Tests** con `pytest` (unitarios de indicadores, agentes, supervisor, riesgo).
- **Config** por YAML (`config/config.yaml`) — sin números mágicos en el código.
- **Backtesting**: el mismo `Supervisor` corre sobre `PaperBroker` con datos
  históricos → evaluación reproducible.
- **Seguridad**: las credenciales de MT5/MySQL van por variables de entorno,
  nunca en el repo.

## 9. Componentes de integración

- **Pine Script v6** (`integrations/pine/`): indicadores que replican la lógica
  de agentes clave para visualización en TradingView y validación visual.
- **Dashboard PHP + MySQL** (`integrations/dashboard/`): esquema de BD para
  persistir decisiones/operaciones y un panel para monitoreo en vivo.

Ver `AGENTES.md` (catálogo completo de agentes) y `ROADMAP.md` (plan por fases).
