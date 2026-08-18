// ── Chat conversation state ────────────────────────────────────────
// The client owns the conversation: `chat.messages` is the full history sent
// to the backend each turn (minus the new message), and each assistant turn
// appends a streamed bubble. `chat.conversationId` persists the transcript
// server-side so follow-ups append to the same file.
//
// Components READ the exported object and mutate it ONLY through the exported
// actions below (Svelte forbids exporting reassigned `$state` bindings).

import type { ChatMessage } from '$lib/api/types';

export const chat = $state({
	messages: [] as ChatMessage[],
	conversationId: null as string | null,
	busy: false,
});

export function pushChatMessage(message: ChatMessage): void {
	chat.messages = [...chat.messages, message];
}

export function replaceChatMessages(messages: ChatMessage[]): void {
	chat.messages = messages;
}

export function setConversationId(id: string | null): void {
	chat.conversationId = id;
}

export function setBusy(value: boolean): void {
	chat.busy = value;
}

export function clearChat(): void {
	chat.messages = [];
	chat.conversationId = null;
	chat.busy = false;
}
