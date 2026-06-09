import { useEffect, useState } from 'react';
import { Route, Routes } from 'react-router-dom';
import ClinicianPage from './pages/ClinicianPage';
import FamilyPage from './pages/FamilyPage';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

type Health = { status: string; service: string; version: string };

function WelcomeScreen() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setHealth)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-2xl px-6 py-16">
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <strong>PoC Environment:</strong> Synthetic Data Only. Do not input Real PHI.
        </div>

        <h1 className="mt-8 text-3xl font-semibold tracking-tight">MGC PoC</h1>
        <p className="mt-2 text-slate-600">
          Foundation scaffold. FHIR fetch, LLM translation, and clinician approval flow
          will land in subsequent tasks.
        </p>

        <div className="mt-8 rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Backend status
          </div>
          {health && (
            <div className="mt-2 flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-green-500" />
              <span className="text-sm">
                {health.service} v{health.version} — {health.status}
              </span>
            </div>
          )}
          {error && (
            <div className="mt-2 flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
              <span className="text-sm text-red-700">unreachable: {error}</span>
            </div>
          )}
          {!health && !error && (
            <div className="mt-2 text-sm text-slate-500">checking…</div>
          )}
        </div>

        <div className="mt-6">
          <a
            href="/clinician"
            className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Open Clinician View →
          </a>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<WelcomeScreen />} />
      <Route path="/clinician" element={<ClinicianPage />} />
      <Route path="/family/:id" element={<FamilyPage />} />
    </Routes>
  );
}
