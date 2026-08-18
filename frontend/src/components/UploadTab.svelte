<script lang="ts">
	import { toast } from 'svelte-sonner';
	import UploadCloudIcon from '@lucide/svelte/icons/upload-cloud';
	import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw';
	import Trash2Icon from '@lucide/svelte/icons/trash-2';
	import { api } from '$lib/api/client';
	import type { DocItem } from '$lib/api/types';
	import { collectionNames, setNavStatus } from '$lib/app/store.svelte';
	import { formatDateShort, formatSize, fileIcon } from '$lib/utils';
	import { Button } from '$lib/components/ui/button/index.js';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Select from '$lib/components/ui/select/index.js';

	interface UploadItem {
		name: string;
		size: number;
		status: 'loading' | 'success' | 'error';
		message?: string;
	}

	let uploadCollection = $state('documents');
	let uploads = $state<UploadItem[]>([]);
	let docs = $state<DocItem[]>([]);
	let docFilter = $state('');
	let dragging = $state(false);
	let fileInput: HTMLInputElement | undefined = $state();

	async function loadDocuments() {
		try {
			const data = await api.documents({ collection: docFilter || undefined });
			docs = data.items;
			const counts: Record<string, number> = {};
			for (const d of docs) counts[d.status] = (counts[d.status] || 0) + 1;
			setNavStatus(
				Object.entries(counts)
					.map(([k, v]) => `${v} ${k}`)
					.join(' · ') || '',
			);
		} catch (e) {
			docs = [];
			console.warn('Failed to load documents:', e);
		}
	}

	async function handleUpload(files: FileList | File[]) {
		const list = Array.from(files);
		for (const file of list) {
			const item: UploadItem = {
				name: file.name,
				size: file.size,
				status: 'loading',
			};
			uploads = [...uploads, item];
			try {
				const res = await api.upload(file, uploadCollection);
				item.status = 'success';
				item.message = res.status || 'uploaded';
			} catch (e) {
				item.status = 'error';
				item.message = e instanceof Error ? e.message : 'Upload failed';
			}
			uploads = uploads.map((u) => (u === item ? item : u));
		}
		if (list.length) {
			setTimeout(() => {
				uploads = [];
			}, 4000);
			await loadDocuments();
		}
	}

	async function deleteDoc(id: string) {
		if (!confirm('Delete this document?')) return;
		try {
			await api.deleteDocument(id);
			toast.success('Document deleted');
			await loadDocuments();
		} catch (e) {
			toast.error(e instanceof Error ? e.message : 'Delete failed');
		}
	}

	function onDrop(e: DragEvent) {
		e.preventDefault();
		dragging = false;
		if (e.dataTransfer?.files.length) handleUpload(e.dataTransfer.files);
	}

	function onDragOver(e: DragEvent) {
		e.preventDefault();
		dragging = true;
	}

	function statusVariant(status: string): 'default' | 'secondary' | 'outline' | 'ghost' | 'destructive' {
		const s = (status || '').toLowerCase();
		if (s === 'completed' || s === 'ready') return 'outline';
		if (s === 'processing' || s === 'pending') return 'secondary';
		if (s === 'failed' || s === 'error') return 'destructive';
		return 'ghost';
	}

	// Reload whenever the collection filter changes (and on first render).
	$effect(() => {
		void docFilter;
		loadDocuments();
	});
</script>

