<script lang="ts">
	import { onMount } from 'svelte';
	import UploadIcon from '@lucide/svelte/icons/upload';
	import SearchIcon from '@lucide/svelte/icons/search';
	import PenLineIcon from '@lucide/svelte/icons/pen-line';
	import MessageSquareIcon from '@lucide/svelte/icons/message-square';
	import HistoryIcon from '@lucide/svelte/icons/history';
	import { Toaster } from '$lib/components/ui/sonner/index.js';
	import {
		app,
		loadVersion,
		refreshCollections,
		setTab,
		type TabId,
	} from '$lib/app/store.svelte';
	import UploadTab from './components/UploadTab.svelte';
	import SearchTab from './components/SearchTab.svelte';
	import ResearchTab from './components/ResearchTab.svelte';
	import ChatTab from './components/ChatTab.svelte';
	import HistoryTab from './components/HistoryTab.svelte';

	interface NavTab {
		id: TabId;
		label: string;
		icon: typeof UploadIcon;
	}

	const tabs: NavTab[] = [
		{ id: 'upload', label: 'Upload', icon: UploadIcon },
		{ id: 'search', label: 'Search', icon: SearchIcon },
		{ id: 'research', label: 'Research', icon: PenLineIcon },
		{ id: 'chat', label: 'Chat', icon: MessageSquareIcon },
		{ id: 'history', label: 'History', icon: HistoryIcon },
	];

	onMount(() => {
		loadVersion();
		refreshCollections();
	});
</script>

<div class="flex min-h-svh flex-col bg-background text-foreground">
	<header class="sticky top-0 z-40 border-b border-border bg-card/85 backdrop-blur-md">
		<div class="flex h-14 items-center gap-3 px-3 sm:px-4">
			<div class="flex shrink-0 items-center gap-2 text-[1.05rem] font-bold">
				<span class="text-lg">🔬</span>
				<span>Mysterium</span>
			</div>
			<span class="hidden shrink-0 text-xs text-muted-foreground md:inline">
				RAG + Deep Research
			</span>

			<nav class="ml-auto flex items-center gap-0.5 overflow-x-auto no-scrollbar">
				{#each tabs as tab}
					<button
						type="button"
						class="flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring {app.activeTab ===
						tab.id
							? 'bg-secondary text-foreground'
							: 'text-muted-foreground hover:bg-muted hover:text-foreground'}"
						onclick={() => setTab(tab.id)}
					>
						<svelte:component this={tab.icon} class="size-4" />
						<span>{tab.label}</span>
					</button>
				{/each}
			</nav>

			{#if app.navStatus}
				<span class="hidden shrink-0 text-xs text-muted-foreground lg:inline">
					{app.navStatus}
				</span>
			{/if}
			{#if app.version}
				<span class="shrink-0 text-xs text-muted-foreground">v{app.version}</span>
			{/if}
		</div>
	</header>

	<main class="mx-auto w-full max-w-5xl flex-1 px-3 py-5 sm:px-4 sm:py-6">
		{#if app.activeTab === 'upload'}
			<UploadTab />
		{:else if app.activeTab === 'search'}
			<SearchTab />
		{:else if app.activeTab === 'research'}
			<ResearchTab />
		{:else if app.activeTab === 'chat'}
			<ChatTab />
		{:else}
			<HistoryTab />
		{/if}
	</main>

	<Toaster theme="dark" richColors />
</div>
