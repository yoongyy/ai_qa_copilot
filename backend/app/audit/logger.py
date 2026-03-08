from __future__ import annotations

import json
from datetime import datetime, timezone

from ..db import get_conn


def log_ai_operation(
  operation: str,
  prompt_version: str,
  retrieved_sources,
  model: str,
  cost_estimate: float,
  output,
) -> None:
  conn = get_conn()
  try:
    conn.execute(
      """
      INSERT INTO ai_audit_logs
      (timestamp, operation, prompt_version, retrieved_sources, model, cost_estimate, output)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      """,
      (
        datetime.now(timezone.utc).isoformat(),
        operation,
        prompt_version,
        json.dumps(retrieved_sources, ensure_ascii=True),
        model,
        cost_estimate,
        json.dumps(output, ensure_ascii=True),
      ),
    )
    conn.commit()
  finally:
    conn.close()
