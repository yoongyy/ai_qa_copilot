import { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export default function VesselConnectSim() {
  const [vesselName, setVesselName] = useState('');
  const [port, setPort] = useState('');
  const [eta, setEta] = useState('');

  const [nominationId, setNominationId] = useState('-');
  const [submitStatus, setSubmitStatus] = useState('Not submitted');
  const [submitPayload, setSubmitPayload] = useState('');

  const [jetty, setJetty] = useState('');
  const [scheduleEta, setScheduleEta] = useState('');
  const [scheduleStatus, setScheduleStatus] = useState('Not scheduled');
  const [calendarCount, setCalendarCount] = useState(0);

  const [submitPressed, setSubmitPressed] = useState(false);
  const [schedulePressed, setSchedulePressed] = useState(false);
  const [interactionFeed, setInteractionFeed] = useState<string[]>([]);

  const [error, setError] = useState<string | null>(null);

  const logAction = (message: string) => {
    const ts = new Date().toLocaleTimeString();
    setInteractionFeed((prev) => [`${ts} - ${message}`, ...prev].slice(0, 10));
  };

  const flashPressed = (setter: (value: boolean) => void) => {
    setter(true);
    window.setTimeout(() => setter(false), 400);
  };

  const submitNomination = async () => {
    setError(null);
    setSubmitStatus('Submitting...');
    logAction('Submitting nomination form');

    try {
      const response = await fetch(`${API_BASE}/vc/nominations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vessel_name: vesselName,
          port,
          eta,
        }),
      });

      const body = await response.json();
      if (!response.ok) {
        throw new Error(JSON.stringify(body));
      }

      setNominationId(body.id);
      setSubmitPayload(JSON.stringify(body, null, 2));
      setSubmitStatus(`Form submitted successfully (HTTP ${response.status})`);
      logAction(`Nomination created: ${body.id}`);
    } catch (e) {
      setError((e as Error).message);
      setSubmitStatus('Submit failed');
      logAction('Nomination submit failed');
    }
  };

  const updateSchedule = async () => {
    setError(null);

    if (nominationId === '-') {
      setScheduleStatus('Create nomination first');
      logAction('Schedule blocked: no nomination ID');
      return;
    }

    setScheduleStatus('Updating schedule...');
    logAction('Submitting schedule update');

    try {
      const patch = await fetch(`${API_BASE}/vc/nominations/${nominationId}/schedule`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jetty, eta: scheduleEta }),
      });

      if (!patch.ok) {
        throw new Error(await patch.text());
      }

      const calendar = await fetch(`${API_BASE}/vc/nominations/${nominationId}/calendar`);
      if (!calendar.ok) {
        throw new Error(await calendar.text());
      }

      const calendarBody = await calendar.json();
      const count = Array.isArray(calendarBody.events) ? calendarBody.events.length : 0;
      setCalendarCount(count);
      setScheduleStatus(`Schedule updated (HTTP ${patch.status})`);
      logAction(`Schedule updated, calendar events: ${count}`);
    } catch (e) {
      setError((e as Error).message);
      setScheduleStatus('Schedule failed');
      logAction('Schedule update failed');
    }
  };

  return (
    <div className="sim-layout">
      <section className="card">
        <h2>Vessel Connect Simulator</h2>
        <p>Real form flow for Playwright visual demo: blank fields, fill values, submit, then view result status.</p>

        <div className="form-grid two-col">
          <label>
            Vessel Name
            <input
              data-testid="vc-vessel-name"
              value={vesselName}
              placeholder="e.g. MT Aurora"
              onFocus={() => logAction('Focus: vessel name')}
              onChange={(e) => setVesselName(e.target.value)}
            />
          </label>

          <label>
            Port
            <input
              data-testid="vc-port"
              value={port}
              placeholder="e.g. Rotterdam"
              onFocus={() => logAction('Focus: port')}
              onChange={(e) => setPort(e.target.value)}
            />
          </label>

          <label>
            ETA (ISO)
            <input
              data-testid="vc-eta"
              value={eta}
              placeholder="e.g. 2026-03-20T09:00:00Z"
              onFocus={() => logAction('Focus: ETA')}
              onChange={(e) => setEta(e.target.value)}
            />
          </label>
        </div>

        <button
          data-testid="vc-submit"
          className={`btn primary ${submitPressed ? 'btn-pressed' : ''}`}
          onMouseEnter={() => logAction('Hover: Submit Nomination Form')}
          onMouseDown={() => flashPressed(setSubmitPressed)}
          onClick={submitNomination}
        >
          Submit Nomination Form
        </button>

        <p data-testid="vc-submit-status">
          <strong>Submit Status:</strong> {submitStatus}
        </p>
        <p>
          <strong>Nomination ID:</strong> <span data-testid="vc-nomination-id">{nominationId}</span>
        </p>

        {submitPayload && <pre>{submitPayload}</pre>}
      </section>

      <section className="card">
        <h3>Schedule Update</h3>

        <div className="form-grid two-col">
          <label>
            Jetty
            <input
              data-testid="vc-jetty"
              value={jetty}
              placeholder="e.g. Jetty-X2"
              onFocus={() => logAction('Focus: jetty')}
              onChange={(e) => setJetty(e.target.value)}
            />
          </label>

          <label>
            Schedule ETA (ISO)
            <input
              data-testid="vc-schedule-eta"
              value={scheduleEta}
              placeholder="e.g. 2026-03-20T11:00:00Z"
              onFocus={() => logAction('Focus: schedule ETA')}
              onChange={(e) => setScheduleEta(e.target.value)}
            />
          </label>
        </div>

        <button
          data-testid="vc-schedule-submit"
          className={`btn ${schedulePressed ? 'btn-pressed' : ''}`}
          onMouseEnter={() => logAction('Hover: Update Schedule')}
          onMouseDown={() => flashPressed(setSchedulePressed)}
          onClick={updateSchedule}
        >
          Update Schedule
        </button>

        <p data-testid="vc-schedule-status">
          <strong>Schedule Status:</strong> {scheduleStatus}
        </p>
        <p data-testid="vc-calendar-count">
          <strong>Calendar Events:</strong> {calendarCount}
        </p>
      </section>

      <section className="card">
        <h3>Interaction Feed</h3>
        <ul className="feed-list">
          {interactionFeed.length === 0 ? <li>Waiting for interactions...</li> : null}
          {interactionFeed.map((event, index) => (
            <li key={index}>{event}</li>
          ))}
        </ul>
      </section>

      {error && (
        <section className="card">
          <p className="error">{error}</p>
        </section>
      )}
    </div>
  );
}
