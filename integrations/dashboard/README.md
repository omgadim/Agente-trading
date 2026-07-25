# Dashboard PHP + MySQL (Fase 6 — andamiaje)

Panel de monitoreo del sistema: decisiones del Supervisor, aportes por agente y
operaciones. Este es el andamiaje inicial; la fase 6 añade gráficos de desempeño
por agente y estado en vivo.

## Puesta en marcha

```bash
# 1) Crear el esquema
mysql -u root -p < sql/schema.sql

# 2) Configurar credenciales (variables de entorno)
export DB_HOST=localhost DB_NAME=trading_system DB_USER=usuario DB_PASSWORD=secreto

# 3) Servir el panel
php -S localhost:8000 -t public
# abrir http://localhost:8000
```

## Integración con el motor Python

El motor Python persistirá cada `SupervisorDecision` en `supervisor_decisions`,
cada aporte en `agent_decisions` y cada operación en `trades` (capa de
persistencia a implementar en la Fase 6). El panel solo lee esas tablas.

## Seguridad

- Credenciales **solo** por variables de entorno (ver `.env.example`).
- Consultas con PDO y sentencias preparadas.
- No exponer este panel a Internet sin autenticación y HTTPS.
