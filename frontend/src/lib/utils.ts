import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChild<T> = T extends { child?: any } ? Omit<T, "child"> : T;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChildren<T> = T extends { children?: any } ? Omit<T, "children"> : T;
export type WithoutChildrenOrChild<T> = WithoutChildren<WithoutChild<T>>;
export type WithElementRef<T, U extends HTMLElement = HTMLElement> = T & { ref?: U | null };

// ── Formatting helpers ─────────────────────────────────────────────

export function formatSize(bytes: number): string {
	if (bytes < 1024) return bytes + ' B';
	if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
	return (bytes / 1048576).toFixed(1) + ' MB';
}

export function fileIcon(filename: string): string {
	const ext = (filename || '').split('.').pop()?.toLowerCase() ?? '';
	switch (ext) {
		case 'pdf':
			return '📄';
		case 'docx':
			return '📝';
		case 'txt':
			return '📃';
		case 'md':
			return '📑';
		default:
			return '📎';
	}
}

export function statusClass(status: string | null | undefined): string {
	const s = (status || '').toLowerCase();
	if (s === 'completed' || s === 'ready') return 'completed';
	if (s === 'processing' || s === 'pending') return 'processing';
	if (s === 'failed' || s === 'error') return 'failed';
	return 'pending';
}

export function escapeHtml(text: string): string {
	const d = document.createElement('div');
	d.textContent = text;
	return d.innerHTML;
}

export function formatDate(iso: string | null | undefined): string {
	if (!iso) return '';
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return '';
	return d.toLocaleString();
}

export function formatDateShort(iso: string | null | undefined): string {
	if (!iso) return '';
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return '';
	return d.toLocaleDateString();
}

// Downloads a file from a URL that returns a Content-Disposition attachment.
export async function downloadFile(url: string): Promise<void> {
	const res = await fetch(url);
	if (!res.ok) {
		const data = await res.json().catch(() => ({}));
		throw new Error(
			(data as { detail?: string }).detail || `Download failed (${res.status})`,
		);
	}
	const blob = await res.blob();
	const disposition = res.headers.get('Content-Disposition') || '';
	const match = disposition.match(/filename="?([^";]+)"?/);
	const name = match ? match[1] : 'export';
	const a = document.createElement('a');
	a.href = URL.createObjectURL(blob);
	a.download = name;
	document.body.appendChild(a);
	a.click();
	a.remove();
	URL.revokeObjectURL(a.href);
}
