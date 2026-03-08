from __future__ import annotations

import sqlite3
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / 'data' / 'app.db'


def get_conn() -> sqlite3.Connection:
  DB_PATH.parent.mkdir(parents=True, exist_ok=True)
  conn = sqlite3.connect(DB_PATH, check_same_thread=False)
  conn.row_factory = sqlite3.Row
  return conn


def init_db() -> None:
  conn = get_conn()
  try:
    conn.executescript(
      """
      CREATE TABLE IF NOT EXISTS nominations (
        id TEXT PRIMARY KEY,
        vessel_name TEXT NOT NULL,
        port TEXT NOT NULL,
        eta TEXT NOT NULL,
        readiness_time TEXT,
        scheduled_eta TEXT,
        jetty TEXT,
        cq_id TEXT,
        created_at TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS cqs (
        id TEXT PRIMARY KEY,
        nomination_id TEXT NOT NULL,
        status TEXT NOT NULL,
        signed_by TEXT,
        signed_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (nomination_id) REFERENCES nominations(id)
      );

      CREATE TABLE IF NOT EXISTS calendar_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nomination_id TEXT NOT NULL,
        title TEXT NOT NULL,
        start_time TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (nomination_id) REFERENCES nominations(id)
      );

      CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nomination_id TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (nomination_id) REFERENCES nominations(id)
      );

      CREATE TABLE IF NOT EXISTS ai_audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        operation TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        retrieved_sources TEXT NOT NULL,
        model TEXT NOT NULL,
        cost_estimate REAL NOT NULL,
        output TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS test_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        endpoint_method TEXT NOT NULL,
        endpoint_path TEXT NOT NULL,
        runner TEXT NOT NULL,
        script TEXT NOT NULL,
        assertions TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS test_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL,
        trigger_type TEXT NOT NULL,
        status TEXT NOT NULL,
        return_code INTEGER NOT NULL,
        log TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        FOREIGN KEY (case_id) REFERENCES test_cases(id)
      );

      CREATE TABLE IF NOT EXISTS test_schedules (
        case_id INTEGER PRIMARY KEY,
        cron_expr TEXT NOT NULL,
        enabled INTEGER NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (case_id) REFERENCES test_cases(id)
      );
      """
    )
    conn.commit()
  finally:
    conn.close()
