<script lang="ts">
	import { toast } from 'svelte-sonner';
	import PenLineIcon from '@lucide/svelte/icons/pen-line';
	import type { ResearchReport, PhaseEvent } from '$lib/api/types';
	import { streamSSE } from '$lib/api/sse';
	import { app, collectionNames, setResearchReport } from '$lib/app/store.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Checkbox } from '$lib/components/ui/checkbox/index.js';
	import * as Select from '$lib/components/ui/select/index.js';
	import ReportView from './ReportView.svelte';

	const models = [
		{ value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4' },
		{ value: 'claude-opus-4-20250514', label: 'Claude Opus 4' },
		{ value: 'claude-haiku-4-20250514', label: 'Claude Haiku 4' },
	];

	let query = $state('');
	let collection = $state('documents');
	let limit = $state(10);
	let model = $state(models[0].value);
	let useWeb = $state(true);
	let useWebFetch = $state(true);
	let useWebFetchLocal = $state(true);
	let generating = $state(false);
	let statusText = $state('');
	let steps = $state<{ tool: string; message: string }[]>([]);

	function addStep(evt: PhaseEvent) {
		const prev = steps[steps.length - 1];
		if (prev && prev.tool === evt.tool) return;
		steps = [...steps, { tool: evt.tool || '', message: evt.message }];
	}

	async function runResearch() {
		const q = query.trim();
		if (!q) {
			toast.error('Enter a research topic');
			return;
		}
		generating = true;
		statusText = 'Preparing the research agent…';
		steps = [];
		setResearchReport(null);

		try {
			const rep = await streamSSE<ResearchReport>(
				'/api/research/report/stream',
				{
					query: q,
					collection_name: collection,
					limit: Math.max(1, Math.min(50, Number(limit) || 10)),
					model,
					use_web: useWeb,
					use_web_fetch: useWebFetch,
					use_web_fetch_local: useWebFetchLocal,
				},
				{
					onPhase: (evt) => {
						statusText = evt.message;
						addStep(evt);
					},
				},
			);
			setResearchReport(rep);
		} catch (e) {
			setResearchReport(null);
			toast.error(
				e instanceof Error ? e.message : 'Report generation failed',
			);
		} finally {
			generating = false;
		}
	}</script>

<Card>
	<CardHeader>
		<CardTitle>Generate Research Report</CardTitle>
		<CardDescription>
			Synthesize a structured research report from RAG documents and LLM
			analysis. Uses <strong>pydantic-deep</strong> agents for structured
			synthesis.
		</CardDescription>
	</CardHeader>
	<CardContent class="flex flex-col gap-4">
		<div class="flex flex-col gap-2 sm:flex-row">
			<Input
				type="text"
				placeholder="What would you like to research?"
				bind:value={query}
				class="flex-1"
				onkeydown={(e) => {
					if (e.key === 'Enter') runResearch();
				}}
			/>
			<Button onclick={runResearch} disabled={generating}>
				<PenLineIcon />
				Generate
			</Button>
		</div>

		<div class="flex flex-wrap items-center gap-x-5 gap-y-3">
			<label class="flex items-center gap-2 text-sm text-muted-foreground">
				Collection
				<Select.Root type="single" bind:value={collection}>
					<Select.Trigger class="w-40">
						<span class="flex-1 text-left">{collection}</span>
					</Select.Trigger>
					<Select.Content>
						{#each collectionNames() as name}
							<Select.Item value={name} label={name}>{name}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</label>

			<label class="flex items-center gap-2 text-sm text-muted-foreground">
				RAG Results
				<Input
					type="number"
					bind:value={limit}
					class="h-8 w-20"
					min="1"
					max="50"
				/>
			</label>

			<label class="flex items-center gap-2 text-sm text-muted-foreground">
				Model
				<Select.Root type="single" bind:value={model}>
					<Select.Trigger class="w-48">
						<span class="flex-1 truncate text-left">
							{models.find((m) => m.value === model)?.label || model}
						</span>
					</Select.Trigger>
					<Select.Content>
						{#each models as m}
							<Select.Item value={m.value} label={m.label}>{m.label}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</label>

			<label
				class="flex cursor-pointer items-center gap-2 text-sm"
				title="Let the agent supplement RAG documents with current web sources"
			>
				<Checkbox bind:checked={useWeb} />
				<span>Web search</span>
			</label>

			<label
				class="flex cursor-pointer items-center gap-2 text-sm"
				title="Fetch and read full web pages. Off automatically for gateways that don't support it"
			>
				<Checkbox bind:checked={useWebFetch} />
				<span>Fetch pages</span>
			</label>

			<label
				class="flex cursor-pointer items-center gap-2 text-sm"
				title="Fetch pages with a local markdownify tool instead of Anthropic's server-side web-fetch tool. Works with every Anthropic-compatible gateway"
			>
				<Checkbox bind:checked={useWebFetchLocal} />
				<span>Local fetch</span>
			</label>
		</div>

		{#if generating}
			<div class="flex items-start gap-3 rounded-lg border border-border bg-background p-3">
				<span class="mt-1 size-4 shrink-0 animate-spin rounded-full border-2 border-primary border-t-transparent"></span>
				<div class="min-w-0 flex-1">
					<p class="text-sm">{statusText}</p>
					{#if steps.length}
						<ul class="mt-2 flex flex-col gap-1">
							{#each steps as step, i (i)}
								<li class="truncate text-xs text-muted-foreground">
									{step.message}
								</li>
							{/each}
						</ul>
					{/if}
				</div>
			</div>
		{/if}

		{#if app.researchReport}
			<ReportView report={app.researchReport} />
		{/if}
	</CardContent>
</Card>
