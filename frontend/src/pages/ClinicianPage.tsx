import { useState } from 'react';
import type { Session } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ── types ─────────────────────────────────────────────────────────────────────

type Stage = 'idle' | 'fetching' | 'ready' | 'generating' | 'generated' | 'approved';

interface ConditionDiff {
  added: string[];
  removed: string[];
  ongoing: string[];
}

interface PatientData {
  epic_patient_id: string;
  patient_name: string;
  dob: string;
  gender: string;
  conditions: string[];
  comm_id: string;
  fhir_source: string;
  condition_diff: ConditionDiff;
}

// ── constants ─────────────────────────────────────────────────────────────────

const PATIENTS = [
  {
    id: 'mock-oncology-123',
    label: 'Elena Vasquez — Breast cancer, stage III (Mock)',
  },
  {
    id: 'mock-cardiology-456',
    label: 'Marcus Thompson — Heart failure, T2DM (Mock)',
  },
  {
    id: 'mock-pediatric-789',
    label: 'Lily Chen — Paediatric ALL maintenance (Mock)',
  },
  {
    id: 'mock-neurology-101',
    label: 'Amara Osei — Relapsing-remitting MS (Mock)',
  },
  {
    id: 'mock-geriatric-202',
    label: 'Robert Kim — Alzheimer\'s, AFib, osteoporosis (Mock)',
  },
  {
    id: 'eovIMNNn7tHBQwLGAXNRRw3',
    label: 'eovIMNNn7tHBQwLGAXNRRw3 (Epic Open Sandbox)',
  },
];

const AUDIENCE_OPTIONS = [
  { value: 'family', label: 'Family' },
  { value: 'patient', label: 'Patient' },
];

// ── sub-components ────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      {message}
    </div>
  );
}

