import { useState } from 'react';
import QRCode from 'react-qr-code';
import type { Session } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import { markdownToHtml, openPrintWindow, PRINT_FONT } from '../lib/markdown';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ── types ─────────────────────────────────────────────────────────────────────

type Stage = 'idle' | 'fetching' | 'ready' | 'generating' | 'generated' | 'approving' | 'approved';

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

// Live IDs are fetched from the Synapxe HealthX FHIR R4B endpoint and must be
// provisioned first via `backend/seed_healthx.py`. The Mock ID is served from
// the local backend/mock_data fixture (offline fallback). Patients are ordered
// so the default selection has active conditions (the panel won't open on
// "None recorded"); patients whose conditions are all resolved are flagged.
const PATIENT_GROUPS = [
  {
    label: 'Live — HealthX endpoint',
    patients: [
      {
        id: 'hx-oncology-001',
        label: 'Tan Mei Ling — Breast cancer, stage III',
      },
      {
        id: '1d604da9-9a81-4ba9-80c2-de3375d59b40',
        label: 'Aaron Koh — Chronic sinusitis',
      },
      {
        id: '10339b10-3cd1-4ac3-ac13-ec26728cb592',
        label: 'Aaron Teo — Sinusitis / bronchitis / laceration (all resolved)',
      },
      {
        id: '034e9e3b-2def-4559-bb2a-7850888ae060',
        label: 'Aaron Lim — Acute bronchitis (resolved)',
      },
    ],
  },
  {
    label: 'Mock — offline fallback',
    patients: [
      {
        id: 'mock-oncology-123',
        label: 'Tan Mei Ling — Breast cancer, stage III',
      },
    ],
  },
];

const DEFAULT_PATIENT_ID = PATIENT_GROUPS[0].patients[0].id;

const AUDIENCE_OPTIONS = [
  { value: 'patient', label: 'Patient (self)' },
  { value: 'spouse', label: 'Spouse / Partner' },
  { value: 'child', label: 'Adult Child' },
  { value: 'caregiver', label: 'Caregiver' },
];

type ReportLength = 'short' | 'medium' | 'long';

const LENGTH_OPTIONS: { value: ReportLength; label: string; description: string }[] = [
  { value: 'short', label: 'Short', description: '~100 words · diagnosis + key treatment only' },
  { value: 'medium', label: 'Medium', description: '~250 words · diagnosis, treatment plan, what to expect' },
  { value: 'long', label: 'Long', description: '~450 words · full detail with changes, side effects, next steps' },
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
  length: ReportLength;
  draftText: string;
  fetchError: string | null;
  generateError: string | null;
  commId: string;
  generateImage: boolean;
  onAudienceChange: (v: string) => void;
  onLengthChange: (v: ReportLength) => void;
  onDraftChange: (v: string) => void;
  onGenerate: () => void;
  onApprove: () => void;
  onGenerateImageChange: (v: boolean) => void;
}

