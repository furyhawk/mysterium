<script lang="ts">
	import { renderMarkdown } from '$lib/markdown/render';
	import type { ChatMessage, ReportImage } from '$lib/api/types';
	import * as Dialog from '$lib/components/ui/dialog/index.js';

	let { message }: { message: ChatMessage } = $props();

	let lightbox = $state<ReportImage | null>(null);

	function openLightbox(im: ReportImage) {
		lightbox = im;
	}
</script>

<div class="flex w-full {message.role === 'user' ? 'justify-end' : 'justify-start'}">
	<div
		class="max-w-[85%] rounded-lg px-3 py-2 text-sm sm:max-w-[75%] {message.role ===
		'user'
			? 'bg-primary text-primary-foreground'
			: 'border border-border bg-card'}"
	>
		{#if message.role === 'assistant'}
			<div class="markdown">{@html renderMarkdown(message.content)}</div>
		{:else}
			<p class="whitespace-pre-wrap">{message.content}</p>
		{/if}

		{#if message.images?.length}
			<div class="mt-3 flex flex-wrap gap-2">
				{#each message.images as im (im.image_id)}
					<button
						type="button"
						class="overflow-hidden rounded-md border border-border outline-none focus-visible:ring-2 focus-visible:ring-ring"
						onclick={() => openLightbox(im)}
					>
						<img
							src={`/api/images/${encodeURIComponent(im.image_id)}`}
							alt={im.description || 'Document image'}
							loading="lazy"
							class="h-24 w-32 object-cover"
						/>
					</button>
				{/each}
			</div>
		{/if}

		{#if message.sources?.length}
			<details class="chat-sources mt-3 rounded-md border border-border bg-background">
				<summary class="cursor-pointer select-none px-3 py-2 text-xs font-medium text-muted-foreground">
					📚 Sources ({message.sources.length})
				</summary>
				<div class="flex flex-col gap-2 px-3 pb-3">
					{#each message.sources as source, i (i)}
						<div class="rounded-md bg-muted/40 p-2">
							<div class="flex items-center justify-between gap-2">
								<span class="truncate text-xs font-medium">
									{source.filename || 'Unknown source'}
								</span>
								<span class="shrink-0 text-xs text-muted-foreground">
									Score: {((source.score || 0) * 100).toFixed(1)}%
								</span>
							</div>
							<p class="mt-1 line-clamp-3 text-xs text-muted-foreground">
								{source.content}
							</p>
						</div>
					{/each}
				</div>
			</details>
		{/if}
	</div>
</div>

<Dialog.Root
	open={lightbox !== null}
	onOpenChange={(o) => {
		if (!o) lightbox = null;
	}}
>
	<Dialog.Content class="max-w-3xl" showCloseButton={false}>
		{#if lightbox}
			<img
				src={`/api/images/${encodeURIComponent(lightbox.image_id)}`}
				alt={lightbox.description || 'Document image'}
				class="max-h-[80vh] w-full rounded-md object-contain"
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
