# Validación sobre datos reales (XAUUSD)

Registro honesto de cómo se validó el sistema sobre mercado real, con
metodología reproducible y resultados **netos de costes**. La conclusión no es
"esto es rentable garantizado" sino "el edge sobrevive a una validación seria y
merece pasar a cuenta demo".

## Datos

- XAUUSD, export MetaTrader 5 (`Date,Open,High,Low,Close,Volume,Spread,Tick_Volume`).
- `Volume` real = 0 (CFD); se usa `Tick_Volume` (ver `data/loader.py`).
- M30, 55.606 velas, **2021-11 → 2026-07 (~4,7 años)**. Los ficheros (`data/`) no
  se versionan (privados del usuario).

## Metodología: rolling walk-forward

`examples/run_walkforward.py`. En vez de un único split (que puede ser
afortunado), se deslizan 5 ventanas train→test por toda la serie:

- train = 16.000 velas (~1,3 años), test = 7.000 (~7 meses), avance = test.
- En cada fold se busca el multiplicador de **Stop Loss** (× ATR) que maximiza el
  profit factor **en train**, y se evalúa esa política en el **test siguiente**
  (out-of-sample, nunca visto).
- Se agregan TODOS los trades OOS de la política fija candidata (SL=1,0 / TP=2,5).
- Sin look-ahead: features/labels de ML y aprendizaje online usan solo el pasado.
- ML desactivado en la validación (coste computacional); es el edge de los agentes
  de reglas.

## Costes de transacción

`Backtester` descuenta por operación (round-turn): spread entero + 2× slippage +
comisión/lote (`config: costs`). Validación con **spread 0,30 + slippage 0,02/lado**
(conservador para Oro retail).

## Resultados (5 folds, 2023 → 2026)

| Fold | Test desde | SL elegido | PF bruto | **PF neto** | Trades |
|------|-----------|-----------|---------|------------|--------|
| 1 | 2023-03 | 1,0 | 0,79 | **0,69** ❌ | 75 |
| 2 | 2023-10 | 1,0 | 2,56 | **2,32** ✅ | 69 |
| 3 | 2024-05 | 1,0 | 1,98 | **1,83** ✅ | 71 |
| 4 | 2024-12 | 1,0 | 2,35 | **2,23** ✅ | 62 |
| 5 | 2025-07 | 1,0 | 3,16 | **3,06** ✅ | 78 |

**Agregado out-of-sample, NETO de costes** (355 trades):

| Métrica | Bruto | **Neto** |
|---------|-------|---------|
| Profit Factor | 2,00 | **1,85** |
| Winrate | 44,8% | 44,8% |
| Expectancy / trade | 55,6 | **49,9** |
| PnL neto | 19.740 | **17.695** |
| Max Drawdown | 2.141 | **2.700** |

## Lectura

- **SL=1,0 se eligió en train en los 5 folds** → parámetro estable, no ajustado
  al tramo. Confirma el default adoptado (`helpers.atr_sl_tp`).
- **4 de 5 folds rentables OOS**, en regímenes distintos; agregado **PF 1,85 neto**.
  El edge **sobrevive a los costes** (caían ~$5,8/trade, ~10% del bruto).
- Es **robusto**, no un split afortunado: la evidencia abarca ~4,7 años.

## Lo que esto NO afirma (honestidad)

- **Un fold pierde** (arranque 2023, PF 0,69 neto). Hay periodos adversos reales.
- **Un solo broker y un solo activo.** Otro feed con spreads más anchos erosiona
  más; conviene rehacerlo con los costes reales del broker objetivo.
- **ML desactivado** en la validación; el sistema completo puede diferir.
- **Drawdown de 2.700** sobre ~17.700 de beneficio: real y hay que tolerarlo.
- Cifras dependientes del **sizing** (1% de riesgo) y sin compounding modelado.

## Siguiente paso recomendado

Validar en **cuenta demo** de MT5 (`RealMT5Client`) con los **costes reales del
broker**, kill switch y alertas activos (ver `docs/OPERACIONES.md`), durante
varias semanas, antes de cualquier capital real.
