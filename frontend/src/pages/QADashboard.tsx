import { useEffect, useMemo, useRef, useState } from 'react';
import CodeBlock from '../components/CodeBlock';

type Endpoint = {
  method: string;
  path: string;
  description: string;
};

type PageTarget = {
  path: string;
  name: string;
  description: string;
};

type ScheduleMode = 'none' | 'every_minute' | 'daily' | 'weekly' | 'custom';

type TestCase = {
  id: number;
  name: string;
  description: string;
  endpoint_method: string;
  endpoint_path: string;
  runner: 'python_api' | 'playwright_ui';
  assertions: string[];
  created_at: string;
  updated_at: string;
  schedule: {
    enabled: boolean;
    cron_expr: string;
    next_run_at: string | null;
  };
  latest_run: {
    id: number;
    status: 'passed' | 'failed';
    finished_at: string;
    trigger_type: string;
  } | null;
};

type TestRun = {
  id: number;
  case_id: number;
  case_name: string;
  status: 'passed' | 'failed';
  return_code: number;
  log: string;
  trigger_type: string;
  finished_at: string;
};

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
const MOCK_NEW_API = { method: 'POST', path: '/vc/nominations/{id}/link-cq' };
const MOCK_NEW_PAGE = { path: '/vessel-connect', name: 'Vessel Connect Simulator' };

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function apiPost<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function apiDelete(path: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await response.text());
  }
}

function detectScheduleMode(schedule: TestCase['schedule']): ScheduleMode {
  if (!schedule.enabled) return 'none';
  if (schedule.cron_expr === '* * * * *') return 'every_minute';
  if (schedule.cron_expr === '0 9 * * *') return 'daily';
  if (schedule.cron_expr === '0 9 * * 1') return 'weekly';
  return 'custom';
}

function formatMalaysiaDateTime(iso: string | null): string {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '-';

  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kuala_Lumpur',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).formatToParts(date);

  const pick = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  const dayPeriod = pick('dayPeriod').toUpperCase();
  return `${pick('day')}/${pick('month')}/${pick('year')} ${pick('hour')}:${pick('minute')}${dayPeriod}`;
}

