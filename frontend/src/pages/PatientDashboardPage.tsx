import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { clearPatientToken, patientFetch } from '../lib/patientSession';

// ── types ─────────────────────────────────────────────────────────────────────

interface ReportCard {
  comm_id: string;
  target_audience: string;
  approved_at: string | null;
  delivered_at: string | null;
  viewed: boolean;
  has_image: boolean;
}

interface ReportListResponse {
  patient_name: string;
  role: string;
  unread: number;
  reports: ReportCard[];
}

const ROLE_LABELS: Record<string, string> = {
  patient: 'the patient',
  spouse: 'the spouse / partner',
  child: 'an adult child',
  caregiver: 'a caregiver',
};

type PageState = 'loading' | 'error' | 'loaded';

// ── constants ─────────────────────────────────────────────────────────────────

const AUDIENCE_LABELS: Record<string, string> = {
  patient: 'For the patient',
  spouse: 'For the spouse / partner',
  child: 'For the adult child',
  caregiver: 'For the caregiver',
};

const AUDIENCE_CHIP: Record<string, string> = {
  patient: 'bg-teal-50 text-teal-700 border-teal-200',
  spouse: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  child: 'bg-violet-50 text-violet-700 border-violet-200',
  caregiver: 'bg-amber-50 text-amber-800 border-amber-200',
};

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

// ── page ──────────────────────────────────────────────────────────────────────

export default function PatientDashboardPage() {
  const navigate = useNavigate();
  const [pageState, setPageState] = useState<PageState>('loading');
  const [data, setData] = useState<ReportListResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    patientFetch('/api/account/reports')
      .then(async (res) => {
        if (res.status === 401) {
          clearPatientToken();
          navigate('/patient/login', { replace: true });
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as ReportListResponse;
        if (!cancelled) {
          setData(json);
          setPageState('loaded');
        }
      })
      .catch(() => {
        if (!cancelled) setPageState('error');
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  function signOut() {
    clearPatientToken();
    navigate('/patient/login', { replace: true });
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="border-b border-slate-100 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-lg items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-teal-600">Sigma Tech</span>
            <span className="text-slate-300">·</span>
            <span className="text-sm text-slate-500">My Reports</span>
            {data && data.unread > 0 && (
              <span className="ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-teal-600 px-1.5 text-xs font-semibold text-white">
                {data.unread}
              </span>
            )}
          </div>
          <button
            onClick={signOut}
            className="text-xs text-slate-400 hover:text-slate-600"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-lg px-6 py-8">
        {pageState === 'loading' && (
          <div className="flex justify-center py-20">
            <span className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-teal-500" />
          </div>
        )}

        {pageState === 'error' && (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            We couldn't load your reports. Please try again later.
          </div>
        )}

        {pageState === 'loaded' && data && (
          <>
            <div className="mb-6">
              <p className="text-xs text-slate-400">Reports for {data.patient_name}</p>
              <p className="text-xl font-semibold text-slate-900">Your summaries</p>
              <p className="mt-1 text-sm text-slate-500">
                Signed in as {ROLE_LABELS[data.role] ?? data.role}.{' '}
                {data.unread > 0
                  ? `You have ${data.unread} new ${data.unread === 1 ? 'report' : 'reports'}.`
                  : 'You are all caught up.'}
              </p>
            </div>

            {data.reports.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 bg-white px-6 py-12 text-center text-sm text-slate-400">
                No reports yet. Your care team will send summaries here.
              </div>
            ) : (
              <ul className="space-y-3">
                {data.reports.map((r) => (
                  <li key={r.comm_id}>
                    <button
                      onClick={() => navigate(`/patient/report/${r.comm_id}`)}
                      className="flex w-full items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-4 text-left transition-colors hover:border-teal-300 hover:bg-teal-50/40"
                    >
                      {!r.viewed && (
                        <span
                          className="h-2.5 w-2.5 flex-shrink-0 rounded-full bg-teal-500"
                          aria-label="Unread"
                        />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
                              AUDIENCE_CHIP[r.target_audience] ??
                              'bg-slate-50 text-slate-600 border-slate-200'
                            }`}
                          >
                            {AUDIENCE_LABELS[r.target_audience] ?? r.target_audience}
                          </span>
                          {!r.viewed && (
                            <span className="text-xs font-semibold uppercase tracking-wide text-teal-600">
                              New
                            </span>
                          )}
                          {r.has_image && (
                            <span className="text-xs text-slate-400">🖼 illustration</span>
                          )}
                        </div>
                        <p className={`mt-1 text-sm ${r.viewed ? 'text-slate-500' : 'font-medium text-slate-800'}`}>
                          Care summary
                        </p>
                        <p className="text-xs text-slate-400">
                          Released {formatDate(r.delivered_at ?? r.approved_at)}
                        </p>
                      </div>
                      <span className="text-slate-300">›</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </main>
    </div>
  );
}
