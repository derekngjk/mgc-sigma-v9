import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { API_BASE, setPatientToken } from '../lib/patientSession';

type Stage = 'idle' | 'submitting';

const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: 'patient', label: 'Patient (myself)' },
  { value: 'spouse', label: 'Spouse / Partner' },
  { value: 'child', label: 'Adult child' },
  { value: 'caregiver', label: 'Caregiver' },
];

export default function PatientRegisterPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('patient');
  const [patientName, setPatientName] = useState('');
  const [patientNric, setPatientNric] = useState('');
  const [stage, setStage] = useState<Stage>('idle');
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStage('submitting');
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/account/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          password,
          role,
          patient_full_name: patientName,
          patient_nric: patientNric,
        }),
      });
      if (!res.ok) {
        if (res.status === 404)
          throw new Error("No patient found with that name + NRIC. Check the details, or ask the care team to register the patient first.");
        if (res.status === 409) throw new Error('That email is already registered. Try signing in.');
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as { token: string };
      setPatientToken(data.token);
      navigate('/patient', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
      setStage('idle');
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-teal-600">
            Sigma Tech · Patient &amp; Family Portal
          </p>
          <h1 className="mt-1 text-xl font-semibold text-slate-900">Create your account</h1>
          <p className="mt-1 text-sm text-slate-500">
            You'll see the summaries written for your role.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-slate-700">
              Your email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder-slate-400 focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-slate-700">
              Choose a password
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 6 characters"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder-slate-400 focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
            />
          </div>

          <div>
            <label htmlFor="role" className="mb-1 block text-sm font-medium text-slate-700">
              Your role
            </label>
            <select
              id="role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
            >
              {ROLE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              Link to the patient
            </p>
            <div className="space-y-3">
              <div>
                <label htmlFor="patient-name" className="mb-1 block text-sm font-medium text-slate-700">
                  Patient's full name
                </label>
                <input
                  id="patient-name"
                  type="text"
                  required
                  value={patientName}
                  onChange={(e) => setPatientName(e.target.value)}
                  placeholder="As registered, e.g. Tan Mei Ling"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm placeholder-slate-400 focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
                />
              </div>
              <div>
                <label htmlFor="patient-nric" className="mb-1 block text-sm font-medium text-slate-700">
                  Patient's NRIC
                </label>
                <input
                  id="patient-nric"
                  type="text"
                  required
                  value={patientNric}
                  onChange={(e) => setPatientNric(e.target.value)}
                  placeholder="e.g. S1234567A"
                  autoCapitalize="characters"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm uppercase placeholder-slate-400 focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
                />
              </div>
            </div>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={stage === 'submitting'}
            className="w-full rounded-md bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-700 disabled:opacity-50"
          >
            {stage === 'submitting' ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-slate-500">
          Already have an account?{' '}
          <Link to="/patient/login" className="font-medium text-teal-600 hover:text-teal-700">
            Sign in
          </Link>
        </p>

        <p className="mt-6 text-center text-xs text-slate-400">
          PoC environment · Synthetic data only
        </p>
      </div>
    </div>
  );
}
