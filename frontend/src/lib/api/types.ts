// ── API contracts ──────────────────────────────────────────────────
// These mirror the payload shapes returned by the FastAPI backend
// (see mysterium/routers/*).

export interface Collection {
	name: string;
	total_vectors: number;
	dim: number;
	indexing_status: string;
}

export interface DocItem {
	id: string;
	collection_name: string;
	filename: string;
	filesize: number;
	filetype: string;
	status: string;
	chunk_count: number;
	error_message: string | null;
	created_at: string | null;
	completed_at: string | null;
}

export interface SearchResult {
	content: string;
	score: number;
	parent_doc_id?: string;
	metadata?: {
		filename?: string;
		page?: number;
		chunk_index?: number;
	};
}

export interface UploadResult {
	id?: string;
	filename?: string;
	status?: string;
	message?: string;
}

export interface ReportSection {
	heading: string;
	content: string;
	sources?: string[];
}

export interface ReportSource {
	title: string;
	relevance: string;
	excerpt: string;
}

export interface ReportImage {
	image_id: string;
	description?: string;
	page_num?: number;
	url?: string;
}

export interface ResearchReport {
	report_id?: string;
	title: string;
	summary?: string;
	key_findings?: string[];
	sections?: ReportSection[];
	gaps?: string[];
	sources?: ReportSource[];
	images?: ReportImage[];
	generated_at?: string;
}

export interface ChatMessage {
	role: 'user' | 'assistant';
	content: string;
	/** Present on assistant messages that cite RAG sources (and when restored from history). */
	sources?: ChatSource[];
	images?: ReportImage[];
}

export interface ChatSource {
	filename?: string;
	content: string;
	score: number;
}

export interface ChatTurnResult {
	role?: string;
	content: string;
	sources?: ChatSource[];
	images?: ReportImage[];
	conversation_id?: string;
}

export interface HistoryReportItem {
	id: string;
	title: string;
	query?: string;
	model?: string;
	saved_at?: string;
}

export interface HistoryChatItem {
	id: string;
	title: string;
	message_count: number;
	collection_name?: string;
	updated_at?: string;
}

export interface HistoryChat extends HistoryChatItem {
	messages: ChatMessage[];
}

export interface PageResponse<T> {
	items: T[];
	total: number;
	page: number;
	per_page: number;
}

export interface SearchResponse {
	results: SearchResult[];
}

// ── Server-Sent Events ─────────────────────────────────────────────

export interface PhaseEvent {
	type: 'phase';
	message: string;
	tool?: string;
}

export interface TokenEvent {
	type: 'token';
	text: string;
}

export interface MessageEvent {
	type: 'message';
	message: ChatTurnResult;
}

export interface ReportEvent {
	type: 'report';
	report: ResearchReport;
}

export interface ErrorEvent {
	type: 'error';
	message: string;
}

export type SSEEvent =
	| PhaseEvent
	| TokenEvent
	| MessageEvent
	| ReportEvent
	| ErrorEvent;