export default function QADashboard() {
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [pages, setPages] = useState<PageTarget[]>([]);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [runs, setRuns] = useState<TestRun[]>([]);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedEndpointKey, setSelectedEndpointKey] = useState('');
  const [selectedPagePath, setSelectedPagePath] = useState('/vessel-connect');
  const [selectedRunner, setSelectedRunner] = useState<TestCase['runner']>('python_api');
  const [createName, setCreateName] = useState('');
  const [createAiPrompt, setCreateAiPrompt] = useState('');
  const [createScheduleMode, setCreateScheduleMode] = useState<ScheduleMode>('none');
  const [createScheduleCron, setCreateScheduleCron] = useState('0 9 * * *');
  const [mockNotifVisible, setMockNotifVisible] = useState(true);

  const [scheduleModeByCase, setScheduleModeByCase] = useState<Record<number, ScheduleMode>>({});
  const [customCronByCase, setCustomCronByCase] = useState<Record<number, string>>({});

  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('Ready');
  const [error, setError] = useState<string | null>(null);
  const customCronSaveTimers = useRef<Record<number, number>>({});

  const runSummary = useMemo(() => {
    const passed = runs.filter((r) => r.status === 'passed').length;
    const failed = runs.filter((r) => r.status === 'failed').length;
    return { passed, failed };
  }, [runs]);

  const loadAll = async () => {
    const [epRes, pageRes, caseRes, runRes] = await Promise.all([
      apiGet<{ endpoints: Endpoint[] }>('/api/endpoints'),
      apiGet<{ pages: PageTarget[] }>('/api/pages'),
      apiGet<{ test_cases: TestCase[] }>('/api/test-cases'),
      apiGet<{ runs: TestRun[] }>('/api/test-runs?limit=40'),
    ]);

    setEndpoints(epRes.endpoints);
    setPages(pageRes.pages);
    setTestCases(caseRes.test_cases);
    setRuns(runRes.runs);

    const modes: Record<number, ScheduleMode> = {};
    const crons: Record<number, string> = {};
    caseRes.test_cases.forEach((c) => {
      modes[c.id] = detectScheduleMode(c.schedule);
      crons[c.id] = c.schedule.cron_expr;
    });
    setScheduleModeByCase(modes);
    setCustomCronByCase(crons);

    if (!selectedEndpointKey && epRes.endpoints.length > 0) {
      const first = epRes.endpoints[0];
      setSelectedEndpointKey(`${first.method}|||${first.path}`);
    }
    if (!selectedPagePath && pageRes.pages.length > 0) {
      setSelectedPagePath(pageRes.pages[0].path);
    }
  };

  useEffect(() => {
    loadAll().catch((e) => setError((e as Error).message));

    const pollId = window.setInterval(() => {
      loadAll().catch(() => {
        // Keep polling silent when backend briefly reloads.
      });
    }, 10000);

    return () => window.clearInterval(pollId);
  }, []);

  useEffect(() => {
    return () => {
      Object.values(customCronSaveTimers.current).forEach((timerId) => window.clearTimeout(timerId));
    };
  }, []);

  const openCreateModal = () => {
    if (!selectedEndpointKey && endpoints.length > 0) {
      setSelectedEndpointKey(`${endpoints[0].method}|||${endpoints[0].path}`);
    }
    setCreateName('');
    setCreateAiPrompt('');
    setCreateScheduleMode('none');
    setCreateScheduleCron('0 9 * * *');
    setShowCreateModal(true);
  };

  const openCreateModalForApi = (method: string, path: string) => {
    const found = endpoints.find((ep) => ep.method === method && ep.path === path);
    const endpointKey = found
      ? `${found.method}|||${found.path}`
      : endpoints.length > 0
        ? `${endpoints[0].method}|||${endpoints[0].path}`
        : '';

    setSelectedRunner('python_api');
    setSelectedEndpointKey(endpointKey);
    setCreateName(`${method} ${path} coverage`);
    setCreateAiPrompt(`Generate a test that validates ${method} ${path} behavior and critical edge cases.`);
    setCreateScheduleMode('none');
    setCreateScheduleCron('0 9 * * *');
    setShowCreateModal(true);
  };

  const openCreateModalForPage = (path: string, pageName: string) => {
    const found = pages.find((p) => p.path === path);
    const targetPage = found ? found.path : pages.length > 0 ? pages[0].path : path;

    setSelectedRunner('playwright_ui');
    setSelectedPagePath(targetPage);
    setCreateName(`${pageName} browser flow`);
    setCreateAiPrompt(`Generate a browser workflow test for ${pageName} (${path}) with realistic user actions and assertions.`);
    setCreateScheduleMode('none');
    setCreateScheduleCron('0 9 * * *');
    setShowCreateModal(true);
  };

  const createCase = async () => {
    setError(null);
    setBusy(true);

    try {
      const payload: Record<string, unknown> = {
        runner: selectedRunner,
        name: createName.trim() ? createName.trim() : undefined,
        schedule_mode: createScheduleMode,
        ai_prompt: createAiPrompt.trim() ? createAiPrompt.trim() : undefined,
      };
      if (createScheduleMode === 'custom') {
        const cron = createScheduleCron.trim();
        if (!cron) {
          throw new Error('Custom cron expression is required');
        }
        payload.schedule_cron_expr = cron;
      }

      if (selectedRunner === 'python_api') {
        if (!selectedEndpointKey) {
          throw new Error('Please select an API endpoint');
        }
        const [endpoint_method, endpoint_path] = selectedEndpointKey.split('|||');
        setStatus(`Creating AI test case for ${endpoint_method} ${endpoint_path}...`);
        payload.target_type = 'endpoint';
        payload.endpoint_method = endpoint_method;
        payload.endpoint_path = endpoint_path;
        await apiPost('/api/test-cases/auto-create', payload);
      } else {
        if (!selectedPagePath) {
          throw new Error('Please select a page');
        }
        setStatus(`Creating AI browser test case for page ${selectedPagePath}...`);
        payload.target_type = 'page';
        payload.page_path = selectedPagePath;
        await apiPost('/api/test-cases/auto-create', payload);
      }

      await loadAll();
      setShowCreateModal(false);
      setStatus('Test case created');
    } catch (e) {
      setError((e as Error).message);
      setStatus('Failed to create test case');
    } finally {
      setBusy(false);
    }
  };

  const runCase = async (caseId: number) => {
    setError(null);
    setBusy(true);
    setStatus(`Running test case #${caseId}...`);

    try {
      await apiPost(`/api/test-cases/${caseId}/run`);
      await loadAll();
      setStatus(`Finished test case #${caseId}`);
    } catch (e) {
      setError((e as Error).message);
      setStatus('Run failed');
    } finally {
      setBusy(false);
    }
  };

  const runAll = async () => {
    setError(null);
    setBusy(true);
    setStatus('Running all test cases...');

    try {
      await apiPost('/api/test-cases/run-all', {});
      await loadAll();
      setStatus('Finished running all test cases');
    } catch (e) {
      setError((e as Error).message);
      setStatus('Run-all failed');
    } finally {
      setBusy(false);
    }
  };

  const saveSchedule = async (caseId: number, mode: ScheduleMode, cronExpr: string) => {
    setError(null);
    setBusy(true);
    setStatus(`Saving auto cron for #${caseId}...`);

    try {
      await apiPost(`/api/test-cases/${caseId}/schedule`, {
        mode,
        cron_expr: cronExpr,
      });
      await loadAll();
      setStatus(`Auto cron saved for #${caseId}`);
    } catch (e) {
      setError((e as Error).message);
      setStatus('Schedule update failed');
    } finally {
      setBusy(false);
    }
  };

  const onScheduleModeChange = (testCase: TestCase, nextMode: ScheduleMode) => {
    setScheduleModeByCase((prev) => ({
      ...prev,
      [testCase.id]: nextMode,
    }));

    const cronExpr = customCronByCase[testCase.id] || '';
    if (nextMode === 'custom') {
      const fields = cronExpr.trim().split(/\s+/).filter(Boolean);
      if (fields.length === 5) {
        void saveSchedule(testCase.id, 'custom', cronExpr.trim());
      } else {
        setStatus(`Custom cron selected for #${testCase.id}. Enter a 5-field cron expression to auto-save.`);
      }
      return;
    }

    void saveSchedule(testCase.id, nextMode, cronExpr);
  };

  const onCustomCronChange = (testCase: TestCase, nextCron: string) => {
    setCustomCronByCase((prev) => ({
      ...prev,
      [testCase.id]: nextCron,
    }));

    const existingTimer = customCronSaveTimers.current[testCase.id];
    if (existingTimer) {
      window.clearTimeout(existingTimer);
    }

    customCronSaveTimers.current[testCase.id] = window.setTimeout(() => {
      const trimmed = nextCron.trim();
      const fields = trimmed.split(/\s+/).filter(Boolean);
      if (fields.length !== 5) {
        return;
      }
      void saveSchedule(testCase.id, 'custom', trimmed);
    }, 700);
  };

  const deleteCase = async (caseId: number) => {
    setError(null);
    setBusy(true);
    setStatus(`Deleting test case #${caseId}...`);

    try {
      await apiDelete(`/api/test-cases/${caseId}`);
      await loadAll();
      setStatus(`Deleted test case #${caseId}`);
    } catch (e) {
      setError((e as Error).message);
      setStatus('Delete failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="qa-layout">
      {mockNotifVisible && (
        <aside className="notification-popup">
          <div className="notification-popup-head">
            <strong>New Targets Found</strong>
            <button className="btn tiny" onClick={() => setMockNotifVisible(false)}>
              x
            </button>
          </div>
          <div className="notification-popup-list">
            <div className="notify-item compact">
              <span className="notify-badge">New API</span>
              <p>
                {MOCK_NEW_API.method} {MOCK_NEW_API.path}
              </p>
              <button
                className="btn primary tiny"
                onClick={() => openCreateModalForApi(MOCK_NEW_API.method, MOCK_NEW_API.path)}
              >
                Create Test Case Now
              </button>
            </div>
            <div className="notify-item compact">
              <span className="notify-badge">New Page</span>
              <p>{MOCK_NEW_PAGE.name}</p>
              <button
                className="btn primary tiny"
                onClick={() => openCreateModalForPage(MOCK_NEW_PAGE.path, MOCK_NEW_PAGE.name)}
              >
                Create Test Case Now
              </button>
            </div>
          </div>
        </aside>
      )}

      <section className="card panel-wide">
        <div className="row-between">
          <h2>Test Cases</h2>
          <div>
            <button className="btn" disabled={busy} onClick={openCreateModal}>
              Create New Test Case
            </button>
            <button className="btn primary" disabled={busy || testCases.length === 0} onClick={runAll}>
              Run All Test Cases
            </button>
          </div>
        </div>

        {testCases.length === 0 ? (
          <p className="empty-state">No test cases yet. Click “Create New Test Case”.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Target</th>
                  <th>Runner</th>
                  <th>Auto Cron</th>
                  <th>Next Run (MYT)</th>
                  <th>Latest</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {testCases.map((c) => (
                  <tr key={c.id}>
                    <td>{c.id}</td>
                    <td>{c.name}</td>
                    <td>
                      <span className="method small">{c.endpoint_method}</span> {c.endpoint_path}
                    </td>
                    <td>{c.runner}</td>
                    <td>
                      <select
                        value={scheduleModeByCase[c.id] || 'none'}
                        onChange={(e) => onScheduleModeChange(c, e.target.value as ScheduleMode)}
                      >
                        <option value="none">None</option>
                        <option value="every_minute">Every Minute</option>
                        <option value="daily">Daily</option>
                        <option value="weekly">Weekly</option>
                        <option value="custom">Custom Cron</option>
                      </select>
                      {(scheduleModeByCase[c.id] || 'none') === 'custom' && (
                        <input
                          placeholder="*/15 * * * *"
                          value={customCronByCase[c.id] || ''}
                          onChange={(e) => onCustomCronChange(c, e.target.value)}
                        />
                      )}
                    </td>
                    <td>{formatMalaysiaDateTime(c.schedule.next_run_at)}</td>
                    <td>
                      {c.latest_run ? (
                        <span className={c.latest_run.status === 'passed' ? 'tag-pass' : 'tag-fail'}>
                          {c.latest_run.status} ({c.latest_run.trigger_type})
                        </span>
                      ) : (
                        'never'
                      )}
                    </td>
                    <td className="actions-cell">
                      <div className="actions-inline">
                        <button className="btn tiny" disabled={busy} onClick={() => runCase(c.id)}>
                          Run
                        </button>
                        <button className="btn tiny danger" disabled={busy} onClick={() => deleteCase(c.id)}>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card panel-wide">
        <h2>Execution Results</h2>
        <p>
          Passed: <strong>{runSummary.passed}</strong> | Failed: <strong>{runSummary.failed}</strong>
        </p>
        {runs.slice(0, 8).map((run) => (
          <CodeBlock
            key={run.id}
            title={`Run #${run.id} | Case #${run.case_id} (${run.case_name}) | ${run.status} | ${run.trigger_type}`}
            language="log"
            code={run.log}
          />
        ))}
      </section>

      <section className="card panel-wide">
        <h2>Status</h2>
        <p>{status}</p>
        {error && <p className="error">{error}</p>}
      </section>

      {showCreateModal && (
        <div className="modal-backdrop" onClick={() => setShowCreateModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3>Create New AI Test Case</h3>
            <label>
              Name
              <input
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="Optional custom test case name"
              />
            </label>
            <label>
              Runner
              <select value={selectedRunner} onChange={(e) => setSelectedRunner(e.target.value as TestCase['runner'])}>
                <option value="python_api">Python API</option>
                <option value="playwright_ui">Playwright UI</option>
              </select>
            </label>
            {selectedRunner === 'python_api' ? (
              <label>
                API Endpoint
                <select value={selectedEndpointKey} onChange={(e) => setSelectedEndpointKey(e.target.value)}>
                  {endpoints.map((ep) => {
                    const key = `${ep.method}|||${ep.path}`;
                    return (
                      <option key={key} value={key}>
                        {ep.method} {ep.path}
                      </option>
                    );
                  })}
                </select>
              </label>
            ) : (
              <label>
                Page
                <select value={selectedPagePath} onChange={(e) => setSelectedPagePath(e.target.value)}>
                  {pages.map((page) => (
                    <option key={page.path} value={page.path}>
                      {page.name} ({page.path})
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              AI Prompt
              <textarea
                value={createAiPrompt}
                onChange={(e) => setCreateAiPrompt(e.target.value)}
                placeholder="Describe the workflow and checks you want AI to generate for this test case."
                rows={4}
              />
            </label>
            <label>
              Auto Cron
              <select value={createScheduleMode} onChange={(e) => setCreateScheduleMode(e.target.value as ScheduleMode)}>
                <option value="none">None</option>
                <option value="every_minute">Every Minute</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="custom">Custom Cron</option>
              </select>
            </label>
            {createScheduleMode === 'custom' && (
              <label>
                Custom Cron
                <input value={createScheduleCron} onChange={(e) => setCreateScheduleCron(e.target.value)} />
              </label>
            )}

            <div className="row-between">
              <button className="btn" onClick={() => setShowCreateModal(false)}>
                Cancel
              </button>
              <button className="btn primary" disabled={busy} onClick={createCase}>
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
