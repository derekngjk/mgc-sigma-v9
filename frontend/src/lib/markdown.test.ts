import { describe, expect, it } from 'vitest';

import { inlineToHtml, markdownToHtml, stripMarkdown } from './markdown';

describe('markdownToHtml', () => {
  it('renders blank-line-separated markdown (the well-spaced style)', () => {
    const md = [
      '## What is happening',
      '',
      'Your heart is beating too fast.',
      '',
      '## What you can do',
      '',
      '- Rest often',
      '- Take your medicine',
    ].join('\n');

    expect(markdownToHtml(md)).toBe(
      '<h2>What is happening</h2>\n' +
        '<p>Your heart is beating too fast.</p>\n' +
        '<h2>What you can do</h2>\n' +
        '<ul><li>Rest often</li><li>Take your medicine</li></ul>',
    );
  });

  it('renders tightly-spaced markdown identically (the regression case)', () => {
    // No blank lines: heading glued to its content and to the list under it.
    const md = [
      '## What is happening',
      'Your heart is beating too fast.',
      '## What you can do',
      '- Rest often',
      '- Take your medicine',
    ].join('\n');

    expect(markdownToHtml(md)).toBe(
      '<h2>What is happening</h2>\n' +
        '<p>Your heart is beating too fast.</p>\n' +
        '<h2>What you can do</h2>\n' +
        '<ul><li>Rest often</li><li>Take your medicine</li></ul>',
    );
  });

  it('does not let a heading swallow the lines beneath it', () => {
    const html = markdownToHtml('## Title\n- item');
    expect(html).toBe('<h2>Title</h2>\n<ul><li>item</li></ul>');
  });

  it('joins consecutive paragraph lines with <br/> and applies inline formatting', () => {
    const html = markdownToHtml('Line **one**\nLine two');
    expect(html).toBe('<p>Line <strong>one</strong><br/>Line two</p>');
  });

  it('supports -, *, and + list markers', () => {
    const html = markdownToHtml('- a\n* b\n+ c');
    expect(html).toBe('<ul><li>a</li><li>b</li><li>c</li></ul>');
  });

  it('ignores leading/trailing whitespace and blank lines', () => {
    const html = markdownToHtml('\n\n  # Heading  \n\n');
    expect(html).toBe('<h1>Heading</h1>');
  });
});

describe('inlineToHtml', () => {
  it('converts bold and italic', () => {
    expect(inlineToHtml('**b** and *i*')).toBe(
      '<strong>b</strong> and <em>i</em>',
    );
  });
});

describe('stripMarkdown', () => {
  it('removes headings, emphasis, and list markers', () => {
    expect(stripMarkdown('## Head\n- **bold** item')).toBe('Head\nbold item');
  });
});
