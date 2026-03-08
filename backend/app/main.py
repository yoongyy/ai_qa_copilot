from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Dict, List, Literal, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .ai import rag
from .ai.schemas import (
  ApplyFixRequest,
  ApplyFixResponse,
  GenerateTestsRequest,
  IndexDocRequest,
  IndexDocResponse,
  ProposeFixRequest,
  RunTestsResponse,
)
from .ai.service import AIService
from .db import get_conn, init_db
from .fix.patch_apply import apply_demo_patch
from .vc_api import router as vc_router

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / 'backend'

ai_service = AIService(PROJECT_ROOT)
scheduler = BackgroundScheduler(timezone='UTC')

ENDPOINT_CATALOG = [
  {
    'method': 'POST',
    'path': '/vc/nominations',
    'description': 'Create nomination',
  },
  {
    'method': 'PATCH',
    'path': '/vc/nominations/{id}/readiness',
    'description': 'Update readiness timestamp',
  },
  {
    'method': 'PATCH',
    'path': '/vc/nominations/{id}/schedule',
    'description': 'Update jetty + ETA and create calendar event',
  },
  {
    'method': 'POST',
    'path': '/vc/nominations/{id}/link-cq',
    'description': 'Link CQ/COQ reference',
  },
  {
    'method': 'POST',
    'path': '/vc/cq/{id}/sign',
    'description': 'Sign CQ document',
  },
  {
    'method': 'GET',
    'path': '/vc/nominations/{id}/messages',
    'description': 'Get secure message thread',
  },
  {
    'method': 'GET',
    'path': '/vc/nominations/{id}/calendar',
    'description': 'Get nomination calendar events',
  },
]

PAGE_CATALOG = [
  {
    'path': '/vessel-connect',
    'name': 'Vessel Connect Simulator',
    'description': 'Nomination and schedule UI workflow for browser automation',
  }
]


class AutoCreateCaseRequest(BaseModel):
  target_type: Literal['endpoint', 'page'] = 'endpoint'
  endpoint_method: Optional[str] = None
  endpoint_path: Optional[str] = None
  page_path: Optional[str] = None
  name: Optional[str] = None
  ai_prompt: Optional[str] = None
  schedule_mode: Literal['none', 'every_minute', 'daily', 'weekly', 'custom'] = 'none'
  schedule_cron_expr: Optional[str] = None
  runner: Literal['python_api', 'playwright_ui'] = 'python_api'
  context_doc_id: Optional[str] = None


class ScheduleRequest(BaseModel):
  mode: Literal['none', 'every_minute', 'daily', 'weekly', 'custom']
  cron_expr: Optional[str] = None


app = FastAPI(title='AI QA Copilot Backend', version='0.2.0')

app.add_middleware(
  CORSMiddleware,
  allow_origins=['*'],
  allow_credentials=True,
  allow_methods=['*'],
  allow_headers=['*'],
)

app.include_router(vc_router)


def utc_now() -> str:
  return datetime.now(timezone.utc).isoformat()


def _run_command(cmd: List[str], cwd: Path, timeout_seconds: int = 120, env: dict | None = None) -> dict:
  try:
    proc = subprocess.run(
      cmd,
      cwd=str(cwd),
      env=env,
      capture_output=True,
      text=True,
      timeout=timeout_seconds,
      check=False,
    )
    combined = (proc.stdout or '') + ('\n' + proc.stderr if proc.stderr else '')
    return {'returncode': proc.returncode, 'log': combined.strip()}
  except FileNotFoundError as exc:
    return {'returncode': 1, 'log': f'Command not found: {exc}'}
  except subprocess.TimeoutExpired:
    return {'returncode': 1, 'log': f'Timeout after {timeout_seconds}s: {" ".join(cmd)}'}


def _extract_counts(log: str) -> tuple[int, int]:
  passed_match = re.search(r'(\d+)\s+passed', log)
  failed_match = re.search(r'(\d+)\s+failed', log)
  passed = int(passed_match.group(1)) if passed_match else 0
  failed = int(failed_match.group(1)) if failed_match else 0
  return passed, failed


def _fetch_case(case_id: int):
  conn = get_conn()
  try:
    row = conn.execute('SELECT * FROM test_cases WHERE id = ?', (case_id,)).fetchone()
    return row
  finally:
    conn.close()


def _record_run(case_id: int, trigger_type: str, status: str, return_code: int, log: str, started_at: str, finished_at: str) -> int:
  conn = get_conn()
  try:
    cur = conn.execute(
      """
      INSERT INTO test_runs (case_id, trigger_type, status, return_code, log, started_at, finished_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      """,
      (case_id, trigger_type, status, return_code, log, started_at, finished_at),
    )
    conn.commit()
    return cur.lastrowid
  finally:
    conn.close()


