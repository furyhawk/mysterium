// ── Markdown export helpers ────────────────────────────────────────
// Builds a Markdown document from a research report so it can be copied
// to the clipboard or downloaded. Ported from app.js `reportToMarkdown`.

import type { ResearchReport } from '$lib/api/types';

export function reportToMarkdown(report: ResearchReport): string {
	const lines: string[] = [];

	// Title
	if (report.title) lines.push(`# ${report.title}\n`);

	// Summary
	if (report.summary) {
		lines.push('## Summary\n');
		lines.push(report.summary + '\n');
	}

	// Images
	if (report.images?.length) {
		lines.push('## Images\n');
		report.images.forEach((im) => {
			const src = im.url || `/api/images/${encodeURIComponent(im.image_id)}`;
			lines.push(`![${im.description || 'Image'}](${src})`);
			if (im.page_num != null) lines.push(`*Page ${im.page_num}*`);
			lines.push('');
		});
	}

	// Key findings
	if (report.key_findings?.length) {
		lines.push('## Key Findings\n');
		report.key_findings.forEach((f) => lines.push(`- ${f}`));
		lines.push('');
	}

	// Sections
	if (report.sections?.length) {
		report.sections.forEach((sec) => {
			lines.push(`## ${sec.heading}\n`);
			lines.push(sec.content + '\n');
			if (sec.sources?.length) {
				lines.push(`*Sources: ${sec.sources.join(', ')}*\n`);
			}
		});
	}

	// Knowledge gaps
	if (report.gaps?.length) {
		lines.push('## Knowledge Gaps\n');
		report.gaps.forEach((g) => lines.push(`- ${g}`));
		lines.push('');
	}

	// Sources
	if (report.sources?.length) {
		lines.push('## Sources\n');
		report.sources.forEach((s) => {
			lines.push(`### ${s.title}`);
			lines.push(`*${s.relevance}*`);
			lines.push(`> ${s.excerpt}`);
			lines.push('');
		});
	}

	// Timestamp
	if (report.generated_at) {
		const d = new Date(report.generated_at);
		lines.push(`---\n*Generated: ${d.toLocaleString()}*`);
	}

	return lines.join('\n');
}