function ClinicalDataPanel({ patient }: { patient: PatientData }) {
  return (
    <div className="flex h-full flex-col">
      <div className="rounded-t-lg bg-slate-100 px-4 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          Clinical Data
        </span>
        <span className="ml-2 rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-500">
          {patient.fhir_source}
        </span>
      </div>
      <div className="flex-1 rounded-b-lg border border-t-0 border-slate-200 bg-white p-4">
        <div className="mb-4">
          <p className="text-base font-semibold text-slate-900">{patient.patient_name}</p>
          <p className="text-sm text-slate-500">
            DOB: {patient.dob || '—'} &nbsp;·&nbsp; {patient.gender || '—'}
          </p>
        </div>

        <div className="mb-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Active Conditions
          </p>
          {patient.conditions.length === 0 ? (
            <p className="text-sm text-slate-400">None recorded</p>
          ) : (
            <ul className="space-y-1">
              {patient.condition_diff.added.map((c) => (
                <li key={c} className="flex items-start gap-2 text-sm text-slate-700">
                  <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-emerald-400" />
                  {c}
                  <span className="ml-1 rounded-sm bg-emerald-100 px-1 py-0.5 text-xs font-semibold uppercase text-emerald-700">
                    New
                  </span>
                </li>
              ))}
              {patient.condition_diff.ongoing.map((c) => (
                <li key={c} className="flex items-start gap-2 text-sm text-slate-700">
                  <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-indigo-400" />
                  {c}
                  {(patient.condition_diff.added.length > 0 ||
                    patient.condition_diff.removed.length > 0) && (
                    <span className="ml-1 rounded-sm bg-slate-100 px-1 py-0.5 text-xs font-semibold uppercase text-slate-500">
                      Ongoing
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {patient.condition_diff.removed.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Resolved since last report
              </p>
              <ul className="space-y-1">
                {patient.condition_diff.removed.map((c) => (
                  <li key={c} className="flex items-start gap-2 text-sm text-slate-400 line-through">
                    <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-slate-300" />
                    {c}
                    <span className="ml-1 rounded-sm bg-slate-100 px-1 py-0.5 text-xs font-semibold uppercase text-slate-400 no-underline" style={{ textDecoration: 'none' }}>
                      Resolved
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface AiDraftPanelProps {
  stage: Stage;
  audience: string;
  draftText: string;
  fetchError: string | null;
  generateError: string | null;
  commId: string;
  onAudienceChange: (v: string) => void;
  onDraftChange: (v: string) => void;
  onGenerate: () => void;
  onApprove: () => void;
}

function AiDraftPanel({
  stage,
  audience,
  draftText,
  fetchError,
  generateError,
  commId,
  onAudienceChange,
  onDraftChange,
  onGenerate,
  onApprove,
}: AiDraftPanelProps) {
  const canGenerate = stage === 'ready' || stage === 'generated';
  const isGenerating = stage === 'generating';
  const canApprove = stage === 'generated' && draftText.trim().length > 0;

  return (
    <div className="flex h-full flex-col">
      <div className="rounded-t-lg bg-slate-100 px-4 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          AI Draft
        </span>
      </div>
      <div className="flex flex-1 flex-col rounded-b-lg border border-t-0 border-slate-200 bg-white p-4">
        {/* Audience + Generate */}
        <div className="mb-3 flex items-center gap-3">
          <label className="text-sm font-medium text-slate-600" htmlFor="audience">
            Audience
          </label>
          <select
            id="audience"
            value={audience}
            onChange={(e) => onAudienceChange(e.target.value)}
            disabled={isGenerating}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {AUDIENCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>

          <button
            onClick={onGenerate}
            disabled={!canGenerate || isGenerating}
            className="ml-auto flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
          >
            {isGenerating ? (
              <>
                <Spinner /> Generating…
              </>
            ) : (
              'Generate Summary'
            )}
          </button>
        </div>

        {generateError && <ErrorBanner message={generateError} />}
        {fetchError && <ErrorBanner message={fetchError} />}

        {/* Draft textarea */}
        <textarea
          value={draftText}
          onChange={(e) => onDraftChange(e.target.value)}
          disabled={stage !== 'generated'}
          placeholder={
            stage === 'ready'
              ? 'Click "Generate Summary" to create an AI draft…'
              : stage === 'generating'
                ? 'Generating…'
                : 'Select a patient and fetch data first.'
          }
          className="mt-1 flex-1 resize-none rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-800 placeholder-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400 disabled:cursor-default disabled:opacity-60"
          rows={10}
        />

        {/* Comm ID display (for debugging / Task 4.2 wiring) */}
        {commId && (
          <p className="mt-2 text-xs text-slate-400">
            Record ID: <span className="font-mono">{commId}</span>
          </p>
        )}

        {/* Approve */}
        <button
          onClick={onApprove}
          disabled={!canApprove}
          className="mt-4 w-full rounded-md bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
        >
          ✓ Approve &amp; Generate Link
        </button>
      </div>
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function ClinicianPage({ session }: { session: Session }) {
  const authHeader = { Authorization: `Bearer ${session.access_token}` };
  const [selectedPatientId, setSelectedPatientId] = useState(PATIENTS[0].id);
  const [stage, setStage] = useState<Stage>('idle');
  const [patient, setPatient] = useState<PatientData | null>(null);
  const [audience, setAudience] = useState('family');
  const [draftText, setDraftText] = useState('');
  const [commId, setCommId] = useState('');
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [approvedLink, setApprovedLink] = useState('');

  async function handleFetch() {
    setStage('fetching');
    setPatient(null);
    setDraftText('');
    setCommId('');
    setFetchError(null);
    setGenerateError(null);

    try {
      const res = await fetch(`${API_BASE}/api/patient/${selectedPatientId}`, {
        headers: authHeader,
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as PatientData;
      setPatient(data);
      setCommId(data.comm_id);
      setStage('ready');
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : 'Unknown error');
      setStage('idle');
    }
  }

  async function handleGenerate() {
    if (!commId) return;
    setStage('generating');
    setGenerateError(null);

    try {
      const res = await fetch(`${API_BASE}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify({ comm_id: commId, target_audience: audience }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as { ai_summary_text: string };
      setDraftText(data.ai_summary_text);
      setStage('generated');
    } catch (e) {
      setGenerateError(e instanceof Error ? e.message : 'Unknown error');
      setStage('ready');
    }
  }

  async function handleApprove() {
    setApproveError(null);
    try {
      const res = await fetch(`${API_BASE}/api/communications/${commId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify({ ai_summary_text: draftText }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as { family_link: string };
      setApprovedLink(data.family_link);
      setStage('approved');
    } catch (e) {
      setApproveError(e instanceof Error ? e.message : 'Unknown error');
    }
  }

  const isFetching = stage === 'fetching';

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {/* Top bar */}
      <header className="bg-slate-800 px-6 py-3">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-white">Sigma Tech v9</span>
            <span className="text-slate-500">/</span>
            <span className="text-sm text-slate-300">Clinician View</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-amber-500 px-2.5 py-0.5 text-xs font-medium text-amber-950">
              PoC · Synthetic Data Only
            </span>
            <button
              onClick={() => supabase.auth.signOut()}
              className="text-xs text-slate-400 hover:text-slate-200"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* PHI banner */}
      <div className="border-b border-amber-300 bg-amber-50 px-6 py-2 text-center text-xs text-amber-800">
        <strong>Warning:</strong> Do not enter real patient data. This environment uses synthetic
        Epic Sandbox data only.
      </div>

      {/* Patient selector */}
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-6xl items-center gap-4">
          <label className="text-sm font-medium text-slate-600" htmlFor="patient-select">
            Patient
          </label>
          <select
            id="patient-select"
            value={selectedPatientId}
            onChange={(e) => {
              setSelectedPatientId(e.target.value);
              setStage('idle');
              setPatient(null);
              setDraftText('');
              setFetchError(null);
              setGenerateError(null);
              setApproveError(null);
              setApprovedLink('');
            }}
            disabled={isFetching}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {PATIENTS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>

          <button
            onClick={handleFetch}
            disabled={isFetching}
            className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
          >
            {isFetching ? (
              <>
                <Spinner /> Fetching…
              </>
            ) : (
              'Fetch Patient Data'
            )}
          </button>

          {fetchError && !patient && (
            <span className="text-sm text-red-600">{fetchError}</span>
          )}
        </div>
      </div>

      {/* Main content */}
      {stage === 'idle' && !patient && (
        <div className="mx-auto max-w-6xl px-6 py-20 text-center text-slate-400">
          Select a patient and click <strong>Fetch Patient Data</strong> to begin.
        </div>
      )}

      {/* Approved success card */}
      {stage === 'approved' && (
        <div className="mx-auto max-w-2xl px-6 py-16">
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-8">
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-600 text-white">
                ✓
              </span>
              <h2 className="text-lg font-semibold text-emerald-900">Message Approved</h2>
            </div>
            <p className="mt-4 text-sm text-emerald-800">
              Share this link with the patient's family:
            </p>
            <div className="mt-3 flex items-center gap-2">
              <input
                readOnly
                value={approvedLink}
                className="flex-1 rounded-md border border-emerald-300 bg-white px-3 py-2 font-mono text-sm text-slate-700 focus:outline-none"
              />
              <button
                onClick={() => navigator.clipboard.writeText(approvedLink)}
                className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700"
              >
                Copy
              </button>
            </div>
            <button
              onClick={() => {
                setStage('idle');
                setPatient(null);
                setDraftText('');
                setCommId('');
                setApprovedLink('');
                setApproveError(null);
                setFetchError(null);
                setGenerateError(null);
              }}
              className="mt-6 text-sm text-emerald-700 underline hover:text-emerald-900"
            >
              Start New Patient
            </button>
          </div>
        </div>
      )}

      {/* Two-column workflow */}
      {patient && stage !== 'approved' && (
        <div className="mx-auto grid max-w-6xl grid-cols-2 gap-6 px-6 py-6">
          <ClinicalDataPanel patient={patient} />
          <AiDraftPanel
            stage={stage}
            audience={audience}
            draftText={draftText}
            fetchError={null}
            generateError={generateError ?? approveError}
            commId={commId}
            onAudienceChange={setAudience}
            onDraftChange={setDraftText}
            onGenerate={handleGenerate}
            onApprove={handleApprove}
          />
        </div>
      )}
    </div>
  );
}
