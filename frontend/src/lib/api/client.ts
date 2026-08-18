// ── Typed API client ───────────────────────────────────────────────
// Port of the vanilla `API` object in mysterium/static/js/app.js.

import type {
	ChatTurnResult,
	Collection,
	DocItem,
	HistoryChat,
	HistoryChatItem,
	HistoryReportItem,
	PageResponse,
	ResearchReport,
	SearchResponse,
	UploadResult,
} from './types';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(path, init);
	if (!res.ok) {
		const data = await res.json().catch(() => ({}));
		throw new Error(
			(data as { detail?: string }).detail ||
				`${init?.method || 'GET'} ${path} failed (${res.status})`,
		);
	}
	return res.json() as Promise<T>;
}

function post<T>(path: string, body: unknown): Promise<T> {
	return request<T>(path, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body),
	});
}

export interface SearchOptions {
	collection?: string;
	limit?: number;
	rerank?: boolean;
}

export interface AskOptions {
	collection?: string;
	limit?: number;
}

export const api = {
	version: () => request<{ version: string }>('/api/version'),

	// ── Documents ─────────────────────────────────────────────────
	collections: () =>
		request<PageResponse<Collection>>('/api/documents/collections'),

	documents: (params: { collection?: string; page?: number; per_page?: number } = {}) => {
		const qs = new URLSearchParams();
		qs.set('page', String(params.page ?? 1));
		qs.set('per_page', String(params.per_page ?? 50));
		if (params.collection) qs.set('collection_name', params.collection);
		return request<PageResponse<DocItem>>(`/api/documents?${qs.toString()}`);
	},

	deleteDocument: (id: string) =>
		request<{ message: string }>(
			`/api/documents/${encodeURIComponent(id)}`,
			{ method: 'DELETE' },
		),

	async upload(file: File, collection: string): Promise<UploadResult> {
		const form = new FormData();
		form.append('file', file);
		form.append('collection_name', collection);
		const res = await fetch('/api/documents/upload', {
			method: 'POST',
			body: form,
		});
		if (!res.ok) {
			const data = await res.json().catch(() => ({}));
			throw new Error(
				(data as { detail?: string }).detail || `Upload failed (${res.status})`,
			);
		}
		return res.json() as Promise<UploadResult>;
	},

	search: (query: string, opts: SearchOptions = {}) =>
		post<SearchResponse>('/api/documents/search', {
			query,
			collection_name: opts.collection || 'documents',
			limit: opts.limit || 5,
			min_score: 0.0,
			use_reranker: opts.rerank || false,
		}),

	// ── Research ──────────────────────────────────────────────────
	ask: (question: string, opts: AskOptions = {}) =>
		post<ChatTurnResult>('/api/research/ask', {
			question,
			collection_name: opts.collection || 'documents',
			limit: opts.limit || 5,
		}),

	// ── History: reports ──────────────────────────────────────────
	historyReports: () =>
		request<{ items: HistoryReportItem[] }>('/api/history/reports'),

	historyReport: (id: string) =>
		request<ResearchReport>(`/api/history/reports/${encodeURIComponent(id)}`),

	deleteHistoryReport: (id: string) =>
		request<{ message: string }>(
			`/api/history/reports/${encodeURIComponent(id)}`,
			{ method: 'DELETE' },
		),

	// ── History: chats ────────────────────────────────────────────
	historyChats: () =>
		request<{ items: HistoryChatItem[] }>('/api/history/chats'),

	historyChat: (id: string) =>
		request<HistoryChat>(`/api/history/chats/${encodeURIComponent(id)}`),

	deleteHistoryChat: (id: string) =>
		request<{ message: string }>(
			`/api/history/chats/${encodeURIComponent(id)}`,
			{ method: 'DELETE' },
		),
};
