<?php
// Dashboard mínimo (Fase 6): últimas decisiones del supervisor y operaciones.
// Andamiaje funcional; se ampliará con gráficos de desempeño por agente.
declare(strict_types=1);
require __DIR__ . '/db.php';

$decisions = [];
$trades = [];
$error = null;
try {
    $decisions = db()->query(
        "SELECT * FROM supervisor_decisions ORDER BY created_at DESC LIMIT 20"
    )->fetchAll();
    $trades = db()->query(
        "SELECT * FROM trades ORDER BY opened_at DESC LIMIT 20"
    )->fetchAll();
} catch (Throwable $e) {
    $error = $e->getMessage();
}

function h(?string $s): string { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
function badge(string $signal): string {
    $color = $signal === 'BUY' ? '#16a34a' : ($signal === 'SELL' ? '#dc2626' : '#6b7280');
    return "<span style=\"background:$color;color:#fff;padding:2px 8px;border-radius:4px;font-size:12px\">" . h($signal) . "</span>";
}
?>
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dashboard — Sistema Multiagente XAUUSD</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background:#0f172a; color:#e2e8f0; }
    header { padding: 16px 24px; background:#1e293b; border-bottom:1px solid #334155; }
    h1 { margin:0; font-size:18px; } h2 { font-size:15px; color:#94a3b8; }
    .wrap { padding: 24px; max-width: 1100px; margin:0 auto; }
    table { width:100%; border-collapse: collapse; margin-bottom:32px; background:#1e293b; }
    th, td { padding:8px 10px; text-align:left; border-bottom:1px solid #334155; font-size:13px; }
    th { color:#94a3b8; text-transform:uppercase; font-size:11px; letter-spacing:.5px; }
    .err { background:#7f1d1d; padding:12px; border-radius:6px; }
  </style>
</head>
<body>
  <header><h1>🥇 Sistema de Trading Multiagente — XAUUSD</h1></header>
  <div class="wrap">
    <?php if ($error): ?>
      <p class="err">No se pudo conectar a la base de datos: <?= h($error) ?><br>
      Ejecuta <code>sql/schema.sql</code> y configura las variables DB_* del entorno.</p>
    <?php endif; ?>

    <h2>Últimas decisiones del Supervisor</h2>
    <table>
      <tr><th>Fecha</th><th>Señal</th><th>Conf.</th><th>Score</th><th>Riesgo</th><th>SL</th><th>TP</th><th>Motivo</th></tr>
      <?php foreach ($decisions as $d): ?>
        <tr>
          <td><?= h($d['created_at']) ?></td>
          <td><?= badge($d['signal_type']) ?></td>
          <td><?= h((string)$d['confidence']) ?></td>
          <td><?= h((string)$d['score']) ?></td>
          <td><?= h((string)$d['estimated_risk']) ?></td>
          <td><?= h((string)$d['stop_loss']) ?></td>
          <td><?= h((string)$d['take_profit']) ?></td>
          <td><?= h($d['explanation']) ?></td>
        </tr>
      <?php endforeach; ?>
      <?php if (!$decisions): ?><tr><td colspan="8">Sin datos todavía.</td></tr><?php endif; ?>
    </table>

    <h2>Operaciones</h2>
    <table>
      <tr><th>Apertura</th><th>Símbolo</th><th>Dir.</th><th>Vol.</th><th>Entrada</th><th>PnL</th><th>Estado</th></tr>
      <?php foreach ($trades as $t): ?>
        <tr>
          <td><?= h($t['opened_at']) ?></td>
          <td><?= h($t['symbol']) ?></td>
          <td><?= badge($t['direction']) ?></td>
          <td><?= h((string)$t['volume']) ?></td>
          <td><?= h((string)$t['entry_price']) ?></td>
          <td><?= h((string)$t['pnl']) ?></td>
          <td><?= h($t['status']) ?></td>
        </tr>
      <?php endforeach; ?>
      <?php if (!$trades): ?><tr><td colspan="7">Sin operaciones todavía.</td></tr><?php endif; ?>
    </table>
  </div>
</body>
</html>
