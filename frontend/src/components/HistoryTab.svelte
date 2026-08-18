<script lang="ts">
	import { toast } from 'svelte-sonner';
	import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw';
	import ExternalLinkIcon from '@lucide/svelte/icons/external-link';
	import DownloadIcon from '@lucide/svelte/icons/download';
	import Trash2Icon from '@lucide/svelte/icons/trash-2';
	import { api } from '$lib/api/client';
	import type { HistoryChatItem, HistoryReportItem } from '$lib/api/types';
	import { openReport, setTab } from '$lib/app/store.svelte';
	import {
		replaceChatMessages,
		setConversationId,
	} from '$lib/chat/store.svelte';
	import { downloadFile, formatDate } from '$lib/utils';
	import { Button } from '$lib/components/ui/button/index.js';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card/index.js';

	let reports = $state<HistoryReportItem[]>([]);
	let chats = $state<HistoryChatItem[]>([]);

	async function loadReports() {
		try {
			const data = await api.historyReports();
			reports = data.items || [];
		} catch (e) {
			toast.error(
				e instanceof Error ? e.message : 'Failed to load reports',
			);
		}
	}

	async function loadChats() {
		try {
			const data = await api.historyChats();
			chats = data.items || [];
		} catch (e) {
			toast.error(
				e instanceof Error ? e.message : 'Failed to load conversations',
			);
		}
	}

	async function loadHistory() {
		await Promise.all([loadReports(), loadChats()]);
	}

	async function openReportById(id: string) {
		try {
			const report = await api.historyReport(id);
			openReport(report);
		} catch (e) {
			toast.error(e instanceof Error ? e.message : 'Failed to open report');
		}
	}

	async function deleteReport(id: string) {
		if (!confirm('Delete this saved report?')) return;
		try {
			await api.deleteHistoryReport(id);
			toast.success('Report deleted');
			await loadReports();
		} catch (e) {
			toast.error(e instanceof Error ? e.message : 'Delete failed');
		}
	}

	async function openChatById(id: string) {
		try {
			const chat = await api.historyChat(id);
			replaceChatMessages(chat.messages || []);
			setConversationId(chat.id || id);
			setTab('chat');
		} catch (e) {
			toast.error(
				e instanceof Error ? e.message : 'Failed to open conversation',
			);
		}
	}

	async function deleteChat(id: string) {
		if (!confirm('Delete this saved conversation?')) return;
		try {
			await api.deleteHistoryChat(id);
			toast.success('Conversation deleted');
			await loadChats();
		} catch (e) {
			toast.error(e instanceof Error ? e.message : 'Delete failed');
		}
	}

	$effect(() => {
		loadHistory();
	});
</script>

<Card>
	<CardHeader class="flex-row items-center justify-between gap-2">
		<div>
			<CardTitle>Saved Research Reports</CardTitle>
			<CardDescription>
				Reports are saved automatically after generation.
			</CardDescription>
		</div>
		<Button variant="outline" size="sm" onclick={loadHistory}>
			<RefreshCwIcon />
			Refresh
		</Button>
	</CardHeader>
	<CardContent>
		{#if !reports.length}
			<p class="py-6 text-center text-sm text-muted-foreground">
				No saved reports yet.
			</p>
		{:else}
			<ul class="flex flex-col divide-y divide-border">
				{#each reports as report (report.id)}
					<li class="flex items-center gap-3 py-2.5">
						<div class="min-w-0 flex-1">
							<p class="truncate text-sm font-medium">{report.title}</p>
							<p class="truncate text-xs text-muted-foreground">
								{report.query || ''}
								{#if report.model} · {report.model}{/if}
								{#if report.saved_at} · {formatDate(report.saved_at)}{/if}
							</p>
						</div>
						<div class="flex shrink-0 items-center gap-1">
							<Button
								variant="ghost"
								size="sm"
								onclick={() => openReportById(report.id)}
								title="Open"
							>
								<ExternalLinkIcon />
								Open
							</Button>
							<Button
								variant="ghost"
								size="icon-sm"
								onclick={() =>
									downloadFile(
										`/api/history/reports/${encodeURIComponent(report.id)}/export?format=md`,
									).catch((e) =>
										toast.error(
											e instanceof Error ? e.message : 'Download failed',
										),
									)}
								title="Download as Markdown"
							>
								<DownloadIcon />
							</Button>
							<Button
								variant="ghost"
								size="icon-sm"
								class="text-muted-foreground hover:text-[#f85149]"
								onclick={() => deleteReport(report.id)}
								title="Delete"
							>
								<Trash2Icon />
							</Button>
						</div>
					</li>
				{/each}
			</ul>
		{/if}
	</CardContent>
</Card>

<Card class="mt-4">
	<CardHeader>
		<CardTitle>Saved Conversations</CardTitle>
		<CardDescription>
			Chat transcripts are saved automatically. Open one to continue it.
		</CardDescription>
	</CardHeader>
	<CardContent>
		{#if !chats.length}
			<p class="py-6 text-center text-sm text-muted-foreground">
				No saved conversations yet.
			</p>
		{:else}
			<ul class="flex flex-col divide-y divide-border">
				{#each chats as chat (chat.id)}
					<li class="flex items-center gap-3 py-2.5">
						<div class="min-w-0 flex-1">
							<p class="truncate text-sm font-medium">{chat.title}</p>
							<p class="truncate text-xs text-muted-foreground">
								{chat.message_count} messages
								{#if chat.collection_name} · {chat.collection_name}{/if}
								{#if chat.updated_at} · {formatDate(chat.updated_at)}{/if}
							</p>
						</div>
						<div class="flex shrink-0 items-center gap-1">
							<Button
								variant="ghost"
								size="sm"
								onclick={() => openChatById(chat.id)}
								title="Open"
							>
								<ExternalLinkIcon />
								Open
							</Button>
							<Button
								variant="ghost"
								size="icon-sm"
								onclick={() =>
									downloadFile(
										`/api/history/chats/${encodeURIComponent(chat.id)}/export?format=md`,
									).catch((e) =>
										toast.error(
											e instanceof Error ? e.message : 'Download failed',
										),
									)}
								title="Download as Markdown"
							>
								<DownloadIcon />
							</Button>
							<Button
								variant="ghost"
								size="icon-sm"
								class="text-muted-foreground hover:text-[#f85149]"
								onclick={() => deleteChat(chat.id)}
								title="Delete"
							>
								<Trash2Icon />
							</Button>
						</div>
					</li>
				{/each}
			</ul>
		{/if}
	</CardContent>
</Card>
