import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ── types ─────────────────────────────────────────────────────────────────────

type PageState = 'loading' | 'not_found' | 'loaded';

interface ConditionDiff {
  added: string[];
  removed: string[];
  ongoing: string[];
}

interface FamilyViewData {
  id: string;
  patient_name: string;
  ai_summary_text: string;
  approved_at: string;
  condition_diff: ConditionDiff;
}

// ── helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
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

// ── sub-components ────────────────────────────────────────────────────────────

function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <span className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-teal-500" />
    </div>
  );
}

function NotFoundScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-6">
      <div className="max-w-sm text-center">
        <div className="mb-4 text-4xl">🔒</div>
        <h1 className="mb-2 text-lg font-semibold text-slate-800">
          Summary not available
        </h1>
        <p className="text-sm text-slate-500">
          This link may be invalid, or your summary hasn't been finalised yet.
          Please check with your care team.
        </p>
      </div>
    </div>
  );
}

function ChangesSection({ diff }: { diff: ConditionDiff }) {
  if (diff.added.length === 0 && diff.removed.length === 0) return null;

  return (
    <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        What's changed since your last update
      </h2>
      {diff.added.length > 0 && (
        <div className="mb-3">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-600">
            New
          </p>
          <ul className="space-y-1">
            {diff.added.map((c) => (
              <li key={c} className="flex items-start gap-2 text-sm text-slate-700">
                <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-emerald-400" />
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}
      {diff.removed.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Resolved
          </p>
          <ul className="space-y-1">
            {diff.removed.map((c) => (
              <li key={c} className="flex items-start gap-2 text-sm text-slate-400 line-through">
                <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-slate-300" />
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function FamilyPage() {
  const { fid, mid } = useParams<{ fid: string; mid: string }>();
  const [pageState, setPageState] = useState<PageState>('loading');
  const [data, setData] = useState<FamilyViewData | null>(null);

  useEffect(() => {
    if (!fid || !mid) {
      setPageState('not_found');
      return;
    }
    fetch(`${API_BASE}/api/family/${fid}/member/${mid}`)
      .then(async (res) => {
        if (!res.ok) {
          setPageState('not_found');
          return;
        }
        const json = (await res.json()) as FamilyViewData;
        setData(json);
        setPageState('loaded');
      })
      .catch(() => setPageState('not_found'));
  }, [fid, mid]);

  if (pageState === 'loading') return <LoadingScreen />;
  if (pageState === 'not_found' || !data) return <NotFoundScreen />;

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b border-slate-100 bg-white px-6 py-4">
        <div className="mx-auto max-w-lg">
          <span className="text-sm font-semibold text-teal-600">Sigma Tech</span>
          <span className="mx-2 text-slate-300">·</span>
          <span className="text-sm text-slate-500">Your Health Summary</span>
        </div>
      </header>

      {/* Body */}
      <main className="mx-auto max-w-lg px-6 py-8">
        {/* Meta */}
        <div className="mb-6">
          <p className="text-xs text-slate-400">Prepared for</p>
          <p className="text-xl font-semibold text-slate-900">{data.patient_name}</p>
          <p className="mt-1 text-xs text-slate-400">
            Last updated {formatDate(data.approved_at)}
          </p>
        </div>

        {/* Summary */}
        <div className="prose prose-slate max-w-none">
          {data.ai_summary_text.split('\n\n').map((para, i) => (
            <p key={i} className="mb-4 text-base leading-relaxed text-slate-700">
              {para}
            </p>
          ))}
        </div>

        {/* Condition changes */}
        <ChangesSection diff={data.condition_diff} />

        {/* Footer */}
        <p className="mt-10 text-center text-xs text-slate-300">
          This summary was reviewed and approved by your care team.
          It uses synthetic data only and is for demonstration purposes.
        </p>
      </main>
    </div>
  );
}
