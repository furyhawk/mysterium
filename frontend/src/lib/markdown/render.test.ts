import { describe, expect, it } from 'vitest';
import { renderMarkdown } from './render';

describe('renderMarkdown', () => {
	it('renders an empty string to an empty string', () => {
		expect(renderMarkdown('')).toBe('');
	});

	it('renders headings', () => {
		expect(renderMarkdown('# Hello')).toBe('<h1>Hello</h1>');
		expect(renderMarkdown('## Two')).toBe('<h2>Two</h2>');
		expect(renderMarkdown('###### Six')).toBe('<h6>Six</h6>');
	});

	it('renders bold and italic', () => {
		expect(renderMarkdown('**bold**')).toBe('<p><strong>bold</strong></p>');
		expect(renderMarkdown('*italic*')).toBe('<p><em>italic</em></p>');
		expect(renderMarkdown('**b** and *i*')).toBe(
			'<p><strong>b</strong> and <em>i</em></p>',
		);
	});

	it('renders paragraphs', () => {
		expect(renderMarkdown('one line')).toBe('<p>one line</p>');
		expect(renderMarkdown('a\nb')).toBe('<p>a<br/>b</p>');
	});

	it('renders unordered and ordered lists', () => {
		expect(renderMarkdown('- a\n- b')).toBe('<ul><li>a</li><li>b</li></ul>');
		expect(renderMarkdown('1. a\n2. b')).toBe('<ol><li>a</li><li>b</li></ol>');
	});

	it('renders fenced code blocks without processing inner content', () => {
		const md = '```js\nconst x = 1 < 2;\n```';
		expect(renderMarkdown(md)).toBe(
			'<pre><code>const x = 1 &lt; 2;\n</code></pre>',
		);
	});

	it('renders blockquotes', () => {
		expect(renderMarkdown('> quoted')).toBe('<blockquote>quoted</blockquote>');
	});

	it('renders tables', () => {
		const md = '| A | B |\n|---|---|\n| 1 | 2 |';
		expect(renderMarkdown(md)).toBe(
			'<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>',
		);
	});

	it('renders links with sanitization and rel', () => {
		expect(renderMarkdown('[site](https://example.com)')).toBe(
			'<p><a href="https://example.com" target="_blank" rel="noopener noreferrer">site</a></p>',
		);
		expect(renderMarkdown('[x](/api/images/abc)')).toContain(
			'href="/api/images/abc"',
		);
	});

	it('renders images with relative paths allowed', () => {
		expect(renderMarkdown('![alt](/api/images/1)')).toBe(
			'<p><img src="/api/images/1" alt="alt" loading="lazy" /></p>',
		);
	});

	describe('XSS safety', () => {
		it('escapes raw HTML', () => {
			expect(renderMarkdown('<script>alert(1)</script>')).toBe(
				'<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>',
			);
		});

		it('strips javascript: URLs from links', () => {
			expect(renderMarkdown('[x](javascript:alert(1))')).toBe(
				'<p>[x](javascript:alert(1))</p>',
			);
		});

		it('strips javascript: URLs from images', () => {
			expect(renderMarkdown('![x](javascript:alert(1))')).toBe(
				'<p>![x](javascript:alert(1))</p>',
			);
		});

		it('does not inject HTML via code spans', () => {
			expect(renderMarkdown('`<img onerror=alert(1)>`')).toBe(
				'<p><code>&lt;img onerror=alert(1)&gt;</code></p>',
			);
		});

		it('does not inject HTML via fenced code', () => {
			const md = '```\n<script>alert(1)</script>\n```';
			expect(renderMarkdown(md)).toBe(
				'<pre><code>&lt;script&gt;alert(1)&lt;/script&gt;\n</code></pre>',
			);
		});

		it('escapes quotes and angle brackets in link labels', () => {
			const out = renderMarkdown('[<b>x</b>](https://example.com)');
			expect(out).not.toContain('<b>');
			expect(out).toContain('&lt;b&gt;');
		});
	});
});
