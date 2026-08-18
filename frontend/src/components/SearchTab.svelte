<script lang="ts">
	import { toast } from 'svelte-sonner';
	import SearchIcon from '@lucide/svelte/icons/search';
	import { api } from '$lib/api/client';
	import type { SearchResult } from '$lib/api/types';
	import { collectionNames } from '$lib/app/store.svelte';
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

	let query = $state('');
	let collection = $state('documents');
	let limit = $state(5);
	let rerank = $state(false);
	let results = $state<SearchResult[]>([]);
	let searching = $state(false);

	async function runSearch() {
		const q = query.trim();
		if (!q) {
			toast.error('Enter a search query');
			return;
		}
		searching = true;
		try {
			const data = await api.search(q, {
				collection,
				limit: Math.max(1, Math.min(50, Number(limit) || 5)),
				rerank,
			});
			results = data.results || [];
		} catch (e) {
			results = [];
			toast.error(e instanceof Error ? e.message : 'Search failed');
		} finally {
			searching = false;
		}
	}

	function sourceName(r: SearchResult, i: number): string {
		return r.metadata?.filename || r.parent_doc_id || `Result ${i + 1}`;
	}
</script>

<Card>
	<CardHeader>
		<CardTitle>Search Documents</CardTitle>
		<CardDescription>
			Search across your document collections using vector + hybrid search.
		</CardDescription>
	</CardHeader>
	<CardContent class="flex flex-col gap-4">
		<div class="flex flex-col gap-2 sm:flex-row">
			<Input
				type="text"
				placeholder="Search your documents…"
				bind:value={query}
				class="flex-1"
				onkeydown={(e) => {
					if (e.key === 'Enter') runSearch();
				}}
			/>
			<Button onclick={runSearch} disabled={searching}>
				<SearchIcon />
				Search
			</Button>
		</div>

		<div class="flex flex-wrap items-center gap-x-5 gap-y-3">
			<label class="flex items-center gap-2 text-sm text-muted-foreground">
				Collection
				<Select.Root type="single" bind:value={collection}>
					<Select.Trigger class="w-44">
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
				Results
				<Input
					type="number"
					bind:value={limit}
					class="h-8 w-20"
					min="1"
					max="50"
				/>
			</label>

			<label class="flex cursor-pointer items-center gap-2 text-sm">
				<Checkbox bind:checked={rerank} />
				<span>Rerank</span>
			</label>
		</div>

		<div>
			{#if searching}
				<p class="py-6 text-center text-sm text-muted-foreground">Searching…</p>
			{:else if !results.length}
				<p class="py-6 text-center text-sm text-muted-foreground">
					Enter a query to search your documents.
				</p>
			{:else}
				<ul class="flex flex-col gap-3">
					{#each results as result, i (i)}
						<li class="rounded-lg border border-border bg-card p-3">
							<div class="flex items-center justify-between gap-2">
								<span class="truncate text-sm font-medium">
									{sourceName(result, i)}
								</span>
								<span class="shrink-0 text-xs text-muted-foreground">
									Score: {(result.score * 100).toFixed(1)}%
								</span>
							</div>
							<p class="mt-2 max-h-40 overflow-hidden text-sm text-muted-foreground">
								{result.content}
							</p>
							{#if result.metadata?.page !== undefined || result.metadata?.chunk_index !== undefined}
								<p class="mt-2 text-xs text-muted-foreground">
									{#if result.metadata?.page !== undefined}
										<span>Page {result.metadata.page}</span>
									{/if}
									{#if result.metadata?.chunk_index !== undefined}
										<span class="ml-2">Chunk {result.metadata.chunk_index}</span>
									{/if}
								</p>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</CardContent>
</Card>