def _run_test_case(case_row, trigger_type: str = 'manual') -> dict:
  case_id = case_row['id']
  runner = case_row['runner']
  script = case_row['script']
  started_at = utc_now()

  generated_dir = BACKEND_DIR / 'generated_tests' / 'dynamic'
  generated_dir.mkdir(parents=True, exist_ok=True)

  if runner == 'python_api':
    script_file = generated_dir / f'case_{case_id}.py'
    script_file.write_text(script, encoding='utf-8')
    result = _run_command([sys.executable, str(script_file)], cwd=PROJECT_ROOT, timeout_seconds=120)
    artifacts = [str(script_file)]
  elif runner == 'playwright_ui':
    ui_dir = PROJECT_ROOT / 'frontend' / 'tests' / 'generated'
    ui_dir.mkdir(parents=True, exist_ok=True)
    script_file = ui_dir / f'case_{case_id}.spec.ts'
    script_file.write_text(script, encoding='utf-8')

    frontend_env = os.environ.copy()
    frontend_env['BASE_URL'] = frontend_env.get('BASE_URL', 'http://localhost:5173')
    frontend_env['PLAYWRIGHT_HEADED'] = '1'
    frontend_env['PLAYWRIGHT_HOLD_MS'] = frontend_env.get('PLAYWRIGHT_HOLD_MS', '7000')
    frontend_env['PLAYWRIGHT_STEP_MS'] = frontend_env.get('PLAYWRIGHT_STEP_MS', '350')
    frontend_env['PLAYWRIGHT_SLOW_MO'] = frontend_env.get('PLAYWRIGHT_SLOW_MO', '140')

    result = _run_command(
      [
        'npx',
        'playwright',
        'test',
        f'tests/generated/case_{case_id}.spec.ts',
        '--config',
        'playwright.config.ts',
        '--headed',
      ],
      cwd=PROJECT_ROOT / 'frontend',
      timeout_seconds=90,
      env=frontend_env,
    )
    artifacts = [str(script_file)]
  else:
    result = {'returncode': 1, 'log': f'Unsupported runner: {runner}'}
    artifacts = []

  finished_at = utc_now()
  status = 'passed' if result['returncode'] == 0 else 'failed'
  run_id = _record_run(
    case_id=case_id,
    trigger_type=trigger_type,
    status=status,
    return_code=result['returncode'],
    log=result['log'],
    started_at=started_at,
    finished_at=finished_at,
  )

  return {
    'run_id': run_id,
    'case_id': case_id,
    'case_name': case_row['name'],
    'runner': runner,
    'status': status,
    'return_code': result['returncode'],
    'log': result['log'],
    'trigger_type': trigger_type,
    'artifacts': artifacts,
    'started_at': started_at,
    'finished_at': finished_at,
  }


def _run_test_case_by_id(case_id: int, trigger_type: str = 'manual') -> dict:
  case_row = _fetch_case(case_id)
  if not case_row:
    raise HTTPException(status_code=404, detail='Test case not found')
  return _run_test_case(case_row, trigger_type=trigger_type)


def _schedule_case(case_id: int, cron_expr: str, enabled: bool) -> None:
  job_id = f'test-case-{case_id}'
  if scheduler.get_job(job_id):
    scheduler.remove_job(job_id)

  if not enabled:
    return

  trigger = CronTrigger.from_crontab(cron_expr)
  scheduler.add_job(_run_test_case_by_id, trigger=trigger, id=job_id, replace_existing=True, args=[case_id, 'cron'])


def _resolve_schedule(mode: str, cron_expr: str | None) -> tuple[bool, str]:
  mode_to_cron = {
    'every_minute': '* * * * *',
    'daily': '0 9 * * *',
    'weekly': '0 9 * * 1',
  }

  if mode == 'none':
    enabled = False
    resolved = '0 9 * * *'
  elif mode in mode_to_cron:
    enabled = True
    resolved = mode_to_cron[mode]
  else:
    if not cron_expr:
      raise HTTPException(status_code=400, detail='cron_expr is required for custom mode')
    enabled = True
    resolved = cron_expr

  try:
    CronTrigger.from_crontab(resolved)
  except Exception:
    raise HTTPException(status_code=400, detail='Invalid cron expression. Expected standard 5-field crontab format.')

  return enabled, resolved


