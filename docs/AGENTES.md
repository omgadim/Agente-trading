# Catálogo de Agentes

Cada agente es una clase que hereda de `BaseAgent`, se registra con
`@register_agent("nombre")` y devuelve un `AgentDecision`. Se agrupan por
**categoría** para que el Supervisor pueda ponderar por familia y evitar
sobre-representar una misma tesis.

Leyenda de estado: ✅ implementado (Fase 1) · 🚧 scaffold (WAIT + TODO) · 🧠 requiere modelo/datos externos.

## Categoría: Estructura y Price Action (Smart Money)

| # | Agente | Estado | Idea central |
|---|--------|--------|--------------|
| 1 | `MarketStructureAgent` | ✅ | HH/HL vs LH/LL → BOS/CHoCH |
| 2 | `SmartMoneyConceptsAgent` | ✅ | Premium/Discount + estructura (BOS/CHoCH) |
| 3 | `OrderBlocksAgent` | ✅ | Última vela contraria antes de impulso (retest) |
| 4 | `FairValueGapAgent` | ✅ | Desequilibrios de 3 velas (mitigación de FVG) |
| 5 | `LiquiditySweepAgent` | ✅ | Barridos de liquidez (stop hunts) sobre highs/lows |
| 6 | `WyckoffAgent` | ✅ | Springs (acumulación) / upthrusts (distribución) |
| 7 | `ElliottWaveAgent` | 🚧🧠 | Conteo de ondas impulsivas/correctivas |
| 8 | `SupportResistanceAgent` | ✅ | Zonas de swing y reacción del precio |
| 9 | `HarmonicPatternAgent` | ✅ | Gartley/Bat/Butterfly/Crab (ratios de Fibonacci) |
| 10 | `CandlestickPatternAgent` | ✅ | Engulfing, pin bar, doji, etc. |

## Categoría: Tendencia y Momentum

| # | Agente | Estado | Idea central |
|---|--------|--------|--------------|
| 11 | `TrendMultiTimeframeAgent` | ✅ | Alineación de EMAs en M15/H1/H4/D1 |
| 12 | `MomentumAgent` | ✅ | ROC / fuerza direccional reciente |
| 13 | `TechnicalIndicatorAgent` | ✅ | Composite RSI + MACD + ADX + EMA |

## Categoría: Volatilidad y Volumen

| # | Agente | Estado | Idea central |
|---|--------|--------|--------------|
| 14 | `VolatilityAgent` | ✅ | Régimen de ATR (expansión/contracción) |
| 15 | `VolumeAgent` | ✅ | Confirmación por volumen (o tick volume) |

## Categoría: Contexto y Fundamentales

| # | Agente | Estado | Idea central |
|---|--------|--------|--------------|
| 16 | `CorrelationAgent` | 🚧🧠 | DXY, US10Y, SPX vs XAUUSD |
| 17 | `NewsAgent` | 🚧🧠 | Calendario económico de alto impacto (veto/timing) |
| 18 | `SessionAgent` (extra) | ✅ | Sesión Asia/Londres/NY, killzones |

## Categoría: Inteligencia y Gestión

| # | Agente | Estado | Idea central |
|---|--------|--------|--------------|
| 19 | `MachineLearningAgent` | 🚧🧠 | LSTM / XGBoost sobre features de mercado |
| 20 | `RiskManagementAgent` | ✅ | Riesgo, SL/TP por ATR, poder de veto |
| 21 | `OpenTradesControlAgent` | ✅ | Gestión de posiciones abiertas (trailing, break-even) |

## Agentes adicionales propuestos (justificación)

Más allá de los 20 pedidos, recomendamos:

- **`SessionAgent` (#18)** — el Oro tiene comportamiento muy distinto por sesión;
  filtrar por *killzones* de Londres/NY mejora la calidad de entradas.
- **`OpenTradesControlAgent` (#21)** — separar la *gestión* de la operación viva
  (trailing stop, break-even, cierre parcial) de la *apertura* reduce drawdown.
- **`RegimeAgent` (futuro)** — clasificar explícitamente tendencia/rango como
  agente dedicado, para alimentar la ponderación del Supervisor.
- **`SentimentAgent` (futuro)** — posicionamiento retail (COT / sentiment feeds)
  como señal contraria.
- **`ExecutionQualityAgent` (futuro)** — monitorea slippage/spread y desaconseja
  operar en condiciones de baja liquidez.

## Cómo añadir un agente nuevo

```python
from trading_system.core import BaseAgent, AgentDecision, SignalType, register_agent

@register_agent("mi_agente")
class MiAgente(BaseAgent):
    category = "momentum"

    def analyze(self, md):
        # ... tu lógica ...
        return self._decision(SignalType.BUY, confidence=72,
                              explanation="Motivo", estimated_risk=30)
```

Registrarlo en `config/config.yaml` bajo `agents:` y listo. El Supervisor lo
descubre y lo pondera automáticamente.
