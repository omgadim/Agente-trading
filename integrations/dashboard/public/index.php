<?php
// Dashboard (Fase 6): KPIs de PnL, decisiones del Supervisor, operaciones y
// desempeño por agente/régimen. Lee las tablas que escribe el motor Python
// (SqliteRepository en local, MySQLRepository en producción).
declare(strict_types=1);
require __DIR__ . '/db.php';

$error = null;
$decisions = $trades = $performance = [];
$kpi = ['trades' => 0, 'wins' => 0, 'net_pnl' => 0.0, 'winrate' => 0.0];

try {
    $pdo = db();
    $decisions = $pdo->query(
        "SELECT * FROM supervisor_decisions ORDER BY id DESC LIMIT 20"
    )->fetchAll();
    $trades = $pdo->query(
        "SELECT * FROM trades ORDER BY id DESC LIMIT 20"
    )->fetchAll();
    $performance = $pdo->query(
        "SELECT * FROM agent_performance ORDER BY hit_rate DESC, hits DESC LIMIT 30"
    )->fetchAll();
    $row = $pdo->query(
        "SELECT COUNT(*) trades, SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) wins,
                COALESCE(SUM(pnl),0) net_pnl
         FROM trades WHERE status='CLOSED'"
    )->fetch();
    if ($row) {
        $kpi['trades'] = (int)$row['trades'];
        $kpi['wins'] = (int)$row['wins'];
        $kpi['net_pnl'] = (float)$row['net_pnl'];
        $kpi['winrate'] = $kpi['trades'] ? round($kpi['wins'] / $kpi['trades'] * 100, 1) : 0.0;
    }
} catch (Throwable $e) {
    $error = $e->getMessage();
}

