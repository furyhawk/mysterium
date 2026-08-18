// ── Markdown rendering (self-contained, XSS-safe) ─────────────────
// Renders the CommonMark subset the assistant/report produces (headings,
// lists, code, bold/italic, links, images, blockquotes, tables) into HTML.
// All input is HTML-escaped first and link/image URLs are sanitized, so
// model output can never inject raw markup or script.
//
// Ported verbatim from mysterium/static/js/app.js so behaviour is identical.

function mdEscape(text: string): string {
	return String(text)
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#39;');
}

function mdSanitizeUrl(url: string): string {
	const u = (url || '').trim();
	if (!u) return '';
	// Allow fragments, relative paths (incl. /api/images/...), http(s), mailto.
	if (/^(#|\/|\.\/|\.\.\/)/.test(u)) return u;
	if (/^https?:\/\//i.test(u)) return u;
	if (/^mailto:/i.test(u)) return u;
	return '';
}

function mdInline(text: string): string {
	let t = text;
	// Inline code (protect first so other rules don't touch it)
	t = t.replace(/`([^`\n]+)`/g, (m, code) => '<code>' + code + '</code>');
	// Images ![alt](url)
	t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (m, alt, url) => {
		const src = mdSanitizeUrl(url);
		if (!src) return m;
		return '<img src="' + src + '" alt="' + alt.replace(/"/g, '&quot;') + '" loading="lazy" />';
	});
	// Links [text](url)
	t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, label, url) => {
		const href = mdSanitizeUrl(url);
		if (!href) return m;
		return '<a href="' + href + '" target="_blank" rel="noopener noreferrer">' + label + '</a>';
	});
	// Bold
	t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
	// Strikethrough
	t = t.replace(/~~([^~]+)~~/g, '<del>$1</del>');
	// Italic — only when not mid-word (avoids things like a*b*c)
	t = t.replace(/(^|[\s(])\*([^*\s][^*]*?)\*([\s).,!?;:]|$)/g, '$1<em>$2</em>$3');
	t = t.replace(/(^|[\s(])_([^_\s][^_]*?)_([\s).,!?;:]|$)/g, '$1<em>$2</em>$3');
	return t;
}

function isTableRow(line: string): boolean {
	return /^\s*\|.*\|\s*$/.test(line) && line.indexOf('|') !== -1;
}

function isTableDelimiter(line: string): boolean {
	return /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$/.test(line);
}

function tableRowCells(line: string): string[] {
	return line
		.trim()
		.replace(/^\|/, '')
		.replace(/\|$/, '')
		.split('|')
		.map((c) => c.trim());
}

export function renderMarkdown(md: string): string {
	if (!md) return '';
	const escaped = mdEscape(md);

	// Protect fenced code blocks so block/inline rules never touch them.
	const codeBlocks: string[] = [];
	const text = escaped.replace(/```[^\n]*\n([\s\S]*?)```/g, (m, code) => {
		codeBlocks.push(code);
		return '\u0000CODE\u0000' + (codeBlocks.length - 1) + '\u0000';
	});

	const lines = text.split('\n');
	const html: string[] = [];
	let i = 0;

	const isBlank = (l: string) => l.trim() === '';
	// After escaping, '>' became '&gt;'.
	const quoteRe = /^\s*&gt;\s?/;
	const hRe = /^(#{1,6})\s+(.*)$/;
	const ulRe = /^\s*[-*+]\s+/;
	const olRe = /^\s*\d+\.\s+/;
	const hrRe = /^\s*([-*_])\s*(\1\s*){2,}\s*$/;
	const isCodePlaceholder = (l: string) => /^\u0000CODE\u0000\d+\u0000$/.test(l);
	const isTableStart = (l: string, n: number) =>
		isTableRow(l) && n + 1 < lines.length && isTableDelimiter(lines[n + 1]);

	while (i < lines.length) {
		const line = lines[i];

		// Fenced code block
		if (isCodePlaceholder(line)) {
			const idx = Number(line.match(/\u0000CODE\u0000(\d+)\u0000/)?.[1] ?? 0);
			html.push('<pre><code>' + codeBlocks[idx] + '</code></pre>');
			i++;
			continue;
		}

		// Heading
		const h = line.match(hRe);
		if (h) {
			const level = h[1].length;
			html.push(`<h${level}>` + mdInline(h[2]) + `</h${level}>`);
			i++;
			continue;
		}

		// Horizontal rule
		if (hrRe.test(line)) {
			html.push('<hr/>');
			i++;
			continue;
		}

		// Blockquote (consecutive "> " lines)
		if (quoteRe.test(line)) {
			const quote: string[] = [];
			while (i < lines.length && quoteRe.test(lines[i])) {
				quote.push(lines[i].replace(quoteRe, ''));
				i++;
			}
			html.push('<blockquote>' + mdInline(quote.join('\n')) + '</blockquote>');
			continue;
		}

		// Table (a pipe row followed by a delimiter row)
		if (isTableStart(line, i)) {
			const header = tableRowCells(line);
			i += 2;
			const rows: string[] = [];
			while (i < lines.length && isTableRow(lines[i]) && lines[i].trim() !== '') {
				rows.push(
					'<tr>' +
						tableRowCells(lines[i])
							.map((c) => '<td>' + mdInline(c) + '</td>')
							.join('') +
						'</tr>',
				);
				i++;
			}
			html.push(
				'<table><thead><tr>' +
					header.map((c) => '<th>' + mdInline(c) + '</th>').join('') +
					'</tr></thead><tbody>' +
					rows.join('') +
					'</tbody></table>',
			);
			continue;
		}

		// Unordered list
		if (ulRe.test(line)) {
			const items: string[] = [];
			while (i < lines.length && ulRe.test(lines[i])) {
				items.push('<li>' + mdInline(lines[i].replace(ulRe, '')) + '</li>');
				i++;
			}
			html.push('<ul>' + items.join('') + '</ul>');
			continue;
		}

		// Ordered list
		if (olRe.test(line)) {
			const items: string[] = [];
			while (i < lines.length && olRe.test(lines[i])) {
				items.push('<li>' + mdInline(lines[i].replace(olRe, '')) + '</li>');
				i++;
			}
			html.push('<ol>' + items.join('') + '</ol>');
			continue;
		}

		// Paragraph: gather until a blank line or a new block start
		if (!isBlank(line)) {
			const para: string[] = [];
			while (
				i < lines.length &&
				!isBlank(lines[i]) &&
				!hRe.test(lines[i]) &&
				!ulRe.test(lines[i]) &&
				!olRe.test(lines[i]) &&
				!quoteRe.test(lines[i]) &&
				!hrRe.test(lines[i]) &&
				!isCodePlaceholder(lines[i]) &&
				!isTableStart(lines[i], i)
			) {
				para.push(lines[i]);
				i++;
			}
			html.push('<p>' + mdInline(para.join('<br/>')) + '</p>');
			continue;
		}

		i++; // blank line
	}

	return html.join('\n');
}
