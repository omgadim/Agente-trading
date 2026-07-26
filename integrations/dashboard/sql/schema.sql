-- Esquema MySQL del Dashboard (Fase 6)
-- Persiste decisiones del supervisor, aportes de agentes y operaciones.
CREATE DATABASE IF NOT EXISTS trading_system
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE trading_system;

-- Decisión agregada del Supervisor por ciclo.
CREATE TABLE IF NOT EXISTS supervisor_decisions (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  symbol        VARCHAR(20)  NOT NULL,
  signal_type   ENUM('BUY','SELL','WAIT') NOT NULL,
  confidence    DECIMAL(5,2) NOT NULL,
  score         DECIMAL(6,4) NOT NULL,
  estimated_risk DECIMAL(5,2) NOT NULL,
  stop_loss     DECIMAL(12,4) NULL,
  take_profit   DECIMAL(12,4) NULL,
  position_size DECIMAL(10,2) NULL,
  conflict      TINYINT(1) NOT NULL DEFAULT 0,
  vetoed        TINYINT(1) NOT NULL DEFAULT 0,
  veto_reason   VARCHAR(255) NULL,
  explanation   TEXT NULL,
  regime        VARCHAR(40) NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_symbol_time (symbol, created_at),
  INDEX idx_signal (signal_type)
) ENGINE=InnoDB;

-- Aporte individual de cada agente a una decisión.
CREATE TABLE IF NOT EXISTS agent_decisions (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  decision_id   BIGINT UNSIGNED NOT NULL,
  agent_name    VARCHAR(50) NOT NULL,
  signal_type   ENUM('BUY','SELL','WAIT') NOT NULL,
  confidence    DECIMAL(5,2) NOT NULL,
  weight        DECIMAL(6,4) NOT NULL DEFAULT 1,
  estimated_risk DECIMAL(5,2) NOT NULL,
  explanation   VARCHAR(500) NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_agent_decision FOREIGN KEY (decision_id)
    REFERENCES supervisor_decisions(id) ON DELETE CASCADE,
  INDEX idx_agent (agent_name)
) ENGINE=InnoDB;

-- Operaciones ejecutadas (paper o live).
CREATE TABLE IF NOT EXISTS trades (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  decision_id   BIGINT UNSIGNED NULL,
  ticket        BIGINT NULL,
  symbol        VARCHAR(20) NOT NULL,
  direction     ENUM('BUY','SELL') NOT NULL,
  volume        DECIMAL(10,2) NOT NULL,
  entry_price   DECIMAL(12,4) NOT NULL,
  stop_loss     DECIMAL(12,4) NULL,
  take_profit   DECIMAL(12,4) NULL,
  exit_price    DECIMAL(12,4) NULL,
  pnl           DECIMAL(14,2) NULL,
  status        ENUM('OPEN','CLOSED') NOT NULL DEFAULT 'OPEN',
  opened_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  closed_at     DATETIME NULL,
  CONSTRAINT fk_trade_decision FOREIGN KEY (decision_id)
    REFERENCES supervisor_decisions(id) ON DELETE SET NULL,
  INDEX idx_status (status),
  INDEX idx_symbol_time (symbol, opened_at)
) ENGINE=InnoDB;

-- Desempeño acumulado por agente y régimen (para la ponderación adaptativa).
CREATE TABLE IF NOT EXISTS agent_performance (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  agent_name    VARCHAR(50) NOT NULL,
  regime        VARCHAR(40) NOT NULL,
  hits          INT NOT NULL DEFAULT 0,
  misses        INT NOT NULL DEFAULT 0,
  hit_rate      DECIMAL(5,4) NOT NULL DEFAULT 0.5,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_agent_regime (agent_name, regime)
) ENGINE=InnoDB;

-- Estado serializado (JSON) de la ponderación del Supervisor, para que el
-- aprendizaje online sobreviva a los reinicios del runner.
CREATE TABLE IF NOT EXISTS weight_state (
  name          VARCHAR(50) NOT NULL,
  state         TEXT NOT NULL,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_name (name)
) ENGINE=InnoDB;