def _upsert_case_schedule(case_id: int, mode: str, cron_expr: str | None) -> dict:
  enabled, resolved = _resolve_schedule(mode, cron_expr)

  conn = get_conn()
  try:
    conn.execute(
      """
      INSERT INTO test_schedules (case_id, cron_expr, enabled, updated_at)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(case_id) DO UPDATE SET
        cron_expr=excluded.cron_expr,
        enabled=excluded.enabled,
        updated_at=excluded.updated_at
      """,
      (case_id, resolved, 1 if enabled else 0, utc_now()),
    )
    conn.commit()
  finally:
    conn.close()

  _schedule_case(case_id, resolved, enabled)
  return {'enabled': enabled, 'cron_expr': resolved, 'mode': mode}


def _load_schedules() -> None:
  conn = get_conn()
  try:
    rows = conn.execute('SELECT case_id, cron_expr, enabled FROM test_schedules').fetchall()
  finally:
    conn.close()

  for row in rows:
    _schedule_case(row['case_id'], row['cron_expr'], bool(row['enabled']))


def _migrate_legacy_runners() -> None:
  conn = get_conn()
  try:
    rows = conn.execute(
      """
      SELECT id, endpoint_method, endpoint_path
      FROM test_cases
      WHERE runner = 'shell_codex'
      """
    ).fetchall()

    for row in rows:
      method = row['endpoint_method'] or 'GET'
      path = row['endpoint_path'] or '/health'
      replacement_script = ai_service._script_for_runner(method, path, 'python_api')
      conn.execute(
        """
        UPDATE test_cases
        SET runner = 'python_api', script = ?, updated_at = ?
        WHERE id = ?
        """,
        (replacement_script, utc_now(), row['id']),
      )

    conn.commit()
  finally:
    conn.close()


def _migrate_playwright_case_scripts() -> None:
  conn = get_conn()
  try:
    rows = conn.execute(
      """
      SELECT id, name, description, endpoint_method, endpoint_path, script
      FROM test_cases
      WHERE runner = 'playwright_ui'
      """
    ).fetchall()

    for row in rows:
      target_method = row['endpoint_method'] if row['endpoint_method'] == 'PAGE' else 'PAGE'
      target_path = row['endpoint_path'] if row['endpoint_method'] == 'PAGE' else '/vessel-connect'
      refreshed = ai_service._script_for_runner(target_method, target_path, 'playwright_ui')
      normalized_name = row['name'] if (row['name'] or '').startswith('UI flow ') else f'UI flow {target_path} browser test'
      normalized_desc = (
        row['description']
        if 'page' in (row['description'] or '').lower()
        else f'Auto-generated browser workflow test for page {target_path}.'
      )
      conn.execute(
        """
        UPDATE test_cases
        SET name = ?, description = ?, endpoint_method = ?, endpoint_path = ?, script = ?, updated_at = ?
        WHERE id = ?
        """,
        (normalized_name, normalized_desc, target_method, target_path, refreshed, utc_now(), row['id']),
      )

    conn.commit()
  finally:
    conn.close()


@app.on_event('startup')
def startup() -> None:
  init_db()
  ai_service.seed_generated_tests_if_missing()
  _migrate_legacy_runners()
  _migrate_playwright_case_scripts()
  if not scheduler.running:
    scheduler.start()
  _load_schedules()


@app.on_event('shutdown')
def shutdown() -> None:
  if scheduler.running:
    scheduler.shutdown(wait=False)


@app.get('/health')
def health() -> Dict[str, str]:
  return {'status': 'ok'}


@app.get('/api/endpoints')
def list_endpoints() -> dict:
  return {'endpoints': ENDPOINT_CATALOG}


@app.get('/api/pages')
def list_pages() -> dict:
  return {'pages': PAGE_CATALOG}


@app.get('/api/test-cases')
def list_test_cases() -> dict:
  conn = get_conn()
  try:
    rows = conn.execute(
      """
      SELECT tc.*, ts.cron_expr, ts.enabled
      FROM test_cases tc
      LEFT JOIN test_schedules ts ON ts.case_id = tc.id
      ORDER BY tc.id DESC
      """
    ).fetchall()

    cases = []
    for row in rows:
      job = scheduler.get_job(f"test-case-{row['id']}")
      latest = conn.execute(
        'SELECT id, status, finished_at, trigger_type FROM test_runs WHERE case_id = ? ORDER BY id DESC LIMIT 1',
        (row['id'],),
      ).fetchone()

      cases.append(
        {
          'id': row['id'],
          'name': row['name'],
          'description': row['description'],
          'endpoint_method': row['endpoint_method'],
          'endpoint_path': row['endpoint_path'],
          'runner': row['runner'],
          'assertions': json.loads(row['assertions']),
          'created_at': row['created_at'],
          'updated_at': row['updated_at'],
          'schedule': {
            'enabled': bool(row['enabled']) if row['enabled'] is not None else False,
            'cron_expr': row['cron_expr'] or '',
            'next_run_at': (
              job.next_run_time.isoformat()
              if job and job.next_run_time
              else None
            ),
          },
          'latest_run': dict(latest) if latest else None,
        }
      )

    return {'test_cases': cases}
  finally:
    conn.close()


