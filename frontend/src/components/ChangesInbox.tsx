import { useCallback, useEffect, useState } from 'react';

interface ConditionDiff {
  added: string[];
  removed: string[];
  ongoing: string[];
}

export interface ChangeInboxItem {
  comm_id: string;
  patient_name: string;
  epic_patient_id: string;
  target_audience: string;
  conditions: string[];
  condition_diff: ConditionDiff;
  ai_summary_text: string;
  fhir_source: string;
  detected_at: string | null;
}

interface ChangesInboxProps {
  apiBase: string;
  authHeader: Record<string, string>;
  /** Load a detected draft into the editor for review + approval. */
  onOpen: (item: ChangeInboxItem) => void;
}

const AUDIENCE_LABELS: Record<string, string> = {
  patient: 'Patient',
  spouse: 'Spouse / Partner',
  child: 'Adult Child',
  caregiver: 'Caregiver',
};

/**
 * Clinician inbox for change-detected drafts. A scheduled scan re-fetches watched
 * patients from Epic, and when their conditions changed it auto-creates a Draft with the
 * updated summary already generated. Each row opens that draft in the normal review flow
 * the clinician still approves before anything reaches the family.
 */
export function ChangesInbox({ apiBase, authHeader, onOpen }: ChangesInboxProps) {
  const [items, setItems] = useState<ChangeInboxItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/api/changes`, { headers: authHeader });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as { items: ChangeInboxItem[] };
      setItems(data.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
    // authHeader is a fresh object each render; depending on it would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        Couldn&apos;t load detected updates: {error}
      </div>
    );
  }

  if (!loading && items.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">
        No updates detected from Epic. A scheduled scan drafts a report here whenever a
        watched patient&apos;s conditions change.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-indigo-200 bg-white">
      <div className="flex items-center justify-between border-b border-indigo-100 bg-indigo-50 px-4 py-2.5">
        <span className="text-xs font-semibold uppercase tracking-wide text-indigo-700">
          Updates detected from Epic
          {items.length > 0 && (
            <span className="ml-2 rounded-full bg-indigo-600 px-2 py-0.5 text-xs font-semibold text-white">
              {items.length}
            </span>
          )}
        </span>
        <button
          onClick={() => load()}
          className="text-xs text-indigo-600 hover:text-indigo-800"
        >
          Refresh
        </button>
      </div>
      <ul className="divide-y divide-slate-100">
        {items.map((item) => (
          <li key={item.comm_id} className="flex items-center justify-between gap-4 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-900">
                {item.patient_name || item.epic_patient_id}
                <span className="ml-2 rounded-sm bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-500">
                  {AUDIENCE_LABELS[item.target_audience] ?? item.target_audience}
                </span>
              </p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {item.condition_diff.added.map((c) => (
                  <span
                    key={`a-${c}`}
                    className="rounded-sm bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-800"
                  >
                    + {c}
                  </span>
                ))}
                {item.condition_diff.removed.map((c) => (
                  <span
                    key={`r-${c}`}
                    className="rounded-sm bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-500 line-through"
                  >
                    − {c}
                  </span>
                ))}
                {!item.ai_summary_text && (
                  <span className="rounded-sm bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800">
                    summary not generated
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={() => onOpen(item)}
              className="flex-shrink-0 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
            >
              Review &amp; approve
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