<Card>
	<CardHeader>
		<CardTitle>Upload Documents</CardTitle>
		<CardDescription>
			Upload documents to the RAG store. Supported: PDF, DOCX, TXT, Markdown.
		</CardDescription>
	</CardHeader>
	<CardContent class="flex flex-col gap-4">
		<div
			class="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring {dragging
				? 'border-primary bg-accent/50'
				: 'border-border hover:border-primary/60 hover:bg-accent/40'}"
			role="button"
			tabindex="0"
			onclick={() => fileInput?.click()}
			onkeydown={(e) => {
				if (e.key === 'Enter' || e.key === ' ') {
					e.preventDefault();
					fileInput?.click();
				}
			}}
			ondragover={onDragOver}
			ondragleave={() => (dragging = false)}
			ondrop={onDrop}
		>
			<UploadCloudIcon class="size-10 opacity-50" />
			<p class="mt-2 text-sm font-medium">Drop files here or click to upload</p>
			<p class="text-xs text-muted-foreground">PDF, DOCX, TXT, MD — up to 50MB</p>
			<input
				type="file"
				class="hidden"
				multiple
				accept=".pdf,.docx,.txt,.md"
				bind:this={fileInput}
				onchange={() => {
					if (fileInput?.files?.length) {
						handleUpload(fileInput.files);
						fileInput.value = '';
					}
				}}
			/>
		</div>

		<div class="flex flex-wrap items-center gap-3">
			<span class="flex items-center gap-2 text-sm text-muted-foreground">
				Collection
			</span>
			<Select.Root type="single" bind:value={uploadCollection}>
				<Select.Trigger class="w-48">
					<span class="flex-1 text-left">{uploadCollection}</span>
				</Select.Trigger>
				<Select.Content>
					{#each collectionNames() as name}
						<Select.Item value={name} label={name}>{name}</Select.Item>
					{/each}
				</Select.Content>
			</Select.Root>
		</div>

		{#if uploads.length}
			<ul class="flex flex-col gap-2">
				{#each uploads as item (item.name + item.status)}
					<li class="flex items-center gap-2 text-sm">
						<span
							class="size-2 shrink-0 rounded-full {item.status === 'loading'
								? 'animate-pulse bg-[#d29922]'
								: item.status === 'success'
									? 'bg-[#3fb950]'
									: 'bg-[#f85149]'}"
						></span>
						<span class="min-w-0 flex-1 truncate">
							{item.name} ({formatSize(item.size)})
						</span>
						{#if item.status === 'loading'}
							<span class="text-muted-foreground">Uploading…</span>
						{:else if item.status === 'success'}
							<span class="text-[#3fb950]">✓ {item.message}</span>
						{:else}
							<span class="text-[#f85149]">✗ {item.message}</span>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</CardContent>
</Card>

<Card class="mt-4">
	<CardHeader class="flex-row items-center justify-between gap-2">
		<div>
			<CardTitle>Documents</CardTitle>
		</div>
		<div class="flex items-center gap-2">
			<Select.Root type="single" bind:value={docFilter}>
				<Select.Trigger class="w-40">
					<span class="flex-1 text-left">
						{docFilter || 'All collections'}
					</span>
				</Select.Trigger>
				<Select.Content>
					<Select.Item value="" label="All collections">All collections</Select.Item>
					{#each collectionNames() as name}
						<Select.Item value={name} label={name}>{name}</Select.Item>
					{/each}
				</Select.Content>
			</Select.Root>
			<Button variant="outline" size="sm" onclick={() => loadDocuments()}>
				<RefreshCwIcon />
				Refresh
			</Button>
		</div>
	</CardHeader>
	<CardContent>
		{#if !docs.length}
			<p class="py-6 text-center text-sm text-muted-foreground">
				No documents uploaded yet.
			</p>
		{:else}
			<ul class="flex flex-col divide-y divide-border">
				{#each docs as doc (doc.id)}
					<li class="flex items-center gap-3 py-2.5">
						<span class="text-lg">{fileIcon(doc.filename)}</span>
						<div class="min-w-0 flex-1">
							<p class="truncate text-sm font-medium">{doc.filename}</p>
							<p class="truncate text-xs text-muted-foreground">
								{formatSize(doc.filesize)}
								<span class="mx-1">·</span>
								{doc.collection_name}
								<span class="mx-1">·</span>
								{doc.chunk_count || 0} chunks
								{#if doc.created_at}
									<span class="mx-1">·</span>
									{formatDateShort(doc.created_at)}
								{/if}
							</p>
						</div>
						<Badge variant={statusVariant(doc.status)}>{doc.status}</Badge>
						<Button
							variant="ghost"
							size="icon-sm"
							class="text-muted-foreground hover:text-[#f85149]"
							title="Delete"
							onclick={() => deleteDoc(doc.id)}
						>
							<Trash2Icon />
						</Button>
					</li>
				{/each}
			</ul>
		{/if}
	</CardContent>
</Card>
