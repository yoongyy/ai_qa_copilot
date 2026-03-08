from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Tuple

from ..audit.logger import log_ai_operation
from . import rag
from .schemas import AutoTestCaseSpec, Citation, GenerateTestsResponse, ProposeFixResponse


class AIService:
  def __init__(self, project_root: Path):
    self.project_root = project_root
    self.backend_dir = project_root / 'backend'
    self.generated_root = self.backend_dir / 'generated_tests'
    self.model = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')
    self.prompt_versions = {
      'index_doc': 'index_doc_v1',
      'generate_tests': 'generate_tests_v1',
      'propose_fix': 'propose_fix_v1',
      'auto_test_case': 'auto_test_case_v1',
    }

  @property
  def has_openai_key(self) -> bool:
    return bool(os.getenv('OPENAI_API_KEY'))

  def seed_generated_tests_if_missing(self) -> None:
    api_file = self.generated_root / 'tests' / 'api' / 'test_vc_api.py'
    ui_file = self.generated_root / 'tests' / 'ui' / 'vc.spec.ts'
    readme_file = self.generated_root / 'README.md'

    if api_file.exists() and ui_file.exists() and readme_file.exists():
      return

    citations = [Citation(page=1, excerpt='Sample vessel workflow excerpt for deterministic test generation.')]
    payload = self._mock_generate_tests([c.model_dump() for c in citations])
    self._write_generated_files(payload['generated_files'])

  def log_index_doc(self, doc_id: str, chunks_count: int) -> None:
    log_ai_operation(
      operation='index_doc',
      prompt_version=self.prompt_versions['index_doc'],
      retrieved_sources=[],
      model='mock-rag',
      cost_estimate=0.0,
      output={'doc_id': doc_id, 'chunks_count': chunks_count},
    )

  def generate_tests(self, doc_id: str, product: str) -> GenerateTestsResponse:
    sources = rag.retrieve_chunks(
      doc_id,
      query='nomination readiness scheduling cq coq signing secure messaging job calendar',
      top_k=4,
    )
    citations = self._citations_from_chunks(sources)

    def mock_builder() -> Dict[str, Any]:
      return self._mock_generate_tests(citations)

    def real_builder() -> Tuple[Dict[str, Any], float]:
      return self._real_generate_tests(citations, product)

    response = self._run_with_validation(
      schema=GenerateTestsResponse,
      operation='generate_tests',
      prompt_version=self.prompt_versions['generate_tests'],
      sources=citations,
      mock_builder=mock_builder,
      real_builder=real_builder,
    )

    self._write_generated_files(response.generated_files)
    return response

  def generate_endpoint_test_case(
    self,
    endpoint_method: str,
    endpoint_path: str,
    runner: str,
    context_doc_id: str | None = None,
    ai_prompt: str | None = None,
  ) -> AutoTestCaseSpec:
    sources = []
    prompt_text = ai_prompt.strip() if ai_prompt else None
    if context_doc_id:
      query = f'{endpoint_method} {endpoint_path}'
      if prompt_text:
        query = f'{query} {prompt_text}'
      chunks = rag.retrieve_chunks(context_doc_id, query=query, top_k=3)
      sources = self._citations_from_chunks(chunks)
    if not sources:
      sources = [{'page': 1, 'excerpt': f'Mock endpoint contract for {endpoint_method} {endpoint_path}'}]

    def mock_builder() -> Dict[str, Any]:
      return self._mock_auto_test_case(endpoint_method, endpoint_path, runner, sources, prompt_text)

    def real_builder() -> Tuple[Dict[str, Any], float]:
      return self._real_auto_test_case(endpoint_method, endpoint_path, runner, sources, prompt_text)

    return self._run_with_validation(
      schema=AutoTestCaseSpec,
      operation='auto_test_case',
      prompt_version=self.prompt_versions['auto_test_case'],
      sources=sources,
      mock_builder=mock_builder,
      real_builder=real_builder,
    )

  def propose_fix(self, failing_logs: str, target_files: List[str], context_doc_id: str | None) -> ProposeFixResponse:
    sources = []
    if context_doc_id:
      chunks = rag.retrieve_chunks(context_doc_id, query='schedule calendar event bug', top_k=3)
      sources = self._citations_from_chunks(chunks)

    def mock_builder() -> Dict[str, Any]:
      return self._mock_propose_fix()

    def real_builder() -> Tuple[Dict[str, Any], float]:
      return self._real_propose_fix(failing_logs, target_files, sources)

    return self._run_with_validation(
      schema=ProposeFixResponse,
      operation='propose_fix',
      prompt_version=self.prompt_versions['propose_fix'],
      sources=sources,
      mock_builder=mock_builder,
      real_builder=real_builder,
    )

  def _run_with_validation(
    self,
    schema,
    operation: str,
    prompt_version: str,
    sources: List[Dict[str, Any]],
    mock_builder: Callable[[], Dict[str, Any]],
    real_builder: Callable[[], Tuple[Dict[str, Any], float]],
  ):
    if self.has_openai_key:
      for _ in range(2):
        try:
          raw, cost = real_builder()
          validated = schema.model_validate(raw)
          log_ai_operation(
            operation=operation,
            prompt_version=prompt_version,
            retrieved_sources=sources,
            model=self.model,
            cost_estimate=cost,
            output=validated.model_dump(),
          )
          return validated
        except Exception:
          continue

    fallback = schema.model_validate(mock_builder())
    log_ai_operation(
      operation=operation,
      prompt_version=prompt_version,
      retrieved_sources=sources,
      model='mock-ai',
      cost_estimate=0.0,
      output=fallback.model_dump(),
    )
    return fallback

  def _real_generate_tests(self, citations: List[Dict[str, Any]], product: str) -> Tuple[Dict[str, Any], float]:
    prompt = {
      'product': product,
      'sources': citations,
      'requirements': {
        'workflow_summary_count': 4,
        'test_cases_count': 12,
      },
      'output_keys': ['workflow_summary', 'test_cases'],
    }

    data, cost = self._call_openai_json(
      system_prompt='You generate QA design JSON. Return JSON with workflow_summary and test_cases.',
      user_payload=prompt,
    )
    data['generated_files'] = self._generated_files_payload()
    return data, cost

  def _real_auto_test_case(
    self,
    endpoint_method: str,
    endpoint_path: str,
    runner: str,
    citations: List[Dict[str, Any]],
    ai_prompt: str | None = None,
  ) -> Tuple[Dict[str, Any], float]:
    target_kind = 'page' if endpoint_method == 'PAGE' else 'endpoint'
    prompt = {
      'target': {'kind': target_kind, 'method': endpoint_method, 'path': endpoint_path},
      'runner': runner,
      'ai_prompt': ai_prompt,
      'sources': citations,
      'output_keys': ['name', 'description', 'assertions'],
    }

    data, cost = self._call_openai_json(
      system_prompt='Generate concise QA test metadata in JSON only.',
      user_payload=prompt,
    )

    data['runner'] = runner
    data['script'] = self._script_for_runner(endpoint_method, endpoint_path, runner)
    data['citations'] = citations[:2]
    if 'assertions' not in data or not isinstance(data['assertions'], list):
      if runner == 'playwright_ui':
        data['assertions'] = [f'Page {endpoint_path} renders and workflow actions complete with expected status']
      else:
        data['assertions'] = [f'{endpoint_method} {endpoint_path} returns expected status and payload']
    return data, cost

  def _real_propose_fix(
    self,
    failing_logs: str,
    target_files: List[str],
    citations: List[Dict[str, Any]],
  ) -> Tuple[Dict[str, Any], float]:
    patch_diff = self._build_bug_fix_diff()

    payload = {
      'failing_logs': failing_logs[-6000:],
      'target_files': target_files,
      'sources': citations,
      'output_keys': ['root_cause', 'regression_tests', 'rollout_plan', 'risk_level'],
    }

    data, cost = self._call_openai_json(
      system_prompt='You are a senior engineer. Return JSON only.',
      user_payload=payload,
    )

    data['patch_diff'] = patch_diff
    return data, cost

  def _call_openai_json(self, system_prompt: str, user_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    response = client.chat.completions.create(
      model=self.model,
      temperature=0.1,
      response_format={'type': 'json_object'},
      messages=[
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': json.dumps(user_payload)},
      ],
    )

    content = response.choices[0].message.content or '{}'
    data = self._extract_json(content)

    usage = getattr(response, 'usage', None)
    cost = 0.0
    if usage:
      prompt_tokens = getattr(usage, 'prompt_tokens', 0) or 0
      completion_tokens = getattr(usage, 'completion_tokens', 0) or 0
      cost = round((prompt_tokens * 0.0000003) + (completion_tokens * 0.0000012), 6)

    return data, cost

  def _extract_json(self, text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith('{'):
      return json.loads(text)

    fenced_match = re.search(r'```json\s*(\{.*\})\s*```', text, flags=re.DOTALL)
    if fenced_match:
      return json.loads(fenced_match.group(1))

    braces_match = re.search(r'(\{.*\})', text, flags=re.DOTALL)
    if braces_match:
      return json.loads(braces_match.group(1))

    raise ValueError('Failed to parse JSON response from model')

  def _citations_from_chunks(self, chunks: List[rag.Chunk]) -> List[Dict[str, Any]]:
    citations: List[Dict[str, Any]] = []
    for chunk in chunks:
      excerpt = chunk.text[:180].strip().replace('\n', ' ')
      citations.append({'page': chunk.page, 'excerpt': excerpt})
    return citations

  def _mock_generate_tests(self, citations: List[Dict[str, Any]]) -> Dict[str, Any]:
    tc_rows = [
      ('TC-01', 'Nomination creation happy path', ['@smoke', '@api']),
      ('TC-02', 'Readiness timestamp update', ['@api']),
      ('TC-03', 'Schedule update with jetty and ETA', ['@api', '@ui']),
      ('TC-04', 'Schedule update creates calendar event', ['@api', '@critical']),
      ('TC-05', 'Link CQ/COQ to nomination', ['@api']),
      ('TC-06', 'Sign linked CQ digitally', ['@api']),
      ('TC-07', 'Secure messaging retrieval', ['@api']),
      ('TC-08', 'Job calendar retrieval by nomination', ['@api']),
      ('TC-09', 'Negative: schedule on unknown nomination', ['@negative']),
      ('TC-10', 'Negative: sign unknown CQ id', ['@negative']),
      ('TC-11', 'Security: reject malformed payloads', ['@security']),
      ('TC-12', 'Security: no key leakage in UI/API logs', ['@security', '@negative']),
    ]

    test_cases = []
    if not citations:
      citations = [{'page': 1, 'excerpt': 'Default citation for mock generation.'}]

    for idx, (case_id, title, tags) in enumerate(tc_rows, start=1):
      citation = citations[(idx - 1) % len(citations)]
      gherkin = (
        f'Given Vessel Connect is running\n'
        f'When I execute scenario {case_id} for {title.lower()}\n'
        f'Then the system returns governed, auditable behavior'
      )
      test_cases.append(
        {
          'id': case_id,
          'title': title,
          'gherkin': gherkin,
          'tags': tags,
          'citations': [citation],
        }
      )

    return {
      'workflow_summary': [
        {
          'title': 'Nomination Lifecycle',
          'detail': 'Create nomination, update readiness, then assign jetty and ETA for execution readiness.',
          'citations': citations[:1],
        },
        {
          'title': 'Scheduling Dependency',
          'detail': 'Schedule updates should propagate into a visible calendar event for operational coordination.',
          'citations': citations[1:2] or citations[:1],
        },
        {
          'title': 'CQ/COQ Flow',
          'detail': 'Nomination links to CQ/COQ process and requires digital signing completion.',
          'citations': citations[2:3] or citations[:1],
        },
        {
          'title': 'Audit and Messaging',
          'detail': 'All operations should be observable via secure messages and traceable logs.',
          'citations': citations[3:4] or citations[:1],
        },
      ],
      'test_cases': test_cases,
      'generated_files': self._generated_files_payload(),
    }

  def _mock_auto_test_case(
    self,
    endpoint_method: str,
    endpoint_path: str,
    runner: str,
    citations: List[Dict[str, Any]],
    ai_prompt: str | None = None,
  ) -> Dict[str, Any]:
    is_page_target = endpoint_method == 'PAGE'
    prompt_text = ai_prompt.strip() if ai_prompt else ''
    prompt_excerpt = prompt_text[:220]
    case_name = (
      f'UI flow {endpoint_path} browser test'
      if is_page_target and runner == 'playwright_ui'
      else f'{endpoint_method} {endpoint_path} smoke test'
    )
    case_desc = (
      f'Auto-generated browser workflow test for page {endpoint_path}.'
      if is_page_target and runner == 'playwright_ui'
      else f'Auto-generated test for {endpoint_method} {endpoint_path} using {runner}.'
    )
    if prompt_excerpt:
      case_desc = f'{case_desc} AI workflow prompt: {prompt_excerpt}'
    assertions = (
      [
        f'Page {endpoint_path} loads with blank defaults',
        'Form submission updates visible status and nomination id',
        'Schedule update shows calendar count and status update',
      ]
      if is_page_target and runner == 'playwright_ui'
      else [
        f'{endpoint_method} {endpoint_path} returns expected status',
        'Response payload includes expected fields',
      ]
    )
    if prompt_excerpt:
      assertions.insert(0, f'AI prompt intent is covered: {prompt_excerpt}')

    return {
      'name': case_name,
      'description': case_desc,
      'runner': runner,
      'script': self._script_for_runner(endpoint_method, endpoint_path, runner),
      'assertions': assertions,
      'citations': citations[:2],
    }

  def _generated_files_payload(self) -> List[Dict[str, str]]:
    return [
      {
        'path': 'tests/ui/vc.spec.ts',
        'language': 'typescript',
        'contents': self._playwright_test_template(),
      },
      {
        'path': 'tests/api/test_vc_api.py',
        'language': 'python',
        'contents': self._pytest_test_template(),
      },
      {
        'path': 'README.md',
        'language': 'markdown',
        'contents': self._generated_readme_template(),
      },
    ]

  def _mock_propose_fix(self) -> Dict[str, Any]:
    patch_diff = self._build_bug_fix_diff()
    if not patch_diff:
      patch_diff = (
        '--- a/backend/app/vc_api.py\n'
        '+++ b/backend/app/vc_api.py\n'
        '@@ -1,1 +1,1 @@\n'
        ' # Patch not generated because file already appears fixed.\n'
      )

    return {
      'root_cause': (
        'The schedule endpoint updates nomination fields and writes a message, but it does not '
        'persist a calendar event. Calendar queries therefore return zero events.'
      ),
      'patch_diff': patch_diff,
      'regression_tests': [
        'API: after PATCH /vc/nominations/{id}/schedule, GET /vc/nominations/{id}/calendar returns at least one event.',
        'UI: scheduling through the form updates calendar count from 0 to 1.',
        'Contract: calendar event title includes jetty and start_time equals scheduled ETA.',
      ],
      'rollout_plan': [
        'Guard the calendar insert behind feature flag vc_schedule_calendar_event_enabled.',
        'Monitor metrics: schedule_patch_success_rate and calendar_event_create_rate.',
        'Audit fields: nomination_id, jetty, eta, actor, patch_version in structured logs.',
      ],
      'risk_level': 'low',
    }

  def _build_bug_fix_diff(self) -> str:
    target = self.backend_dir / 'app' / 'vc_api.py'
    original = target.read_text(encoding='utf-8')

    buggy_block = (
      '    # Intentional bug for demo: schedule updates do not create calendar events.\n'
      '    # create_calendar_event(conn, nomination_id, f"Jetty call at {payload.jetty}", payload.eta)\n'
    )
    fixed_block = '    create_calendar_event(conn, nomination_id, f"Jetty call at {payload.jetty}", payload.eta)\n'

    if buggy_block not in original:
      return ''

    updated = original.replace(buggy_block, fixed_block)

    diff = difflib.unified_diff(
      original.splitlines(keepends=True),
      updated.splitlines(keepends=True),
      fromfile='a/backend/app/vc_api.py',
      tofile='b/backend/app/vc_api.py',
    )
    return ''.join(diff)

  def _write_generated_files(self, generated_files: List[Any]) -> None:
    self.generated_root.mkdir(parents=True, exist_ok=True)

    normalized: List[Dict[str, str]] = []
    for item in generated_files:
      if hasattr(item, 'model_dump'):
        normalized.append(item.model_dump())
      else:
        normalized.append(item)

    root_resolved = self.generated_root.resolve()
    for file_obj in normalized:
      rel_path = file_obj['path'].strip().lstrip('/')
      destination = (self.generated_root / rel_path).resolve()
      if root_resolved not in destination.parents and destination != root_resolved:
        continue
      destination.parent.mkdir(parents=True, exist_ok=True)
      destination.write_text(file_obj['contents'], encoding='utf-8')

  def _script_for_runner(self, method: str, path: str, runner: str) -> str:
    if runner == 'python_api':
      return self._python_runner_script(method, path)
    if runner == 'playwright_ui':
      return self._playwright_runner_script(method, path)
    raise ValueError(f'Unsupported runner: {runner}')

  def _python_runner_script(self, method: str, path: str) -> str:
    if path == '/vc/nominations/{id}/schedule':
      return """from pathlib import Path
import sys
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.db import init_db
from backend.app.main import app

init_db()
client = TestClient(app)

nom = client.post('/vc/nominations', json={
  'vessel_name': 'MT Auto Python',
  'port': 'Singapore',
  'eta': '2026-03-15T10:00:00Z'
})
assert nom.status_code == 200
nom_id = nom.json()['id']

sched = client.patch(f'/vc/nominations/{nom_id}/schedule', json={
  'jetty': 'Jetty-Z9',
  'eta': '2026-03-15T12:00:00Z'
})
assert sched.status_code == 200

calendar = client.get(f'/vc/nominations/{nom_id}/calendar')
assert calendar.status_code == 200
assert len(calendar.json()['events']) >= 1, 'Expected at least 1 calendar event after scheduling'
print('PASS: calendar event created')
"""

    if path == '/vc/nominations/{id}/readiness':
      return """from pathlib import Path
import sys
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.db import init_db
from backend.app.main import app

init_db()
client = TestClient(app)

nom = client.post('/vc/nominations', json={
  'vessel_name': 'MT Auto Readiness',
  'port': 'Singapore',
  'eta': '2026-03-15T10:00:00Z'
})
assert nom.status_code == 200
nom_id = nom.json()['id']

res = client.patch(f'/vc/nominations/{nom_id}/readiness', json={'readiness_time': '2026-03-15T11:00:00Z'})
assert res.status_code == 200
assert res.json()['readiness_time'] == '2026-03-15T11:00:00Z'
print('PASS: readiness updated')
"""

    return f"""from pathlib import Path
import sys
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.db import init_db
from backend.app.main import app

init_db()
client = TestClient(app)
res = client.get('/health')
assert res.status_code == 200
print('PASS: smoke test for {method} {path}')
"""

  def _playwright_runner_script(self, method: str, path: str) -> str:
    target_path = path if path.startswith('/') else '/vessel-connect'
    test_label = f'PAGE {target_path}' if method == 'PAGE' else f'{method} {path}'
    return f"""import {{ expect, test }} from '@playwright/test';

test('{test_label} ui smoke', async ({{ page }}) => {{
  const base = process.env.BASE_URL || 'http://localhost:5173';
  const stepMs = Number(process.env.PLAYWRIGHT_STEP_MS || '450');

  const moveMouseTo = async (testId: string) => {{
    const locator = page.getByTestId(testId);
    const box = await locator.boundingBox();
    if (!box) return;
    await page.mouse.move(box.x - 45, box.y - 20);
    await page.waitForTimeout(Math.max(200, Math.floor(stepMs / 2)));
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, {{ steps: 22 }});
  }};

  await test.step('Open Vessel Connect simulator', async () => {{
    await page.goto(`${{base}}{target_path}`);
    await expect(page.getByTestId('vc-vessel-name')).toHaveValue('');
    await expect(page.getByTestId('vc-port')).toHaveValue('');
    await expect(page.getByTestId('vc-eta')).toHaveValue('');
    await page.waitForTimeout(stepMs);
  }});

  await test.step('Fill nomination form with visible pacing', async () => {{
    await page.getByTestId('vc-vessel-name').click();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-vessel-name').fill('MT Playwright Live 101');
    await page.waitForTimeout(stepMs);

    await page.getByTestId('vc-port').click();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-port').fill('Rotterdam');
    await page.waitForTimeout(stepMs);

    await page.getByTestId('vc-eta').click();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-eta').fill('2026-03-21T09:15:00Z');
    await page.waitForTimeout(stepMs);
  }});

  await test.step('Hover and submit nomination', async () => {{
    await moveMouseTo('vc-submit');
    await page.getByTestId('vc-submit').hover();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-submit').click();
    await page.waitForTimeout(stepMs);
    await expect(page.getByTestId('vc-submit-status')).toContainText('Form submitted successfully');
    await expect(page.getByTestId('vc-nomination-id')).not.toHaveText('-');
  }});

  await test.step('Fill schedule form and hover-click update', async () => {{
    await page.getByTestId('vc-jetty').click();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-jetty').fill('Jetty-Blue-7');
    await page.waitForTimeout(stepMs);

    await page.getByTestId('vc-schedule-eta').click();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-schedule-eta').fill('2026-03-21T11:45:00Z');
    await page.waitForTimeout(stepMs);

    await moveMouseTo('vc-schedule-submit');
    await page.getByTestId('vc-schedule-submit').hover();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-schedule-submit').click();
    await page.waitForTimeout(stepMs);
    await expect(page.getByTestId('vc-schedule-status')).toContainText('Schedule updated');
    await expect(page.getByTestId('vc-calendar-count')).toContainText('Calendar Events:');
  }});

  // Keep browser open briefly so humans can observe the flow in headed mode.
  const holdMs = Number(process.env.PLAYWRIGHT_HOLD_MS || '10000');
  await page.waitForTimeout(holdMs);
}});
"""

  def _playwright_test_template(self) -> str:
    return """import { expect, test } from '@playwright/test';

test('vessel connect simulator form submit flow', async ({ page }) => {
  await page.goto('/vessel-connect');
  await expect(page.getByTestId('vc-vessel-name')).toHaveValue('');
  await expect(page.getByTestId('vc-port')).toHaveValue('');
  await expect(page.getByTestId('vc-eta')).toHaveValue('');

  await page.getByTestId('vc-vessel-name').fill('MT Generated Demo');
  await page.getByTestId('vc-port').fill('Singapore');
  await page.getByTestId('vc-eta').fill('2026-03-16T09:00:00Z');
  await page.getByTestId('vc-submit').hover();
  await page.getByTestId('vc-submit').click();
  await expect(page.getByTestId('vc-submit-status')).toContainText('Form submitted successfully');
  await expect(page.getByTestId('vc-nomination-id')).not.toHaveText('-');

  await page.getByTestId('vc-jetty').fill('Jetty-A1');
  await page.getByTestId('vc-schedule-eta').fill('2026-03-16T11:00:00Z');
  await page.getByTestId('vc-schedule-submit').hover();
  await page.getByTestId('vc-schedule-submit').click();
  await expect(page.getByTestId('vc-schedule-status')).toContainText('Schedule updated');
});
"""

  def _pytest_test_template(self) -> str:
    return """from pathlib import Path
import sys

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.db import init_db
from backend.app.main import app

init_db()
client = TestClient(app)


def _create_nomination() -> str:
  response = client.post(
    '/vc/nominations',
    json={
      'vessel_name': 'MT API Demo',
      'port': 'Singapore',
      'eta': '2026-03-10T08:00:00Z',
    },
  )
  assert response.status_code == 200
  return response.json()['id']


def test_nomination_creation():
  nomination_id = _create_nomination()
  assert nomination_id.startswith('nom-')


def test_readiness_update():
  nomination_id = _create_nomination()
  response = client.patch(
    f'/vc/nominations/{nomination_id}/readiness',
    json={'readiness_time': '2026-03-10T09:00:00Z'},
  )
  assert response.status_code == 200
  assert response.json()['readiness_time'] == '2026-03-10T09:00:00Z'


def test_schedule_update_creates_calendar_event():
  nomination_id = _create_nomination()

  patch = client.patch(
    f'/vc/nominations/{nomination_id}/schedule',
    json={'jetty': 'Jetty-C9', 'eta': '2026-03-10T10:00:00Z'},
  )
  assert patch.status_code == 200

  calendar = client.get(f'/vc/nominations/{nomination_id}/calendar')
  assert calendar.status_code == 200
  assert len(calendar.json()['events']) == 1


def test_link_and_sign_cq():
  nomination_id = _create_nomination()
  link = client.post(f'/vc/nominations/{nomination_id}/link-cq', json={})
  assert link.status_code == 200
  cq_id = link.json()['cq_id']

  sign = client.post(f'/vc/cq/{cq_id}/sign', json={'signed_by': 'qa.engineer'})
  assert sign.status_code == 200
  assert sign.json()['status'] == 'signed'


def test_negative_schedule_unknown_nomination():
  response = client.patch(
    '/vc/nominations/nom-does-not-exist/schedule',
    json={'jetty': 'Jetty-404', 'eta': '2026-03-10T10:00:00Z'},
  )
  assert response.status_code == 404
"""

  def _generated_readme_template(self) -> str:
    return """# Generated Test Suite

This folder contains AI-generated runnable tests for Vessel Connect demo.

## Files

- `tests/api/test_vc_api.py` (Pytest)
- `tests/ui/vc.spec.ts` (Playwright)

## Run

From repository root:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q backend/generated_tests/tests/api/test_vc_api.py
cd frontend && npx playwright test ../backend/generated_tests/tests/ui/vc.spec.ts --config playwright.config.ts
```
"""