@app.get('/api/test-runs')
def list_test_runs(limit: int = 50) -> dict:
  conn = get_conn()
  try:
    rows = conn.execute(
      """
      SELECT tr.*, tc.name as case_name
      FROM test_runs tr
      JOIN test_cases tc ON tc.id = tr.case_id
      ORDER BY tr.id DESC
      LIMIT ?
      """,
      (limit,),
    ).fetchall()

    return {'runs': [dict(r) for r in rows]}
  finally:
    conn.close()


@app.post('/api/test-cases/auto-create')
def auto_create_test_case(payload: AutoCreateCaseRequest) -> dict:
  if payload.runner == 'python_api':
    if payload.target_type != 'endpoint':
      raise HTTPException(status_code=400, detail='python_api runner requires target_type=endpoint')
    if not payload.endpoint_method or not payload.endpoint_path:
      raise HTTPException(status_code=400, detail='endpoint_method and endpoint_path are required')

    endpoint_known = any(
      item['method'] == payload.endpoint_method and item['path'] == payload.endpoint_path for item in ENDPOINT_CATALOG
    )
    if not endpoint_known:
      raise HTTPException(status_code=404, detail='Endpoint not in catalog')

    target_method = payload.endpoint_method
    target_path = payload.endpoint_path
  else:
    if payload.target_type != 'page':
      raise HTTPException(status_code=400, detail='playwright_ui runner requires target_type=page')
    if not payload.page_path:
      raise HTTPException(status_code=400, detail='page_path is required')

    page_known = any(item['path'] == payload.page_path for item in PAGE_CATALOG)
    if not page_known:
      raise HTTPException(status_code=404, detail='Page not in catalog')

    target_method = 'PAGE'
    target_path = payload.page_path

  prepared_schedule: dict | None = None
  if payload.schedule_mode != 'none':
    enabled, resolved = _resolve_schedule(payload.schedule_mode, payload.schedule_cron_expr)
    prepared_schedule = {
      'enabled': enabled,
      'cron_expr': resolved,
      'mode': payload.schedule_mode,
    }

  spec = ai_service.generate_endpoint_test_case(
    endpoint_method=target_method,
    endpoint_path=target_path,
    runner=payload.runner,
    context_doc_id=payload.context_doc_id,
    ai_prompt=payload.ai_prompt,
  )

  case_name = payload.name.strip() if payload.name and payload.name.strip() else spec.name
  now = utc_now()
  conn = get_conn()
  try:
    cur = conn.execute(
      """
      INSERT INTO test_cases
      (name, description, endpoint_method, endpoint_path, runner, script, assertions, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      """,
      (
        case_name,
        spec.description,
        target_method,
        target_path,
        spec.runner,
        spec.script,
        json.dumps(spec.assertions),
        now,
        now,
      ),
    )
    conn.commit()
    case_id = cur.lastrowid
  finally:
    conn.close()

  schedule = {'enabled': False, 'cron_expr': '', 'mode': 'none'}
  if prepared_schedule:
    schedule = _upsert_case_schedule(case_id, prepared_schedule['mode'], prepared_schedule['cron_expr'])

  return {'created': True, 'case_id': case_id, 'name': case_name, 'schedule': schedule}


@app.delete('/api/test-cases/{case_id}')
def delete_test_case(case_id: int) -> dict:
  conn = get_conn()
  try:
    conn.execute('DELETE FROM test_runs WHERE case_id = ?', (case_id,))
    conn.execute('DELETE FROM test_schedules WHERE case_id = ?', (case_id,))
    conn.execute('DELETE FROM test_cases WHERE id = ?', (case_id,))
    conn.commit()
  finally:
    conn.close()

  if scheduler.get_job(f'test-case-{case_id}'):
    scheduler.remove_job(f'test-case-{case_id}')

  return {'deleted': True, 'case_id': case_id}


@app.post('/api/test-cases/{case_id}/run')
def run_single_test_case(case_id: int) -> dict:
  return _run_test_case_by_id(case_id, trigger_type='manual')


