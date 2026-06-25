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

export function markdownToHtml(text: string): string {
  const blocks = text.split('\n\n').filter(Boolean);
  return blocks
    .map((block) => {
      const trimmed = block.trim();

      const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/s);
      if (headingMatch) {
        const level = headingMatch[1].length;
        return `<h${level}>${inlineToHtml(headingMatch[2])}</h${level}>`;
      }

      if (/^[-*+]\s+/m.test(trimmed)) {
        const lis = trimmed
          .split('\n')
          .filter(Boolean)
          .map((item) => `<li>${inlineToHtml(item.replace(/^[-*+]\s+/, ''))}</li>`)
          .join('');
        return `<ul>${lis}</ul>`;
      }

      return `<p>${inlineToHtml(trimmed.replace(/\n/g, '<br/>'))}</p>`;
    })
    .join('\n');
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
