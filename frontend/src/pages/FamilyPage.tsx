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
  image_url?: string | null;
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

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  const first = parts[0][0] ?? '';
  const last = parts.length > 1 ? parts[parts.length - 1][0] : '';
  return (first + last).toUpperCase();
}

// ── sub-components ────────────────────────────────────────────────────────────

const PAGE_BG = 'bg-gradient-to-b from-teal-50 via-white to-white';
const CARD = 'rounded-2xl bg-white shadow-sm ring-1 ring-slate-200/70';

function LoadingScreen() {
  return (
    <div className={`flex min-h-screen flex-col items-center justify-center gap-4 ${PAGE_BG}`}>
      <span className="inline-block h-9 w-9 animate-spin rounded-full border-4 border-teal-100 border-t-teal-500" />
      <p className="text-sm text-slate-400">Loading your health summary…</p>
    </div>
  );
}

function NotFoundScreen() {
  return (
    <div className={`flex min-h-screen items-center justify-center px-6 ${PAGE_BG}`}>
      <div className={`w-full max-w-sm p-8 text-center ${CARD}`}>
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-100 text-2xl">
          🔒
        </div>
        <h1 className="mb-2 text-lg font-semibold text-slate-800">Summary not available</h1>
        <p className="text-sm leading-relaxed text-slate-500">
          This link may be invalid, or your summary hasn't been finalised yet. Please check with your
          care team.
        </p>
      </div>
    </div>
  );
}