@app.post('/api/test-cases/run-all')
def run_all_test_cases() -> dict:
  conn = get_conn()
  try:
    rows = conn.execute('SELECT * FROM test_cases ORDER BY id ASC').fetchall()
  finally:
    conn.close()

  results = [_run_test_case(row, trigger_type='manual-batch') for row in rows]
  passed = sum(1 for r in results if r['status'] == 'passed')
  failed = sum(1 for r in results if r['status'] == 'failed')
  return {'passed': passed, 'failed': failed, 'results': results}


@app.post('/api/test-cases/{case_id}/schedule')
def set_case_schedule(case_id: int, payload: ScheduleRequest) -> dict:
  if not _fetch_case(case_id):
    raise HTTPException(status_code=404, detail='Test case not found')

  schedule = _upsert_case_schedule(case_id, payload.mode, payload.cron_expr)

  return {
    'case_id': case_id,
    'schedule': schedule,
  }


@app.post('/api/ai/index_doc', response_model=IndexDocResponse)
def index_doc(payload: IndexDocRequest) -> IndexDocResponse:
  if not payload.pdf_base64 and not payload.use_sample:
    payload.use_sample = True

  doc_id, chunks_count = rag.index_document(payload.pdf_base64, payload.use_sample)
  ai_service.log_index_doc(doc_id=doc_id, chunks_count=chunks_count)
  return IndexDocResponse(doc_id=doc_id, chunks_count=chunks_count)


@app.post('/api/ai/generate_tests')
def generate_tests(payload: GenerateTestsRequest):
  chunks = rag.get_doc_chunks(payload.doc_id)
  if not chunks:
    raise HTTPException(status_code=404, detail='doc_id not found. Run /api/ai/index_doc first.')

  response = ai_service.generate_tests(payload.doc_id, payload.product)
  return response.model_dump()


@app.post('/api/tests/run', response_model=RunTestsResponse)
def run_tests() -> RunTestsResponse:
  api_test_file = PROJECT_ROOT / 'backend' / 'generated_tests' / 'tests' / 'api' / 'test_vc_api.py'
  ui_test_file = PROJECT_ROOT / 'backend' / 'generated_tests' / 'tests' / 'ui' / 'vc.spec.ts'
  ui_test_staged = PROJECT_ROOT / 'frontend' / 'tests' / 'vc.generated.spec.ts'

  ai_service.seed_generated_tests_if_missing()

  pytest_env = os.environ.copy()
  pytest_env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'

  pytest_res = _run_command(
    [sys.executable, '-m', 'pytest', '-q', str(api_test_file)],
    cwd=PROJECT_ROOT,
    timeout_seconds=90,
    env=pytest_env,
  )
  pytest_passed, pytest_failed = _extract_counts(pytest_res['log'])
  if pytest_res['returncode'] != 0 and pytest_failed == 0:
    pytest_failed = 1

  frontend_env = os.environ.copy()
  frontend_env['BASE_URL'] = frontend_env.get('BASE_URL', 'http://localhost:5173')

  if ui_test_file.exists():
    ui_test_staged.write_text(ui_test_file.read_text(encoding='utf-8'), encoding='utf-8')

  playwright_res = _run_command(
    ['npx', 'playwright', 'test', 'tests/vc.generated.spec.ts', '--config', 'playwright.config.ts'],
    cwd=PROJECT_ROOT / 'frontend',
    timeout_seconds=120,
    env=frontend_env,
  )
  playwright_passed, playwright_failed = _extract_counts(playwright_res['log'])
  if playwright_res['returncode'] != 0 and playwright_failed == 0:
    playwright_failed = 1

  return RunTestsResponse(
    pytest={'passed': pytest_passed, 'failed': pytest_failed, 'log': pytest_res['log']},
    playwright={
      'passed': playwright_passed,
      'failed': playwright_failed,
      'log': playwright_res['log'],
    },
    artifacts=[str(api_test_file), str(ui_test_file), str(ui_test_staged)],
  )


@app.post('/api/ai/propose_fix')
def propose_fix(payload: ProposeFixRequest):
  response = ai_service.propose_fix(
    failing_logs=payload.failing_logs,
    target_files=payload.target_files,
    context_doc_id=payload.context_doc_id,
  )
  return response.model_dump()


@app.post('/api/fix/apply', response_model=ApplyFixResponse)
def apply_fix(payload: ApplyFixRequest) -> ApplyFixResponse:
  applied, message = apply_demo_patch(payload.patch_diff, PROJECT_ROOT)
  return ApplyFixResponse(applied=applied, message=message)
