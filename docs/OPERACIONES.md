# Runbook operativo

Guía de operación, despliegue y respuesta a incidentes del sistema. Complementa
`ARQUITECTURA.md` (diseño) y `ROADMAP.md` (fases).

## 1. Entornos y modos

| Modo | Broker/feed | Uso |
|------|-------------|-----|
| **Backtest** | serie histórica (CSV/simulada) | investigación, validación walk-forward |
| **Paper** | `SimulatedMT5Client` | ensayo del pipeline live sin riesgo (cualquier SO) |
| **Live** | `RealMT5Client` (Windows + terminal MT5) | operativa real (empezar SIEMPRE en cuenta demo) |

### Comportamiento del motor en vivo

- **Solo velas cerradas.** El feed (`MT5DataFeed`, `closed_bars_only: true`)
  descarta la última vela de cada marco, que en MT5 está aún en formación. Así
  los indicadores no "repintan" dentro de la vela y las señales son estables. El
  precio de **ejecución** sigue siendo el tick en vivo (BUY al ask, SELL al bid).
  Ponlo en `false` en `config.yaml` (`mt5.closed_bars_only`) solo si quieres el
  comportamiento intradía sobre la vela en curso.
- **Aprendizaje adaptativo en vivo.** Al cerrarse cada operación, el `LiveTrader`
  alimenta la ponderación del Supervisor con el resultado real
  (`supervisor.learn`), de modo que cada agente gana o pierde peso según acierte
  en cada régimen (no solo en el backtest).
- **Persistencia del aprendizaje.** Con persistencia activa, los pesos aprendidos
  se guardan en la tabla `weight_state` tras cada cierre y se restauran al
  arrancar: el aprendizaje sobrevive a los reinicios del runner. Sin base de
  datos, el aprendizaje ocurre en memoria (no persiste), sin romper la operativa.
- **Ficha de decisión.** Antes de cada apertura, el `LiveTrader` registra una
  ficha legible con el voto y la confianza de cada agente, el score, el riesgo y
  el SL/TP, y el motivo. Se ve en el log y, con `live.cards_path` (por defecto
  `logs/decisiones.log`), se anexa a un archivo para auditar cada operación:
  saber en quién se apoyó y con qué convicción, y detectar agentes de baja
  calidad con el tiempo.

## 2. Variables de entorno (nunca en el repo)

```
# MetaTrader 5 (modo live)
MT5_LOGIN=...      MT5_PASSWORD=...      MT5_SERVER=...
# MySQL (dashboard / persistencia)
DB_HOST=...  DB_PORT=3306  DB_NAME=trading_system  DB_USER=...  DB_PASSWORD=...
# Alertas (opcional)
TELEGRAM_TOKEN=...  TELEGRAM_CHAT_ID=...
SMTP_HOST=...  SMTP_PORT=587  SMTP_USER=...  SMTP_PASSWORD=...  ALERT_TO=...
# Flujo de noticias (opcional, agente news_flow) — TheNewsAPI
NEWS_API_TOKEN=...
```

Ver `.env.example`. Cargar con el gestor de secretos del entorno; no versionar `.env`.

## 3. Despliegue

### Local (SQLite, sin servidor)
```bash
pip install -r requirements.txt
PYTHONPATH=src python -m examples.run_persistence_demo   # puebla data/trading.db
```

### Runner de producción (`examples/run_live.py`)
Ensambla todo desde `config.yaml` (`trading_system.runtime.build_live_trader`):
feed+broker MT5, supervisor, riesgo, guardián, kill switch, alertas y persistencia.

```bash
# Paper (cualquier SO): prueba el cableado y el bucle completo
PYTHONPATH=src python -m examples.run_live --mode paper --max-steps 200 --relax-guard

# Live en cuenta DEMO (Windows con terminal MT5):
#   1) pip install MetaTrader5 pymysql
#   2) export MT5_LOGIN=... MT5_PASSWORD=... MT5_SERVER=...
#   3) en config.yaml: mt5.enabled y persistence.enabled/alerts.enabled según se quiera
PYTHONPATH=src python -m examples.run_live --mode live --interval 60
```
El mismo código sirve para paper y live; solo cambia `--mode` y las credenciales
del entorno. Parada limpia con Ctrl-C (o el flag manual del kill switch).

