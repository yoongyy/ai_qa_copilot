import { Link, Route, Routes } from 'react-router-dom';
import QADashboard from './pages/QADashboard';
import VesselConnectSim from './pages/VesselConnectSim';

export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>AI QA Copilot</h1>
        <p>Target-driven AI test generation (API + page), execution, scheduling, and auditable results.</p>
        <nav className="top-nav">
          <Link to="/" className="nav-link">
            QA Dashboard
          </Link>
          <Link to="/vessel-connect" className="nav-link">
            Vessel Connect Simulator
          </Link>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<QADashboard />} />
          <Route path="/demo" element={<QADashboard />} />
          <Route path="/vessel-connect" element={<VesselConnectSim />} />
        </Routes>
      </main>
    </div>
  );
}
