"""Monitor sin servidor: genera un dashboard HTML estático desde la persistencia.

Alternativa al panel PHP para entornos SIN Docker/MySQL (p. ej. un VPS Forex con
SQLite). Lee las mismas tablas que escribe el motor y produce un `.html`
autocontenido que se abre en el navegador, con auto-refresco. La lógica de
recogida y render vive aquí (testeable); `examples/run_monitor.py` es el CLI.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Dict, List

# Tipo laxo para no acoplar al backend concreto (SQLite/MySQL).
Repository = Any


def collect_dashboard_data(repo: Repository) -> Dict[str, Any]:
    """Recoge KPIs, desempeño por agente, decisiones y operaciones recientes."""
    performance = sorted(
        repo.agent_performance(),
        key=lambda p: (float(p.get("hit_rate") or 0.0), int(p.get("hits") or 0)),
        reverse=True,
    )[:30]
    return {
        "kpi": repo.pnl_summary(),
        "performance": performance,
        "decisions": repo.recent_decisions(20),
        "trades": repo.recent_trades(20),
    }


def _h(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _badge(signal: str) -> str:
    color = {"BUY": "#16a34a", "SELL": "#dc2626"}.get(signal, "#6b7280")
    return (f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:4px;font-size:12px">{_h(signal)}</span>')


def _pnl_color(value: float) -> str:
    return "#16a34a" if value > 0 else ("#dc2626" if value < 0 else "#94a3b8")


def _num(value: Any, decimals: int = 2) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return _h(value)


def render_dashboard_html(
    data: Dict[str, Any], refresh: int = 30, now: datetime | None = None, db_label: str = ""
) -> str:
    """Renderiza el dashboard completo como una página HTML autocontenida."""
    now = now or datetime.now(timezone.utc)
    kpi = data.get("kpi") or {}
    trades_n = int(kpi.get("trades") or 0)
    wins = int(kpi.get("wins") or 0)
    net_pnl = float(kpi.get("net_pnl") or 0.0)
    winrate = float(kpi.get("winrate") or 0.0)

    perf_rows = _render_performance(data.get("performance") or [])
    dec_rows = _render_decisions(data.get("decisions") or [])
    trade_rows = _render_trades(data.get("trades") or [])
    source = f" · {_h(db_label)}" if db_label else ""

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="{int(refresh)}">
  <title>Dashboard — Sistema Multiagente XAUUSD</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin:0; background:#0f172a; color:#e2e8f0; }}
    header {{ padding:16px 24px; background:#1e293b; border-bottom:1px solid #334155;
             display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }}
    h1 {{ margin:0; font-size:18px; }} h2 {{ font-size:15px; color:#94a3b8; margin-top:28px; }}
    .wrap {{ padding:24px; max-width:1150px; margin:0 auto; }}
    .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:16px; }}
    .card {{ background:#1e293b; border:1px solid #334155; border-radius:10px; padding:16px; }}
    .card .label {{ color:#94a3b8; font-size:12px; text-transform:uppercase; letter-spacing:.5px; }}
    .card .value {{ font-size:26px; font-weight:700; margin-top:6px; }}
    .tbl {{ overflow-x:auto; }}
    table {{ width:100%; border-collapse:collapse; margin-bottom:8px; background:#1e293b;
            border-radius:10px; overflow:hidden; min-width:560px; }}
    th, td {{ padding:8px 10px; text-align:left; border-bottom:1px solid #334155; font-size:13px; }}
    th {{ color:#94a3b8; text-transform:uppercase; font-size:11px; letter-spacing:.5px; }}
    .bar {{ height:8px; background:#334155; border-radius:4px; overflow:hidden; min-width:80px; }}
    .bar > span {{ display:block; height:100%; background:#38bdf8; }}
    .muted {{ color:#64748b; font-size:12px; }}
  </style>
</head>
<body>
  <header>
    <h1>🥇 Sistema de Trading Multiagente — XAUUSD</h1>
    <span class="muted">Auto-refresco {int(refresh)}s · {now:%Y-%m-%d %H:%M:%S} UTC{source}</span>
  </header>
  <div class="wrap">
    <div class="kpis">
      <div class="card"><div class="label">Operaciones</div><div class="value">{trades_n}</div></div>
      <div class="card"><div class="label">Winrate</div><div class="value">{winrate:.1f}%</div></div>
      <div class="card"><div class="label">PnL neto</div>
        <div class="value" style="color:{_pnl_color(net_pnl)}">{_num(net_pnl)}</div></div>
      <div class="card"><div class="label">Ganadoras</div><div class="value">{wins}/{trades_n}</div></div>
    </div>

    <h2>Desempeño por agente y régimen</h2>
    <div class="tbl"><table>
      <tr><th>Agente</th><th>Régimen</th><th>Aciertos</th><th>Fallos</th><th>Hit-rate</th></tr>
      {perf_rows}
    </table></div>

    <h2>Últimas decisiones del Supervisor</h2>
    <div class="tbl"><table>
      <tr><th>Fecha</th><th>Señal</th><th>Conf.</th><th>Score</th><th>Riesgo</th><th>Régimen</th><th>Motivo</th></tr>
      {dec_rows}
    </table></div>

    <h2>Operaciones</h2>
    <div class="tbl"><table>
      <tr><th>Apertura</th><th>Símbolo</th><th>Dir.</th><th>Vol.</th><th>Entrada</th><th>Salida</th><th>PnL</th><th>Estado</th></tr>
      {trade_rows}
    </table></div>
  </div>
</body>
</html>
"""


def _render_performance(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return '<tr><td colspan="5" class="muted">Sin datos todavía.</td></tr>'
    out = []
    for p in rows:
        pct = round(float(p.get("hit_rate") or 0.0) * 100)
        out.append(
            f"<tr><td>{_h(p.get('agent_name'))}</td><td>{_h(p.get('regime'))}</td>"
            f"<td>{_h(p.get('hits'))}</td><td>{_h(p.get('misses'))}</td>"
            f'<td><div style="display:flex;align-items:center;gap:8px">'
            f'<div class="bar"><span style="width:{pct}%"></span></div>'
            f"<span>{pct}%</span></div></td></tr>"
        )
    return "\n      ".join(out)


def _render_decisions(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return '<tr><td colspan="7" class="muted">Sin datos todavía.</td></tr>'
    out = []
    for d in rows:
        out.append(
            f"<tr><td>{_h(d.get('created_at'))}</td><td>{_badge(str(d.get('signal_type')))}</td>"
            f"<td>{_h(d.get('confidence'))}</td><td>{_h(d.get('score'))}</td>"
            f"<td>{_h(d.get('estimated_risk'))}</td><td>{_h(d.get('regime'))}</td>"
            f"<td>{_h(d.get('explanation'))}</td></tr>"
        )
    return "\n      ".join(out)


def _render_trades(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return '<tr><td colspan="8" class="muted">Sin operaciones todavía.</td></tr>'
    out = []
    for t in rows:
        pnl = t.get("pnl")
        pnl_html = "—" if pnl is None else (
            f'<span style="color:{_pnl_color(float(pnl))}">{_num(pnl)}</span>')
        out.append(
            f"<tr><td>{_h(t.get('opened_at'))}</td><td>{_h(t.get('symbol'))}</td>"
            f"<td>{_badge(str(t.get('direction')))}</td><td>{_h(t.get('volume'))}</td>"
            f"<td>{_num(t.get('entry_price'), 4)}</td><td>{_num(t.get('exit_price'), 4)}</td>"
            f"<td>{pnl_html}</td><td>{_h(t.get('status'))}</td></tr>"
        )
    return "\n      ".join(out)
