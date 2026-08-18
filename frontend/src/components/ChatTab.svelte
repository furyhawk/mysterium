<script lang="ts">
	import { toast } from 'svelte-sonner';
	import SendIcon from '@lucide/svelte/icons/send';
	import EraserIcon from '@lucide/svelte/icons/eraser';
	import DownloadIcon from '@lucide/svelte/icons/download';
	import { streamSSE } from '$lib/api/sse';
	import type { ChatTurnResult } from '$lib/api/types';
	import { collectionNames } from '$lib/app/store.svelte';
	import {
		chat,
		clearChat,
		pushChatMessage,
		setBusy,
		setConversationId,
	} from '$lib/chat/store.svelte';
	import { renderMarkdown } from '$lib/markdown/render';
	import { downloadFile } from '$lib/utils';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Checkbox } from '$lib/components/ui/checkbox/index.js';
	import * as Select from '$lib/components/ui/select/index.js';
	import ChatMessage from './ChatMessage.svelte';

	const models = [
		{ value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4' },
		{ value: 'claude-opus-4-20250514', label: 'Claude Opus 4' },
		{ value: 'claude-haiku-4-20250514', label: 'Claude Haiku 4' },
	];

	let inputText = $state('');
	let collection = $state('documents');
	let limit = $state(5);
	let model = $state(models[0].value);
	let useWeb = $state(true);
	let useWebFetch = $state(true);
	let useWebFetchLocal = $state(true);

	// Live streaming state (rendered as the transient assistant bubble).
	let streamingContent = $state('');
	let typing = $state('');

	let messagesEl: HTMLDivElement | undefined = $state();
	let inputEl: HTMLTextAreaElement | undefined = $state();

	function scrollToBottom() {
		if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
	}

	// Keep the message area pinned to the bottom as new tokens arrive.
	$effect(() => {
		void streamingContent;
		void chat.messages.length;
		scrollToBottom();
	});

	async function send() {
		const text = inputText.trim();
		if (!text || chat.busy) return;

		pushChatMessage({ role: 'user', content: text });
		inputText = '';
		setBusy(true);
		streamingContent = '';
		typing = 'Thinking…';

		try {
			const final = await streamSSE<ChatTurnResult>(
				'/api/chat/stream',
				{
					message: text,
					// History excludes the new message — the backend appends it.
					messages: chat.messages.slice(0, -1),
					conversation_id: chat.conversationId,
					collection_name: collection,
					limit: Math.max(1, Math.min(50, Number(limit) || 5)),
					model,
					use_web: useWeb,
					use_web_fetch: useWebFetch,
					use_web_fetch_local: useWebFetchLocal,
				},
				{
					onPhase: (evt) => {
						typing = evt.message;
					},
					onToken: (evt) => {
						// The first token means the answer has started — drop
						// the typing/working indicator.
						if (!streamingContent) typing = '';
						streamingContent += evt.text;
					},
				},
			);

			// Defensive: if no tokens streamed, use the final content.
			if (!streamingContent) streamingContent = final.content || '';
			if (final.conversation_id) setConversationId(final.conversation_id);

			// Commit the assistant turn to history.
			pushChatMessage({
				role: 'assistant',
				content: streamingContent,
				sources: final.sources?.length ? final.sources : undefined,
				images: final.images?.length ? final.images : undefined,
			});
			streamingContent = '';
		} catch (e) {
			streamingContent = '';
			toast.error(
				e instanceof Error ? e.message : 'Chat request failed',
			);
		} finally {
			typing = '';
			setBusy(false);
			scrollToBottom();
			inputEl?.focus();
		}
	}

	function autoGrow() {
		if (!inputEl) return;
		inputEl.style.height = 'auto';
		inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + 'px';
	}

	function newConversation() {
		if (!confirm('Start a new conversation? The current transcript will stay saved.')) return;
		clearChat();
		streamingContent = '';
		typing = '';
		inputEl?.focus();
	}

	function exportChat() {
		if (!chat.conversationId) {
			toast.error(
				'This conversation has not been saved yet — send a message first',
			);
			return;
		}
		downloadFile(
			`/api/history/chats/${encodeURIComponent(chat.conversationId)}/export?format=md`,
		).catch((e) =>
			toast.error(e instanceof Error ? e.message : 'Download failed'),
		);
	}
</script>

<div class="flex h-[calc(100svh-8.5rem)] flex-col gap-3 rounded-lg border border-border bg-card p-3 sm:p-4">
	<div>
		<h2 class="text-lg font-semibold">Ask your documents</h2>
		<p class="text-sm text-muted-foreground">
			Chat with an agent that answers from your RAG document store, using web
			sources to fill gaps when needed. Multi-turn — ask follow-ups.
		</p>
	</div>

	<div class="flex flex-wrap items-center gap-x-5 gap-y-2">
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
			<Input type="number" bind:value={limit} class="h-8 w-20" min="1" max="50" />
		</label>

		<label class="flex items-center gap-2 text-sm text-muted-foreground">
			Model
			<Select.Root type="single" bind:value={model}>
				<Select.Trigger class="w-44">
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
			<span>Web</span>
		</label>
		<label
			class="flex cursor-pointer items-center gap-2 text-sm"
			title="Fetch and read full web pages. Off automatically for gateways that don't support it"
		>
			<Checkbox bind:checked={useWebFetch} />
			<span>Fetch</span>
		</label>
		<label
			class="flex cursor-pointer items-center gap-2 text-sm"
			title="Fetch pages with a local markdownify tool instead of Anthropic's server-side web-fetch tool"
		>
			<Checkbox bind:checked={useWebFetchLocal} />
			<span>Local fetch</span>
		</label>

		<div class="ml-auto flex items-center gap-2">
			<Button
				variant="outline"
				size="sm"
				onclick={newConversation}
				title="Start a new conversation"
			>
				<EraserIcon />
				New
			</Button>
			<Button
				variant="outline"
				size="sm"
				onclick={exportChat}
				disabled={!chat.conversationId}
				title="Download this conversation as Markdown"
			>
				<DownloadIcon />
				Download
			</Button>
		</div>
	</div>

	<div
		bind:this={messagesEl}
		class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto rounded-md border border-border bg-background p-3"
	>
		{#if !chat.messages.length && !streamingContent && !typing}
			<div class="flex flex-1 flex-col items-center justify-center gap-1 text-center">
				<span class="text-3xl">💬</span>
				<p class="text-sm text-muted-foreground">
					Ask a question about your documents.
				</p>
				<p class="text-xs text-muted-foreground/70">
					e.g. "What are the key findings in the quarterly report?"
				</p>
			</div>
		{/if}

		{#each chat.messages as msg, i (i)}
			<ChatMessage message={msg} />
		{/each}

		{#if streamingContent}
			<div class="flex w-full justify-start">
				<div class="max-w-[85%] rounded-lg border border-border bg-card px-3 py-2 text-sm sm:max-w-[75%]">
					<div class="markdown">{@html renderMarkdown(streamingContent)}</div>
				</div>
			</div>
		{:else if typing}
			<div class="flex w-full justify-start">
				<div class="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground">
					<span class="flex gap-1">
						<i class="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:0ms]"></i>
						<i class="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:150ms]"></i>
						<i class="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:300ms]"></i>
					</span>
					<span>{typing}</span>
				</div>
			</div>
		{/if}
	</div>

	<div class="flex items-end gap-2">
		<textarea
			bind:this={inputEl}
			bind:value={inputText}
			rows="1"
			placeholder="Ask a question about your documents… (Enter to send, Shift+Enter for a new line)"
			class="max-h-40 min-h-10 flex-1 resize-none rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
			oninput={autoGrow}
			onkeydown={(e) => {
				if (e.key === 'Enter' && !e.shiftKey) {
					e.preventDefault();
					send();
				}
			}}
		></textarea>
		<Button onclick={send} disabled={chat.busy || !inputText.trim()}>
			<SendIcon />
			Send
		</Button>
	</div>
</div>
