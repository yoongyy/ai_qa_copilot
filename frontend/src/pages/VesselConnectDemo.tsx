import { useMemo, useState } from 'react';
import CodeBlock from '../components/CodeBlock';
import UploadBox from '../components/UploadBox';

type Citation = { page: number; excerpt: string };
type TestCase = {
  id: string;
  title: string;
  gherkin: string;
  tags: string[];
  citations: Citation[];
};
type GeneratedFile = { path: string; language: string; contents: string };
type GenerateResponse = {
  workflow_summary: { title: string; detail: string; citations: Citation[] }[];
  test_cases: TestCase[];
  generated_files: GeneratedFile[];
};
type RunTestsResponse = {
  pytest: { passed: number; failed: number; log: string };
  playwright: { passed: number; failed: number; log: string };
  artifacts: string[];
};
type ProposeFixResponse = {
  root_cause: string;
  patch_diff: string;
  regression_tests: string[];
  rollout_plan: string[];
  risk_level: string;
};

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

async function api<T>(path: string, payload?: unknown): Promise<T> {
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

export default function VesselConnectDemo() {
  const [pdfBase64, setPdfBase64] = useState<string | null>(null);
  const [docId, setDocId] = useState<string>('');
  const [generated, setGenerated] = useState<GenerateResponse | null>(null);
  const [runResults, setRunResults] = useState<RunTestsResponse | null>(null);
  const [fix, setFix] = useState<ProposeFixResponse | null>(null);
  const [applyPatch, setApplyPatch] = useState(false);
  const [status, setStatus] = useState('Idle');
  const [error, setError] = useState<string | null>(null);

  const [vesselName, setVesselName] = useState('MT Demo One');
  const [port, setPort] = useState('Singapore');
  const [eta, setEta] = useState('2026-03-09T10:00:00Z');
  const [jetty, setJetty] = useState('Jetty-A1');
  const [nominationId, setNominationId] = useState('');
  const [calendarCount, setCalendarCount] = useState(0);

  const failingLogs = useMemo(() => {
    if (!runResults) return '';
    return [runResults.pytest.log, runResults.playwright.log].join('\n\n');
  }, [runResults]);

  const clearError = () => setError(null);

  const generateSuite = async () => {
    clearError();
    setStatus('Indexing document...');

    try {
      const index = await api<{ doc_id: string; chunks_count: number }>('/api/ai/index_doc',
        pdfBase64 ? { pdf_base64: pdfBase64 } : { use_sample: true }
      );

      setDocId(index.doc_id);
      setStatus(`Indexed ${index.chunks_count} chunks. Generating tests...`);

      const suite = await api<GenerateResponse>('/api/ai/generate_tests', {
        doc_id: index.doc_id,
        product: 'vessel_connect',
      });

      setGenerated(suite);
      setStatus('Test suite generated and saved to backend/generated_tests');
    } catch (e) {
      setError((e as Error).message);
      setStatus('Failed');
    }
  };

  const runTests = async () => {
    clearError();
    setStatus('Running pytest + playwright...');

    try {
      const result = await api<RunTestsResponse>('/api/tests/run');
      setRunResults(result);
      setStatus('Test run completed');
    } catch (e) {
      setError((e as Error).message);
      setStatus('Failed');
    }
  };

  const proposeFix = async () => {
    clearError();

    if (!failingLogs.trim()) {
      setError('Run tests first to capture failing logs.');
      return;
    }

    setStatus('Generating patch proposal...');
    try {
      const proposal = await api<ProposeFixResponse>('/api/ai/propose_fix', {
        failing_logs: failingLogs,
        target_files: ['backend/app/vc_api.py'],
        context_doc_id: docId || null,
      });
      setFix(proposal);
      setStatus('Patch proposal ready');
    } catch (e) {
      setError((e as Error).message);
      setStatus('Failed');
    }
  };

  const applyProposedPatch = async () => {
    clearError();
    if (!fix) return;

    if (!applyPatch) {
      setError('Tick "Apply patch (demo only)" first.');
      return;
    }

    setStatus('Applying patch...');
    try {
      await api<{ applied: boolean; message: string }>('/api/fix/apply', {
        patch_diff: fix.patch_diff,
      });
      setStatus('Patch applied. Re-running tests...');
      await runTests();
    } catch (e) {
      setError((e as Error).message);
      setStatus('Failed');
    }
  };

  const createNomination = async () => {
    clearError();
    setStatus('Creating nomination...');
    try {
      const res = await fetch(`${API_BASE}/vc/nominations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vessel_name: vesselName, port, eta }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setNominationId(data.id);
      setStatus(`Nomination ${data.id} created`);
    } catch (e) {
      setError((e as Error).message);
      setStatus('Failed');
    }
  };

  const updateSchedule = async () => {
    clearError();
    if (!nominationId) {
      setError('Create nomination first.');
      return;
    }

    setStatus('Updating schedule...');
    try {
      const res = await fetch(`${API_BASE}/vc/nominations/${nominationId}/schedule`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jetty, eta }),
      });
      if (!res.ok) throw new Error(await res.text());
      await res.json();
      setStatus('Schedule updated');
    } catch (e) {
      setError((e as Error).message);
      setStatus('Failed');
    }
  };

  const refreshCalendar = async () => {
    clearError();
    if (!nominationId) {
      setError('Create nomination first.');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/vc/nominations/${nominationId}/calendar`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setCalendarCount(data.events.length || 0);
      setStatus('Calendar refreshed');
    } catch (e) {
      setError((e as Error).message);
      setStatus('Failed');
    }
  };

  return (
    <div className="demo-grid">
      <section className="card panel-wide">
        <h2>Vessel Connect UI Surface</h2>
        <p>Used by Playwright: create nomination, update schedule, verify calendar count.</p>
        <div className="form-grid">
          <label>
            Vessel Name
            <input
              data-testid="vessel-name"
              value={vesselName}
              onChange={(e) => setVesselName(e.target.value)}
            />
          </label>
          <label>
            Port
            <input data-testid="port" value={port} onChange={(e) => setPort(e.target.value)} />
          </label>
          <label>
            ETA (ISO)
            <input data-testid="eta" value={eta} onChange={(e) => setEta(e.target.value)} />
          </label>
          <button data-testid="create-nomination" className="btn" onClick={createNomination}>
            Create Nomination
          </button>
        </div>

        <div className="form-grid">
          <label>
            Nomination ID
            <input data-testid="nomination-id" value={nominationId} readOnly />
          </label>
          <label>
            Jetty
            <input data-testid="jetty" value={jetty} onChange={(e) => setJetty(e.target.value)} />
          </label>
          <button data-testid="update-schedule" className="btn" onClick={updateSchedule}>
            Update Schedule
          </button>
          <button data-testid="refresh-calendar" className="btn" onClick={refreshCalendar}>
            Refresh Calendar
          </button>
        </div>

        <p data-testid="calendar-count">Calendar events: {calendarCount}</p>
      </section>

      <section className="card">
        <h3>A) Upload Brochure (Optional)</h3>
        <UploadBox onFile={setPdfBase64} />
        <p>{pdfBase64 ? 'PDF loaded in memory' : 'No PDF uploaded. Sample text will be used.'}</p>
      </section>

      <section className="card">
        <h3>B) Generate Test Suite</h3>
        <button className="btn primary" onClick={generateSuite}>
          Generate Test Suite
        </button>
        {generated && (
          <>
            <h4>Workflow Summary</h4>
            <ul>
              {generated.workflow_summary.map((item, idx) => (
                <li key={idx}>
                  <strong>{item.title}:</strong> {item.detail}
                </li>
              ))}
            </ul>
            <h4>Gherkin Cases ({generated.test_cases.length})</h4>
            <ul>
              {generated.test_cases.map((tc) => (
                <li key={tc.id}>
                  <strong>{tc.id}</strong> {tc.title} [{tc.tags.join(', ')}]
                </li>
              ))}
            </ul>
            {generated.generated_files.map((file) => (
              <CodeBlock key={file.path} title={file.path} language={file.language} code={file.contents} />
            ))}
          </>
        )}
      </section>

      <section className="card">
        <h3>C) Run Tests</h3>
        <button className="btn primary" onClick={runTests}>
          Run Tests
        </button>
        {runResults && (
          <>
            <p>
              Pytest: {runResults.pytest.passed} passed / {runResults.pytest.failed} failed
            </p>
            <p>
              Playwright: {runResults.playwright.passed} passed / {runResults.playwright.failed} failed
            </p>
            <CodeBlock title="Pytest Log" language="txt" code={runResults.pytest.log} />
            <CodeBlock title="Playwright Log" language="txt" code={runResults.playwright.log} />
          </>
        )}
      </section>

      <section className="card panel-wide">
        <h3>D) Propose Fix</h3>
        <button className="btn primary" onClick={proposeFix}>
          Propose Fix
        </button>
        {fix && (
          <>
            <p>
              <strong>Risk:</strong> {fix.risk_level}
            </p>
            <p>
              <strong>Root cause:</strong> {fix.root_cause}
            </p>
            <CodeBlock title="Patch Diff" language="diff" code={fix.patch_diff} />
            <h4>Regression Tests</h4>
            <ul>
              {fix.regression_tests.map((test, idx) => (
                <li key={idx}>{test}</li>
              ))}
            </ul>
            <h4>Rollout Plan</h4>
            <ul>
              {fix.rollout_plan.map((step, idx) => (
                <li key={idx}>{step}</li>
              ))}
            </ul>
            <label className="checkbox-row">
              <input type="checkbox" checked={applyPatch} onChange={(e) => setApplyPatch(e.target.checked)} />
              Apply patch (demo only)
            </label>
            <button className="btn danger" onClick={applyProposedPatch}>
              Apply Patch + Re-run
            </button>
          </>
        )}
      </section>

      <section className="card panel-wide">
        <h4>Status</h4>
        <p>{status}</p>
        {error && <p className="error">{error}</p>}
      </section>
    </div>
  );
}
