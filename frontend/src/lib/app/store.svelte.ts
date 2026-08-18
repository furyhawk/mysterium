// ── Global app state (Svelte 5 runes at module scope) ─────────────
// Shared by the nav shell and every tab so cross-tab actions (e.g. opening a
// saved conversation, refreshing collections) stay in sync.
//
// State lives in a single exported object that is only mutated via its
// properties — Svelte forbids exporting `$state` bindings that get reassigned.

import { api } from '$lib/api/client';
import type { Collection, ResearchReport } from '$lib/api/types';

export type TabId = 'upload' | 'search' | 'research' | 'chat' | 'history';

export const app = $state({
	activeTab: 'upload' as TabId,
	version: '',
	collections: [] as Collection[],
	// Summary shown in the nav bar, e.g. "3 completed · 1 processing".
	navStatus: '',
	// Report currently displayed in the Research tab (set by Research or History).
	researchReport: null as ResearchReport | null,
});

/** Collection names, falling back to the default collection. */
export function collectionNames(): string[] {
	return app.collections.length
		? app.collections.map((c) => c.name)
		: ['documents'];
}

export function setTab(tab: TabId): void {
	app.activeTab = tab;
}

export function setNavStatus(status: string): void {
	app.navStatus = status;
}

export function setResearchReport(report: ResearchReport | null): void {
	app.researchReport = report;
}

/** Open a report in the Research tab. */
export function openReport(report: ResearchReport): void {
	app.researchReport = report;
	app.activeTab = 'research';
}

export async function loadVersion(): Promise<void> {
	try {
		const data = await api.version();
		app.version = data.version;
	} catch (e) {
		console.warn('Failed to load version:', e);
	}
}

export async function refreshCollections(): Promise<void> {
	try {
		const data = await api.collections();
		app.collections = data.items;
	} catch (e) {
		console.warn('Failed to load collections:', e);
		app.collections = [];
	}
}
