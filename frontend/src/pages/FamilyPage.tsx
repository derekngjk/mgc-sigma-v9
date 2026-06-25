import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { inlineToHtml, markdownToHtml, openPrintWindow, PRINT_FONT, splitMarkdownSentences } from '../lib/markdown';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ── types ─────────────────────────────────────────────────────────────────────

type PageState = 'loading' | 'not_found' | 'loaded';
type Lang = 'en' | 'zh' | 'ms' | 'ta';

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

// ── constants ─────────────────────────────────────────────────────────────────

const LANG_OPTIONS: { code: Lang; label: string }[] = [
  { code: 'en', label: 'EN' },
  { code: 'zh', label: '中文' },
  { code: 'ms', label: 'BM' },
  { code: 'ta', label: 'தமிழ்' },
];

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
  const [lang, setLang] = useState<Lang>('en');
  const [summaryText, setSummaryText] = useState('');
  const [translating, setTranslating] = useState(false);
  const [translateError, setTranslateError] = useState<string | null>(null);
  const [fontSize, setFontSize] = useState(18);
  const MIN_FONT = 14;
  const MAX_FONT = 26;

  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const [sentences, setSentences] = useState<string[]>([]);
  const [currentSentenceIdx, setCurrentSentenceIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (!fid || !mid) {
      setPageState('not_found');
      return;
    }
    fetch(`${API_BASE}/api/family/${fid}/member/${mid}`)
      .then(async (res) => {
        if (!res.ok) { setPageState('not_found'); return; }
        const json = (await res.json()) as FamilyViewData;
        setData(json);
        setSummaryText(json.ai_summary_text);
        setPageState('loaded');
      })
      .catch(() => setPageState('not_found'));
  }, [fid, mid]);

  async function handleLangChange(newLang: Lang) {
    if (newLang === lang || translating || !fid || !mid) return;
    setTranslating(true);
    setTranslateError(null);
    // Reset audio — it's stale for a different language
    setAudioUrl(null);
    setSentences([]);
    setCurrentSentenceIdx(0);
    setIsPlaying(false);
    if (audioRef.current) {
      audioRef.current.pause();
    }
    try {
      const res = await fetch(`${API_BASE}/api/family/${fid}/member/${mid}?lang=${newLang}`);
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const json = (await res.json()) as FamilyViewData;
      setSummaryText(json.ai_summary_text);
      setLang(newLang);
    } catch (e) {
      setTranslateError(e instanceof Error ? e.message : 'Translation failed');
    } finally {
      setTranslating(false);
    }
  }

  async function handlePlay() {
    if (!fid || !mid) return;
    // Toggle play/pause if audio is already loaded
    if (audioUrl && audioRef.current) {
      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
      } else {
        audioRef.current.play();
        setIsPlaying(true);
      }
      return;
    }
    setAudioLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/family/${fid}/member/${mid}/audio?lang=${lang}`);
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const payload = (await res.json()) as { url: string; sentences: string[] };
      setSentences(payload.sentences);
      setCurrentSentenceIdx(0);
      setAudioUrl(payload.url);
    } catch {
      // Audio errors are non-critical — silently ignore so the page stays usable
    } finally {
      setAudioLoading(false);
    }
  }

  useEffect(() => {
    if (!audioUrl || !audioRef.current) return;
    const audio = audioRef.current;

    // Pre-compute cumulative character offsets for proportional sentence timing
    const charOffsets: number[] = [];
    let total = 0;
    for (const s of sentences) {
      charOffsets.push(total);
      total += s.length;
    }

    const onTimeUpdate = () => {
      if (!audio.duration || total === 0) return;
      const charPos = (audio.currentTime / audio.duration) * total;
      let idx = 0;
      for (let i = 0; i < charOffsets.length - 1; i++) {
        if (charPos >= charOffsets[i]) idx = i;
      }
      setCurrentSentenceIdx(idx);
    };
    const onEnded = () => { setIsPlaying(false); setCurrentSentenceIdx(0); };
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    audio.play();

    return () => {
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('ended', onEnded);
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
    };
  }, [audioUrl]);

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
        <div className="mb-5">
          <p className="text-xs text-slate-400">Prepared for</p>
          <p className="text-xl font-semibold text-slate-900">{data.patient_name}</p>
          <p className="mt-1 text-xs text-slate-400">
            Last updated {formatDate(data.approved_at)}
          </p>
        </div>

        {/* Language toggle + font size controls */}
        <div className="mb-6 flex items-center gap-2">
          {LANG_OPTIONS.map(({ code, label }) => (
            <button
              key={code}
              onClick={() => handleLangChange(code)}
              disabled={translating}
              className={`rounded-full px-3 py-1 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                lang === code
                  ? 'bg-teal-600 text-white'
                  : 'border border-slate-200 bg-white text-slate-500 hover:border-teal-400 hover:text-teal-600'
              }`}
            >
              {label}
            </button>
          ))}
          {translating && (
            <span className="ml-1 inline-block h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-teal-500" />
          )}
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={() => setFontSize((s) => Math.max(MIN_FONT, s - 2))}
              disabled={fontSize <= MIN_FONT}
              aria-label="Decrease font size"
              className="flex h-7 w-7 items-center justify-center rounded border border-slate-200 text-sm text-slate-500 hover:border-slate-400 disabled:opacity-30"
            >
              A−
            </button>
            <button
              onClick={() => setFontSize((s) => Math.min(MAX_FONT, s + 2))}
              disabled={fontSize >= MAX_FONT}
              aria-label="Increase font size"
              className="flex h-7 w-7 items-center justify-center rounded border border-slate-200 text-base font-medium text-slate-500 hover:border-slate-400 disabled:opacity-30"
            >
              A+
            </button>
          </div>
        </div>

        {translateError && (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            Translation failed: {translateError}
          </div>
        )}

        {/* Listen button */}
        <button
          onClick={handlePlay}
          disabled={audioLoading || translating}
          className="mb-5 flex items-center gap-2 rounded-full border border-teal-200 bg-teal-50 px-4 py-1.5 text-sm font-medium text-teal-700 transition-colors hover:bg-teal-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {audioLoading ? (
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-teal-300 border-t-teal-600" />
          ) : isPlaying ? (
            '⏸ Pause'
          ) : (
            '▶ Listen'
          )}
        </button>

        {/* Hidden audio element — controlled via audioRef */}
        {audioUrl && <audio ref={audioRef} src={audioUrl} className="hidden" />}

        {/* Summary — sentence-highlight view while playing, markdown view otherwise */}
        {isPlaying || (audioUrl && !isPlaying && sentences.length > 0) ? (
          <div className="summary-body" style={{ fontSize: `${fontSize}px`, lineHeight: 1.85 }}>
            {splitMarkdownSentences(summaryText).map((s, i) => {
              const highlighted = i === currentSentenceIdx;
              const hl = highlighted ? 'rounded bg-amber-100 px-0.5' : '';

              // Heading line
              const hMatch = s.match(/^(#{1,3})\s+(.+)$/);
              if (hMatch) {
                const weight =
                  hMatch[1].length === 1
                    ? 'text-xl font-bold mt-4 mb-1'
                    : hMatch[1].length === 2
                      ? 'text-lg font-semibold mt-3 mb-1'
                      : 'text-base font-semibold mt-2 mb-0.5';
                return (
                  <div
                    key={i}
                    className={`block text-slate-900 transition-colors duration-150 ${weight} ${hl}`}
                    dangerouslySetInnerHTML={{ __html: inlineToHtml(hMatch[2]) }}
                  />
                );
              }

              // List item
              const lMatch = s.match(/^[-*+]\s+(.+)$/);
              if (lMatch) {
                return (
                  <div
                    key={i}
                    className={`my-0.5 flex gap-2 transition-colors duration-150 ${hl}`}
                  >
                    <span className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-slate-400" />
                    <span dangerouslySetInnerHTML={{ __html: inlineToHtml(lMatch[1]) }} />
                  </div>
                );
              }

              // Regular sentence — inline so consecutive sentences flow as a paragraph
              return (
                <span
                  key={i}
                  className={`transition-colors duration-150 ${hl} ${highlighted ? 'text-slate-900' : 'text-slate-600'}`}
                  dangerouslySetInnerHTML={{ __html: inlineToHtml(s) + ' ' }}
                />
              );
            })}
          </div>
        ) : (
          <div
            className={`summary-body transition-opacity ${translating ? 'opacity-40' : 'opacity-100'}`}
            style={{ fontSize: `${fontSize}px` }}
            dangerouslySetInnerHTML={{ __html: markdownToHtml(summaryText) }}
          />
        )}

        {/* Condition changes */}
        <ChangesSection diff={data.condition_diff} />

        {/* Print */}
        <div className="mt-8 flex justify-center">
          <button
            onClick={() => {
              const activeLangLabel = LANG_OPTIONS.find((l) => l.code === lang)?.label ?? lang.toUpperCase();
              const bodyHtml = markdownToHtml(summaryText);
              openPrintWindow(`<!doctype html><html><head>
