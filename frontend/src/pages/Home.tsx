import { Link } from 'react-router-dom';

export default function Home() {
  return (
    <section className="hero card">
      <h1>AI QA Copilot</h1>
      <p>
        Demo app for AI-generated QA: test generation, execution, failure analysis,
        and governed patch proposals.
      </p>
      <Link to="/demo" className="btn primary">
        Use Vessel Connect Demo
      </Link>
    </section>
  );
}
