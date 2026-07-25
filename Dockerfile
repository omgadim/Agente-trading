# Imagen del sistema de trading (motor Python).
# Nota: el modo live real con MetaTrader5 requiere Windows; este contenedor sirve
# para backtesting, ML, persistencia y el modo paper (cliente MT5 simulado).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Dependencias primero (mejor cacheo de capas).
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# Código y configuración.
COPY src/ ./src/
COPY config/ ./config/
COPY examples/ ./examples/

# Usuario no-root.
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# Por defecto, ejecuta el demo de backtesting. Sustituir por el runner real.
CMD ["python", "-m", "examples.run_backtest"]