<meta charset="utf-8"/>
<title>Care Summary — ${data.patient_name}</title>
<style>
  body{font-family:${PRINT_FONT};font-size:${fontSize}px;line-height:1.85;padding:2.5rem;color:#1e293b;max-width:600px;margin:0 auto}
  .title{font-size:1.25rem;font-weight:600;margin:0 0 .25rem}
  .meta{font-size:.875rem;color:#475569;margin:0 0 .25rem}
  .lang{display:inline-block;background:#f0fdfa;color:#0f766e;border:1px solid #99f6e4;border-radius:.25rem;font-size:.75rem;padding:.1rem .4rem;margin-left:.5rem}
  .divider{border:none;border-top:1px solid #e2e8f0;margin:1.25rem 0}
  h1{font-size:1.2em;font-weight:700;margin:1.25rem 0 .4rem;color:#0f172a}
  h2{font-size:1.1em;font-weight:600;margin:1rem 0 .3rem;color:#1e293b}
  h3{font-size:1em;font-weight:600;margin:.75rem 0 .25rem;color:#334155}
  p{margin:0 0 .875rem;color:#334155}
  strong{font-weight:600;color:#0f172a}
  em{font-style:italic}
  ul{margin:0 0 .875rem;padding-left:1.25rem}
  li{margin-bottom:.25rem;color:#334155}
  .footer{margin-top:2rem;font-size:.75rem;color:#94a3b8;border-top:1px solid #e2e8f0;padding-top:.75rem}
</style>
</head><body>
<p class="title">Care Summary <span class="lang">${activeLangLabel}</span></p>
<p class="meta">${data.patient_name} &mdash; Last updated ${formatDate(data.approved_at)}</p>
<hr class="divider"/>
${bodyHtml}
<div class="footer">Reviewed and approved by your care team. Synthetic data only.</div>
</body></html>`);
            }}
            className="rounded-md border border-slate-200 px-4 py-2 text-sm text-slate-500 hover:border-teal-400 hover:text-teal-600"
          >
            Print summary
          </button>
        </div>

        {/* Footer */}
        <p className="mt-8 text-center text-xs text-slate-300">
          This summary was reviewed and approved by your care team.
          It uses synthetic data only and is for demonstration purposes.
        </p>
      </main>
    </div>
  );
}
