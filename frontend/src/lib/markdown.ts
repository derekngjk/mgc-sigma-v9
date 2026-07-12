export function inlineToHtml(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/gs, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/gs, '<em>$1</em>');
}

/** Split text into sentences while preserving markdown — mirrors backend split_sentences(). */
export function splitMarkdownSentences(text: string): string[] {
  const result: string[] = [];
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const parts = trimmed.split(/(?<=[.!?])\s+/);
    result.push(...parts.filter((p) => p.trim()));
  }
  return result;
}

// Line-based so blocks separate on a heading / list / blank-line boundary, not only
// on blank lines — some LLMs emit valid but tightly-spaced markdown (no blank line
// between a heading and the list under it) that a blank-line-only split mis-groups.
export function markdownToHtml(text: string): string {
  const blocks: string[] = [];
  let paragraph: string[] = [];
  let items: string[] = [];

  const flushParagraph = (): void => {
    if (paragraph.length) {
      blocks.push(`<p>${paragraph.map(inlineToHtml).join('<br/>')}</p>`);
      paragraph = [];
    }
  };
  const flushList = (): void => {
    if (items.length) {
      const lis = items.map((item) => `<li>${inlineToHtml(item)}</li>`).join('');
      blocks.push(`<ul>${lis}</ul>`);
      items = [];
    }
  };
  const flush = (): void => {
    flushParagraph();
    flushList();
  };

  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    if (!line) {
      flush();
      continue;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      flush();
      const level = headingMatch[1].length;
      blocks.push(`<h${level}>${inlineToHtml(headingMatch[2])}</h${level}>`);
      continue;
    }

    const listMatch = line.match(/^[-*+]\s+(.+)$/);
    if (listMatch) {
      flushParagraph();
      items.push(listMatch[1]);
      continue;
    }

    flushList();
    paragraph.push(line);
  }

  flush();
  return blocks.join('\n');
}

// Inlined print trigger is more reliable than cross-window load events.
const PRINT_SCRIPT = `<script>window.onload=function(){window.print();}<\/script>`;

// CJK-aware font stack — system-ui alone drops Chinese/Tamil on some systems.
export const PRINT_FONT =
  "system-ui,-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC',sans-serif";

export function openPrintWindow(html: string): void {
  const withPrint = html.replace('</body>', `${PRINT_SCRIPT}</body>`);
  const blob = new Blob([withPrint], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank');
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/\*\*(.+?)\*\*/gs, '$1')
    .replace(/\*(.+?)\*/gs, '$1')
    .replace(/^[-*+]\s+/gm, '')
    .trim();
}
