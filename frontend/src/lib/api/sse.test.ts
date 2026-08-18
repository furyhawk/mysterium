import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamSSE } from './sse';
import type { ChatTurnResult, PhaseEvent, ResearchReport, TokenEvent } from './types';

function sseResponse(chunks: string[], status = 200): Response {
	const body = new ReadableStream({
		start(controller) {
			for (const chunk of chunks) {
				controller.enqueue(new TextEncoder().encode(chunk));
			}
			controller.close();
		},
	});
	return new Response(body, { status });
}

function event(obj: unknown): string {
	return 'data: ' + JSON.stringify(obj) + '\n\n';
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('streamSSE', () => {
	it('parses phases and resolves with a chat message', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () =>
				sseResponse([
					event({ type: 'phase', message: 'Searching…', tool: 'rag' }),
					event({ type: 'token', text: 'Hello ' }),
					event({ type: 'token', text: 'world' }),
					event({
						type: 'message',
						message: { content: 'Hello world', conversation_id: 'c1' },
					}),
				]),
			),
		);

		const phases: PhaseEvent[] = [];
		const tokens: TokenEvent[] = [];
		const result = await streamSSE<ChatTurnResult>('/api/chat/stream', {}, {
			onPhase: (e) => phases.push(e),
			onToken: (e) => tokens.push(e),
		});

		expect(phases).toHaveLength(1);
		expect(phases[0].message).toBe('Searching…');
		expect(tokens.map((t) => t.text).join('')).toBe('Hello world');
		expect(result.content).toBe('Hello world');
		expect(result.conversation_id).toBe('c1');
	});

	it('resolves with a research report payload', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () =>
				sseResponse([
					event({ type: 'phase', message: 'Synthesizing…' }),
					event({
						type: 'report',
						report: { title: 'T', report_id: 'r1' },
					}),
				]),
			),
		);

		const report = await streamSSE<ResearchReport>('/api/research/report/stream', {});
		expect(report.title).toBe('T');
		expect(report.report_id).toBe('r1');
	});

	it('handles events split across multiple chunks', async () => {
		const payload = event({ type: 'message', message: { content: 'done' } });
		const mid = Math.floor(payload.length / 2);
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => sseResponse([payload.slice(0, mid), payload.slice(mid)])),
		);

		const result = await streamSSE<ChatTurnResult>('/api/chat/stream', {});
		expect(result.content).toBe('done');
	});

	it('ignores non-data lines', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () =>
				sseResponse([': keepalive\n\n' + event({ type: 'message', message: { content: 'ok' } })]),
			),
		);
		const result = await streamSSE<ChatTurnResult>('/api/chat/stream', {});
		expect(result.content).toBe('ok');
	});

	it('throws when the server emits an error event', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => sseResponse([event({ type: 'error', message: 'boom' })])),
		);
		await expect(
			streamSSE<ChatTurnResult>('/api/chat/stream', {}),
		).rejects.toThrow('boom');
	});

	it('throws when the stream ends without a result', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => sseResponse([event({ type: 'phase', message: 'x' })])),
		);
		await expect(
			streamSSE<ChatTurnResult>('/api/chat/stream', {}),
		).rejects.toThrow(/without a result/);
	});

	it('throws a descriptive error on non-OK responses', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () =>
				new Response(JSON.stringify({ detail: 'No API key' }), { status: 400 }),
			),
		);
		await expect(
			streamSSE<ChatTurnResult>('/api/chat/stream', {}),
		).rejects.toThrow('No API key');
	});
});