### Docker (MySQL + dashboard + motor)
```bash
docker compose up -d db dashboard   # BD + panel en http://localhost:8080
docker compose run --rm engine      # ejecuta el motor (backtest por defecto)
```
El esquema MySQL se crea automáticamente desde `integrations/dashboard/sql/schema.sql`.

### Monitor sin Docker (SQLite → HTML)
En un VPS sin Docker/MySQL (p. ej. Forex VPS con SQLite) el panel PHP no aplica.
El monitor lee la persistencia (`data/trading.db`) y genera un `dashboard.html`
autocontenido que se abre en el navegador y se auto-refresca:
```bash
# Regenera dashboard.html cada 30 s y lo abre en el navegador:
python -m examples.run_monitor --open
# Un vistazo puntual (genera una vez y termina):
python -m examples.run_monitor --once
```
Muestra los mismos KPIs que el panel PHP (operaciones, winrate, PnL, desempeño
por agente/régimen, últimas decisiones y operaciones). Corre en paralelo al
runner en vivo; SQLite admite lector + escritor a la vez.

## 4. Controles de riesgo (defensa en profundidad)

1. **RiskManager** — dimensiona por ATR y veta por pérdida diaria (por operación).
2. **MarketGuard** — bloquea por spread alto, horario y fin de semana.
3. **Agentes de veto** — `risk_management` (volatilidad extrema) y `news` (blackout).
4. **KillSwitch** — corta TODA nueva entrada ante:
   - pérdida diaria máxima (`max_daily_loss`),
   - drawdown máximo (`max_drawdown`),
   - rachas de pérdidas (`max_consecutive_losses`),
   - **flag manual**: crear el fichero indicado en `flag_file`.

### Parada de emergencia (kill switch manual)
```bash
touch /ruta/al/STOP     # el LiveTrader deja de abrir; las abiertas siguen gestionadas
```
Para reanudar: borrar el fichero y `KillSwitch.reset()` (o reiniciar el runner).

## 5. Alertas

Configurar un `Notifier` (Telegram/Email/Composite) e inyectarlo en el
`LiveTrader`. Se notifica: apertura, cierre (con PnL) y **parada del kill switch**.
Un canal caído nunca detiene la operativa (se aísla y se registra en el log).

## 6. Monitorización

- **Dashboard** (`:8080`): KPIs de PnL, desempeño por agente/régimen, últimas
  decisiones y operaciones. Auto-refresco 30 s.
- **Logs**: `trading_system.utils.setup_logging`. En producción, nivel INFO y
  envío a un agregador (stdout → Docker/systemd → ELK/Loki).
- **Salud**: revisar que llegan decisiones nuevas cada ciclo y que no hay trades
  atascados en `OPEN` sin correlato en el broker.

## 7. Respuesta a incidentes

| Síntoma | Acción |
|---------|--------|
| Kill switch disparado | Revisar motivo en el log/alerta; analizar operaciones del día; `reset()` solo tras entender la causa |
| Sin conexión a MT5 | `RealMT5Client.connect()` reintenta con backoff; si persiste, parar (flag manual) y revisar terminal/credenciales |
| Spread anómalo permanente | El `MarketGuard` bloquea; verificar sesión/broker; no forzar |
| BD caída | El motor sigue operando; la persistencia es best-effort. Restaurar MySQL y revisar continuidad |
| Divergencia posiciones motor↔broker | Fuente de verdad = broker. Conciliar con `poll_closed_deals`; en duda, cerrar manualmente en MT5 |

## 8. Checklist previo a operar en real

- [ ] Validado en **cuenta demo** ≥ 2 semanas con el mismo config.
- [ ] `KillSwitch` configurado (pérdida diaria, drawdown, rachas, flag).
- [ ] Alertas probadas (mensaje de test recibido).
- [ ] Backtest walk-forward reproducible sobre datos reales, no solo simulados.
- [ ] Límites de riesgo revisados (`risk_per_trade_pct`, `max_daily_loss_pct`).
- [ ] Procedimiento de parada de emergencia conocido por el operador.

> **Aviso**: software experimental. El trading apalancado puede acarrear pérdidas
> superiores al capital. Nada aquí es asesoramiento financiero.