function AiDraftPanel({
  stage,
  audience,
  length,
  draftText,
  fetchError,
  generateError,
  commId,
  generateImage,
  onAudienceChange,
  onLengthChange,
  onDraftChange,
  onGenerate,
  onApprove,
  onGenerateImageChange,
}: AiDraftPanelProps) {
  const canGenerate = stage === 'ready' || stage === 'generated';
  const isGenerating = stage === 'generating';
  const isApproving = stage === 'approving';
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

        {/* Report length toggle */}
        <div className="mb-3">
          <p className="mb-1.5 text-xs font-medium text-slate-500">Report length</p>
          <div className="flex gap-1.5">
            {LENGTH_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => onLengthChange(opt.value)}
                disabled={isGenerating}
                title={opt.description}
                className={`rounded-md border px-3 py-1 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                  length === opt.value
                    ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                    : 'border-slate-200 bg-white text-slate-500 hover:border-indigo-300 hover:text-indigo-600'
                }`}
              >
                {opt.label}
              </button>
            ))}
            <span className="ml-2 self-center text-xs text-slate-400">
              {LENGTH_OPTIONS.find((o) => o.value === length)?.description}
            </span>
          </div>
        </div>

        {generateError && <ErrorBanner message={generateError} />}
        {fetchError && <ErrorBanner message={fetchError} />}

        {/* Draft textarea */}
        <textarea
          value={draftText}
          onChange={(e) => onDraftChange(e.target.value)}
          disabled={stage !== 'generated' || isApproving}
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

        {/* Visual aid toggle */}
        <div className={`mt-3 flex items-center justify-between rounded-lg border px-3 py-2.5 transition-colors ${
          generateImage ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-slate-50'
        } ${!canApprove ? 'opacity-50' : ''}`}>
          <div>
            <p className="text-sm font-medium text-slate-700">Visual aid illustration</p>
            <p className="text-xs text-slate-400">Generated via Nano Banana</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={generateImage}
            onClick={() => canApprove && onGenerateImageChange(!generateImage)}
            disabled={!canApprove}
            className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 disabled:cursor-not-allowed ${
              generateImage ? 'bg-emerald-500' : 'bg-slate-300'
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                generateImage ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>

        {/* Approve */}
        <button
          onClick={onApprove}
          disabled={!canApprove || isApproving}
          className="mt-3 w-full rounded-md bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
        >
          {isApproving ? (
            <span className="flex items-center justify-center gap-2">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              {generateImage ? 'Generating image…' : 'Approving…'}
            </span>
          ) : (
            '✓ Approve & Generate Link'
          )}
        </button>
      </div>
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function ClinicianPage({ session }: { session: Session }) {
  const authHeader = { Authorization: `Bearer ${session.access_token}` };
  const [selectedPatientId, setSelectedPatientId] = useState(DEFAULT_PATIENT_ID);
  const [stage, setStage] = useState<Stage>('idle');
  const [patient, setPatient] = useState<PatientData | null>(null);
  const [audience, setAudience] = useState('patient');
  const [length, setLength] = useState<ReportLength>('medium');
  const [draftText, setDraftText] = useState('');
  const [commId, setCommId] = useState('');
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [approvedLink, setApprovedLink] = useState('');
  const [generateImage, setGenerateImage] = useState(false);

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
        body: JSON.stringify({ comm_id: commId, target_audience: audience, length }),
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
    setStage('approving');
    try {
      const res = await fetch(`${API_BASE}/api/communications/${commId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify({ ai_summary_text: draftText, generate_image: generateImage }),
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
      setStage('generated');
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
            {PATIENT_GROUPS.map((group) => (
              <optgroup key={group.label} label={group.label}>
                {group.patients.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </optgroup>
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
          <div id="print-handout" className="rounded-lg border border-emerald-200 bg-emerald-50 p-8">
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-600 text-white print:bg-emerald-600">
                ✓
              </span>
              <h2 className="text-lg font-semibold text-emerald-900">Message Approved</h2>
            </div>
            {patient && (
              <p className="mt-2 text-sm font-medium text-emerald-800">
                {patient.patient_name} &mdash; {patient.dob} &bull; {patient.gender}
              </p>
            )}

            {/* QR code */}
            <div className="mt-6 flex flex-col items-center gap-3 rounded-md border border-emerald-200 bg-white p-6">
              <QRCode value={approvedLink} size={160} />
              <p className="text-center text-xs text-slate-500">
                Scan to open the care summary on a phone or tablet
              </p>
            </div>

            {/* Copyable link */}
            <p className="mt-5 text-sm text-emerald-800">Or share the link directly:</p>
            <div className="mt-2 flex items-center gap-2">
              <input
                readOnly
                value={approvedLink}
                className="flex-1 rounded-md border border-emerald-300 bg-white px-3 py-2 font-mono text-sm text-slate-700 focus:outline-none"
              />
              <button
                onClick={() => navigator.clipboard.writeText(approvedLink)}
                className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 print:hidden"
              >
                Copy
              </button>
            </div>

            {/* Actions */}
            <div className="mt-6 flex items-center gap-4">
              <button
                onClick={() => {
                  const bodyHtml = markdownToHtml(draftText);
                  openPrintWindow(`<!doctype html><html><head>
<meta charset="utf-8"/>
<title>Care Summary — ${patient?.patient_name ?? 'Patient'}</title>
<style>
  body{font-family:${PRINT_FONT};padding:2.5rem;color:#1e293b;max-width:600px;margin:0 auto}
  .title{font-size:1.25rem;font-weight:600;margin:0 0 .25rem}
  .meta{font-size:.875rem;color:#475569;margin:0 0 1.5rem}
  .divider{border:none;border-top:1px solid #e2e8f0;margin:1.25rem 0}
  h1{font-size:1.2rem;font-weight:700;margin:1.25rem 0 .4rem;color:#0f172a}
  h2{font-size:1.05rem;font-weight:600;margin:1rem 0 .3rem;color:#1e293b}
  h3{font-size:1rem;font-weight:600;margin:.75rem 0 .25rem;color:#334155}
  p{font-size:1rem;line-height:1.7;color:#334155;margin:0 0 .875rem}
  strong{font-weight:600;color:#0f172a}
  em{font-style:italic}
  ul{margin:0 0 .875rem;padding-left:1.25rem}
  li{font-size:1rem;line-height:1.7;color:#334155;margin-bottom:.25rem}
  .footer{margin-top:2rem;font-size:.75rem;color:#94a3b8;border-top:1px solid #e2e8f0;padding-top:.75rem}
</style>
</head><body>
<p class="title">Care Summary</p>
<p class="meta">${patient?.patient_name ?? ''} &mdash; ${patient?.dob ?? ''} &bull; ${patient?.gender ?? ''}</p>
<hr class="divider"/>
${bodyHtml}
<div class="footer">Reviewed and approved by your care team. Synthetic data only.</div>
</body></html>`);
                }}
                className="rounded-md border border-emerald-600 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-100"
              >
                Print Handout
              </button>
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
                  setGenerateImage(false);
                }}
                className="text-sm text-emerald-700 underline hover:text-emerald-900"
              >
                Start New Patient
              </button>
            </div>
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
            length={length}
            draftText={draftText}
            fetchError={null}
            generateError={generateError ?? approveError}
            commId={commId}
            generateImage={generateImage}
            onAudienceChange={setAudience}
            onLengthChange={setLength}
            onDraftChange={setDraftText}
            onGenerate={handleGenerate}
            onApprove={handleApprove}
            onGenerateImageChange={setGenerateImage}
          />
        </div>
      )}
    </div>
  );
}
