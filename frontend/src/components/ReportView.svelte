<script lang="ts">
	import { toast } from 'svelte-sonner';
	import CopyIcon from '@lucide/svelte/icons/copy';
	import CheckIcon from '@lucide/svelte/icons/check';
	import DownloadIcon from '@lucide/svelte/icons/download';
	import type { ResearchReport, ReportImage } from '$lib/api/types';
	import { reportToMarkdown } from '$lib/markdown/export';
	import { downloadFile } from '$lib/utils';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Dialog from '$lib/components/ui/dialog/index.js';

	let { report }: { report: ResearchReport } = $props();

	let copied = $state(false);
	let lightbox = $state<ReportImage | null>(null);

	function openLightbox(im: ReportImage) {
		lightbox = im;
	}

	const md = $derived(reportToMarkdown(report));

	async function copyMarkdown() {
		try {
			await navigator.clipboard.writeText(md);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch {
			toast.error('Failed to copy — browser may not support clipboard API');
		}
	}

	function download() {
		if (!report.report_id) return;
		downloadFile(
			`/api/history/reports/${encodeURIComponent(report.report_id)}/export?format=md`,
		).catch((e) =>
			toast.error(e instanceof Error ? e.message : 'Download failed'),
		);
	}
</script>

<div class="rounded-lg border border-border bg-card p-4 sm:p-5">
	<div class="mb-4 flex flex-wrap items-center justify-between gap-2">
		<h2 class="text-lg font-semibold">{report.title}</h2>
		<div class="flex items-center gap-2">
			{#if report.report_id}
				<span class="text-xs text-muted-foreground" title="Saved to history">
					✓ Saved
				</span>
			{/if}
			<Button variant="outline" size="sm" onclick={copyMarkdown}>
				{#if copied}
					<CheckIcon />
					Copied!
				{:else}
					<CopyIcon />
					Copy Markdown
				{/if}
			</Button>
			<Button
				variant="outline"
				size="sm"
				onclick={download}
				disabled={!report.report_id}
				title={report.report_id
					? 'Download as Markdown'
					: 'This report was not saved to history'}
			>
				<DownloadIcon />
				Download
			</Button>
		</div>
	</div>

	{#if report.summary}
		<p class="mb-4 whitespace-pre-line text-sm">{report.summary}</p>
	{/if}

	{#if report.images?.length}
		<h3 class="mb-2 mt-4 text-sm font-semibold">🖼️ Images</h3>
		<div class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
			{#each report.images as im (im.image_id)}
				<figure class="min-w-0">
					<button
						type="button"
						class="block w-full cursor-zoom-in overflow-hidden rounded-md border border-border outline-none focus-visible:ring-2 focus-visible:ring-ring"
						title="Click to enlarge"
						onclick={() => openLightbox(im)}
					>
						<img
							src={`/api/images/${encodeURIComponent(im.image_id)}`}
							alt={im.description || 'Report image'}
							loading="lazy"
							class="w-full"
						/>
					</button>
					{#if im.description}
						<figcaption class="mt-1 text-xs text-muted-foreground">
							{im.description}
							{#if im.page_num != null} — p.{im.page_num}{/if}
						</figcaption>
					{/if}
				</figure>
			{/each}
		</div>
	{/if}

	{#if report.key_findings?.length}
		<h3 class="mb-2 mt-4 text-sm font-semibold">🔑 Key Findings</h3>
		<ul class="mb-4 ml-5 list-disc">
			{#each report.key_findings as finding}
				<li class="text-sm">{finding}</li>
			{/each}
		</ul>
	{/if}

	{#each report.sections || [] as section}
		<div class="mb-4">
			<h3 class="mb-1 text-base font-semibold">{section.heading}</h3>
			<p class="whitespace-pre-line text-sm">{section.content}</p>
			{#if section.sources?.length}
				<p class="mt-1.5 text-xs text-muted-foreground">
					Sources: {section.sources.join(', ')}
				</p>
			{/if}
		</div>
	{/each}

	{#if report.gaps?.length}
		<h3 class="mb-2 mt-4 text-sm font-semibold">⚠️ Knowledge Gaps</h3>
		<ul class="mb-4 ml-5 list-disc">
			{#each report.gaps as gap}
				<li class="text-sm">{gap}</li>
			{/each}
		</ul>
	{/if}

	{#if report.sources?.length}
		<h3 class="mb-2 mt-4 text-sm font-semibold">📚 Sources</h3>
		<div class="mb-4 flex flex-col gap-3">
			{#each report.sources as source}
				<div class="rounded-md border border-border bg-background p-3">
					<p class="text-sm font-medium">{source.title}</p>
					<p class="text-xs text-muted-foreground">{source.relevance}</p>
					<p class="mt-1 text-sm italic">"{source.excerpt}"</p>
				</div>
			{/each}
		</div>
	{/if}

	{#if report.generated_at}
		<p class="mt-4 text-xs text-muted-foreground">
			Generated: {new Date(report.generated_at).toLocaleString()}
		</p>
	{/if}
</div>

<Dialog.Root
	open={lightbox !== null}
	onOpenChange={(o) => {
		if (!o) lightbox = null;
	}}
>
	<Dialog.Content
		class="w-[92vw] max-w-[92vw] p-3 sm:max-w-6xl"
		showCloseButton={false}
	>
		{#if lightbox}
			<img
				src={`/api/images/${encodeURIComponent(lightbox.image_id)}`}
				alt={lightbox.description || 'Report image'}
				class="mx-auto max-h-[85vh] w-full rounded-md object-contain"
			/>
			{#if lightbox.description}
				<p class="text-sm text-muted-foreground">
					{lightbox.description}
					{#if lightbox.page_num != null} — p.{lightbox.page_num}{/if}
				</p>
			{/if}
		{/if}
	</Dialog.Content>
</Dialog.Root>