function h($s): string { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
function badge(string $signal): string {
    $c = $signal === 'BUY' ? '#16a34a' : ($signal === 'SELL' ? '#dc2626' : '#6b7280');
    return "<span style=\"background:$c;color:#fff;padding:2px 8px;border-radius:4px;font-size:12px\">" . h($signal) . "</span>";
}
function pnl_color(float $v): string { return $v > 0 ? '#16a34a' : ($v < 0 ? '#dc2626' : '#94a3b8'); }
?>
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30"><!-- auto-refresco cada 30s -->
  <title>Dashboard — Sistema Multiagente XAUUSD</title>
  <style>
    body { font-family: system-ui, sans-serif; margin:0; background:#0f172a; color:#e2e8f0; }
    header { padding:16px 24px; background:#1e293b; border-bottom:1px solid #334155;
             display:flex; justify-content:space-between; align-items:center; }
    h1 { margin:0; font-size:18px; } h2 { font-size:15px; color:#94a3b8; margin-top:28px; }
    .wrap { padding:24px; max-width:1150px; margin:0 auto; }
    .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:16px; }
    .card { background:#1e293b; border:1px solid #334155; border-radius:10px; padding:16px; }
    .card .label { color:#94a3b8; font-size:12px; text-transform:uppercase; letter-spacing:.5px; }
    .card .value { font-size:26px; font-weight:700; margin-top:6px; }
    table { width:100%; border-collapse:collapse; margin-bottom:8px; background:#1e293b;
            border-radius:10px; overflow:hidden; }
    th, td { padding:8px 10px; text-align:left; border-bottom:1px solid #334155; font-size:13px; }
    th { color:#94a3b8; text-transform:uppercase; font-size:11px; letter-spacing:.5px; }
    .err { background:#7f1d1d; padding:12px; border-radius:6px; }
    .bar { height:8px; background:#334155; border-radius:4px; overflow:hidden; min-width:80px; }
    .bar > span { display:block; height:100%; background:#38bdf8; }
    .muted { color:#64748b; font-size:12px; }
  </style>
</head>
<body>
  <header>
    <h1>🥇 Sistema de Trading Multiagente — XAUUSD</h1>
    <span class="muted">Auto-refresco 30s · <?= date('Y-m-d H:i:s') ?> UTC</span>
  </header>
  <div class="wrap">
    <?php if ($error): ?>
      <p class="err">No se pudo conectar a la base de datos: <?= h($error) ?><br>
      Ejecuta <code>sql/schema.sql</code> y configura las variables DB_* del entorno.</p>
    <?php endif; ?>

    <div class="kpis">
      <div class="card"><div class="label">Operaciones</div><div class="value"><?= $kpi['trades'] ?></div></div>
      <div class="card"><div class="label">Winrate</div><div class="value"><?= $kpi['winrate'] ?>%</div></div>
      <div class="card"><div class="label">PnL neto</div>
        <div class="value" style="color:<?= pnl_color($kpi['net_pnl']) ?>"><?= number_format($kpi['net_pnl'], 2) ?></div></div>
      <div class="card"><div class="label">Ganadoras</div><div class="value"><?= $kpi['wins'] ?>/<?= $kpi['trades'] ?></div></div>
    </div>

    <h2>Desempeño por agente y régimen</h2>
    <table>
      <tr><th>Agente</th><th>Régimen</th><th>Aciertos</th><th>Fallos</th><th>Hit-rate</th></tr>
      <?php foreach ($performance as $p): $rate = (float)$p['hit_rate']; ?>
        <tr>
          <td><?= h($p['agent_name']) ?></td>
          <td><?= h($p['regime']) ?></td>
          <td><?= h($p['hits']) ?></td>
          <td><?= h($p['misses']) ?></td>
          <td>
            <div style="display:flex;align-items:center;gap:8px">
              <div class="bar"><span style="width:<?= round($rate * 100) ?>%"></span></div>
              <span><?= round($rate * 100) ?>%</span>
            </div>
          </td>
        </tr>
      <?php endforeach; ?>
      <?php if (!$performance): ?><tr><td colspan="5" class="muted">Sin datos todavía.</td></tr><?php endif; ?>
    </table>

    <h2>Últimas decisiones del Supervisor</h2>
    <table>
      <tr><th>Fecha</th><th>Señal</th><th>Conf.</th><th>Score</th><th>Riesgo</th><th>Régimen</th><th>Motivo</th></tr>
      <?php foreach ($decisions as $d): ?>
        <tr>
          <td><?= h($d['created_at']) ?></td>
          <td><?= badge((string)$d['signal_type']) ?></td>
          <td><?= h($d['confidence']) ?></td>
          <td><?= h($d['score']) ?></td>
          <td><?= h($d['estimated_risk']) ?></td>
          <td><?= h($d['regime']) ?></td>
          <td><?= h($d['explanation']) ?></td>
        </tr>
      <?php endforeach; ?>
      <?php if (!$decisions): ?><tr><td colspan="7" class="muted">Sin datos todavía.</td></tr><?php endif; ?>
    </table>

    <h2>Operaciones</h2>
    <table>
      <tr><th>Apertura</th><th>Símbolo</th><th>Dir.</th><th>Vol.</th><th>Entrada</th><th>Salida</th><th>PnL</th><th>Estado</th></tr>
      <?php foreach ($trades as $t): $pnl = (float)$t['pnl']; ?>
        <tr>
          <td><?= h($t['opened_at']) ?></td>
          <td><?= h($t['symbol']) ?></td>
          <td><?= badge((string)$t['direction']) ?></td>
          <td><?= h($t['volume']) ?></td>
          <td><?= h($t['entry_price']) ?></td>
          <td><?= h($t['exit_price']) ?></td>
          <td style="color:<?= pnl_color($pnl) ?>"><?= $t['pnl'] !== null ? number_format($pnl, 2) : '—' ?></td>
          <td><?= h($t['status']) ?></td>
        </tr>
      <?php endforeach; ?>
      <?php if (!$trades): ?><tr><td colspan="8" class="muted">Sin operaciones todavía.</td></tr><?php endif; ?>
    </table>
  </div>
</body>
</html>