function ChangesSection({ diff }: { diff: ConditionDiff }) {
  if (diff.added.length === 0 && diff.removed.length === 0) return null;

  return (
    <section className={`p-5 ${CARD}`}>
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-700">
        <span aria-hidden="true">🔔</span> What's changed since your last update
      </h2>
      {diff.added.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-emerald-600">New</p>
          <ul className="space-y-1.5">
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
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">Resolved</p>
          <ul className="space-y-1.5">
            {diff.removed.map((c) => (
              <li key={c} className="flex items-start gap-2 text-sm text-slate-400 line-through">
                <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-slate-300" />
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function IllustrationSection({ url }: { url: string }) {
  return (
    <figure className={`overflow-hidden ${CARD}`}>
      <img
        src={url}
        alt="A calming illustration to support your care summary"
        className="w-full object-cover"
      />
      <figcaption className="px-4 py-2 text-center text-xs text-slate-400">
        A visual to support your care summary
      </figcaption>
    </figure>
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

  const showHighlightView = isPlaying || (audioUrl !== null && !isPlaying && sentences.length > 0);

  function handlePrint() {
    if (!data) return;
    const activeLangLabel = LANG_OPTIONS.find((l) => l.code === lang)?.label ?? lang.toUpperCase();
    const bodyHtml = markdownToHtml(summaryText);
    const imageHtml = data.image_url
      ? `<div class="illustration"><img src="${data.image_url}" alt="Visual aid illustration"/></div>`
      : '';
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
  .illustration{margin:1.5rem 0;text-align:center}
  .illustration img{max-width:100%;border-radius:.5rem;border:1px solid #e2e8f0}
  .footer{margin-top:2rem;font-size:.75rem;color:#94a3b8;border-top:1px solid #e2e8f0;padding-top:.75rem}
</style>
</head><body>
<p class="title">Care Summary <span class="lang">${activeLangLabel}</span></p>
<p class="meta">${data.patient_name} &mdash; Last updated ${formatDate(data.approved_at)}</p>
<hr class="divider"/>
${bodyHtml}
${imageHtml}
<div class="footer">Reviewed and approved by your care team. Synthetic data only.</div>
</body></html>`);
  }

  return (
    <div className={`min-h-screen ${PAGE_BG}`}>
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-slate-100 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-lg items-center gap-2 px-6 py-3.5">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-teal-600 text-xs font-bold text-white">
            S
          </span>
          <span className="text-sm font-semibold text-slate-800">Sigma Tech</span>
          <span className="text-slate-300">·</span>
          <span className="text-sm text-slate-500">Your Health Summary</span>
        </div>
      </header>

      {/* Body */}
      <main className="mx-auto max-w-lg space-y-5 px-4 py-6 sm:px-6">
        {/* Greeting */}
        <section className={`p-5 ${CARD}`}>
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-teal-100 text-base font-semibold text-teal-700">
              {initials(data.patient_name)}
            </div>
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-wide text-slate-400">Prepared for</p>
              <p className="truncate text-xl font-semibold text-slate-900">{data.patient_name}</p>
            </div>
          </div>
          <div className="mt-4 flex items-start gap-2 rounded-lg bg-teal-50 px-3 py-2 text-xs text-teal-700">
            <span aria-hidden="true" className="mt-px">✓</span>
            <span>Reviewed &amp; approved by your care team · Updated {formatDate(data.approved_at)}</span>
          </div>
        </section>

        {/* Visual aid illustration */}
        {data.image_url && <IllustrationSection url={data.image_url} />}

        {/* Controls: language · listen · text size */}
        <section className={`p-4 ${CARD}`}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-xs font-medium text-slate-400">Language</span>
            {LANG_OPTIONS.map(({ code, label }) => (
              <button
                key={code}
                onClick={() => handleLangChange(code)}
                disabled={translating}
                aria-pressed={lang === code}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
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
          </div>

          <div className="mt-3 flex items-center justify-between gap-3 border-t border-slate-100 pt-3">
            <button
              onClick={handlePlay}
              disabled={audioLoading || translating}
              aria-label={isPlaying ? 'Pause audio' : 'Listen to this summary'}
              className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                isPlaying
                  ? 'bg-teal-600 text-white hover:bg-teal-700'
                  : 'border border-teal-200 bg-teal-50 text-teal-700 hover:bg-teal-100'
              }`}
            >
              {audioLoading ? (
                <>
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-teal-300 border-t-teal-600" />
                  Preparing…
                </>
              ) : isPlaying ? (
                <>⏸ Pause</>
              ) : (
                <>▶ Listen</>
              )}
            </button>

            <div className="flex items-center gap-1">
              <span className="mr-1 text-xs text-slate-400">Text size</span>
              <button
                onClick={() => setFontSize((s) => Math.max(MIN_FONT, s - 2))}
                disabled={fontSize <= MIN_FONT}
                aria-label="Decrease text size"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-sm text-slate-500 hover:border-slate-400 disabled:opacity-30"
              >
                A−
              </button>
              <button
                onClick={() => setFontSize((s) => Math.min(MAX_FONT, s + 2))}
                disabled={fontSize >= MAX_FONT}
                aria-label="Increase text size"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-base font-medium text-slate-500 hover:border-slate-400 disabled:opacity-30"
              >
                A+
              </button>
            </div>
          </div>
        </section>

        {translateError && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            Translation failed: {translateError}
          </div>
        )}

        {/* Hidden audio element — controlled via audioRef */}
        {audioUrl && <audio ref={audioRef} src={audioUrl} className="hidden" />}

        {/* Summary */}
        <section className={`p-6 ${CARD}`}>
          {showHighlightView ? (
            <div className="summary-body" style={{ fontSize: `${fontSize}px`, lineHeight: 1.85 }}>
              {splitMarkdownSentences(summaryText).map((s, i) => {
                const highlighted = i === currentSentenceIdx;
                const hl = highlighted ? 'rounded bg-amber-100 px-0.5' : '';

                // Heading line
                const hMatch = s.match(/^(#{1,3})\s+(.+)$/);
                if (hMatch) {
                  const weight =
                    hMatch[1].length === 1
                      ? 'text-xl font-bold mt-6 mb-2'
                      : hMatch[1].length === 2
                        ? 'text-lg font-semibold mt-6 mb-2 border-l-4 border-teal-300 pl-3'
                        : 'text-base font-semibold mt-4 mb-1';
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
                      className={`my-1 flex gap-2 transition-colors duration-150 ${hl}`}
                    >
                      <span className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-teal-400" />
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
        </section>

        {/* Condition changes */}
        <ChangesSection diff={data.condition_diff} />

        {/* Print */}
        <div className="flex justify-center pt-1">
          <button
            onClick={handlePrint}
            className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-2 text-sm font-medium text-slate-500 transition-colors hover:border-teal-400 hover:text-teal-600"
          >
            🖨 Print summary
          </button>
        </div>

        {/* Footer */}
        <p className="pt-2 text-center text-xs leading-relaxed text-slate-400">
          This summary was reviewed and approved by your care team.
          <br />
          It uses synthetic data only and is for demonstration purposes.
        </p>
      </main>
    </div>
  );
}
