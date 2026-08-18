// ── Generic Server-Sent Events streaming helper ────────────────────
// Both the research report endpoint (POST /api/research/report/stream)
// and the chat endpoint (POST /api/chat/stream) push the same `data: {...}`
// framed JSON events. This helper consumes one stream and dispatches typed
// events to the provided handlers, resolving with the final payload
// (a report for research, a message object for chat).

import type {
	ErrorEvent,
	PhaseEvent,
	TokenEvent,
} from './types';

export interface SSEHandlers<T> {
	/** Called for every live `phase` event (agent tool progress). */
	onPhase?: (evt: PhaseEvent) => void;
	/** Called for every `token` event (chat answer text chunks). */
	onToken?: (evt: TokenEvent) => void;
	/** Called with the resolved final payload (`report` / `message`). */
	onResult?: (result: T) => void;
	/** Called when the server emits an `error` event. */
	onError?: (evt: ErrorEvent) => void;
}

export async function streamSSE<T>(
	path: string,
	payload: unknown,
	handlers: SSEHandlers<T> = {},
): Promise<T> {
	const res = await fetch(path, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload),
	});
	if (!res.ok) {
		const data = await res.json().catch(() => ({}));
		throw new Error(
			(data as { detail?: string }).detail || `Stream failed (${res.status})`,
		);
	}
	if (!res.body) {
		throw new Error('Streaming is not supported by this browser');
	}

	const reader = res.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';
	let result: T | null = null;

	for (;;) {
		const { done, value } = await reader.read();
		if (done) break;
		buffer += decoder.decode(value, { stream: true });

		let sep: number;
		while ((sep = buffer.indexOf('\n\n')) !== -1) {
			const raw = buffer.slice(0, sep);
			buffer = buffer.slice(sep + 2);
			const dataLine = raw.split('\n').find((l) => l.startsWith('data:'));
			if (!dataLine) continue;

			let evt: {
				type?: string;
				message?: unknown;
				text?: string;
				report?: unknown;
			};
			try {
				evt = JSON.parse(dataLine.slice(5).trim());
			} catch {
				continue;
			}

			switch (evt.type) {
				case 'phase':
					handlers.onPhase?.(evt as PhaseEvent);
					break;
				case 'token':
					handlers.onToken?.(evt as TokenEvent);
					break;
				case 'message': {
					const r = evt.message as T;
					handlers.onResult?.(r);
					result = r;
					break;
				}
				case 'report': {
					const r = evt.report as T;
					handlers.onResult?.(r);
					result = r;
					break;
				}
				case 'error':
					throw new Error(
						(evt as ErrorEvent).message || 'Stream failed',
					);
			}
		}
	}

	if (result === null) {
		throw new Error('Stream ended without a result.');
	}
	return result;
}
