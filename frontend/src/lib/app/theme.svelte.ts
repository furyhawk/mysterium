// ── Theme manager (Svelte 5 runes at module scope) ────────────────
// Reactive selection + persistence + DOM application for the multi-theme
// system. Themes are defined as folders under src/themes/ (see registry.ts).
//
// How a theme is applied:
//   - `data-theme` attribute on <html>            → identifies the active theme
//   - `.dark` class on <html>                     → keeps `dark:` variants and
//     the toaster consistent with the theme's default mode
//   - `color-scheme` inline style on <html>       → native scrollbars/controls
//   - a <link id="theme-stylesheet"> in <head>    → loads the theme's own CSS
//     asset from <base>themes/<id>/theme.css so each theme is loadable in its
//     own folder and can be swapped at runtime.
//
// The choice is persisted in localStorage under `mysterium.theme`, which is
// also read by the tiny pre-paint script in index.html (avoids FOUC).

import { setMode } from 'mode-watcher';
import { DEFAULT_THEME_ID, getTheme, themeCssUrl } from '../../themes/registry';
import type { Theme, ThemeMode } from '../../themes/types';

const STORAGE_KEY = 'mysterium.theme';

interface PersistedTheme {
	themeId: string;
	mode: ThemeMode;
}

export const themeState = $state({
	themeId: DEFAULT_THEME_ID,
	mode: 'dark' as ThemeMode,
});

/** The active Theme metadata (always falls back to a real theme). */
export function currentTheme(): Theme {
	return getTheme(themeState.themeId);
}

/** Stable id of the <link> element that loads the theme stylesheet. */
const STYLESHEET_ID = 'theme-stylesheet';

function persisted(): PersistedTheme | null {
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return null;
		const parsed = JSON.parse(raw) as PersistedTheme;
		if (typeof parsed.themeId !== 'string') return null;
		return {
			themeId: parsed.themeId,
			mode: parsed.mode === 'light' ? 'light' : 'dark',
		};
	} catch {
		return null;
	}
}

function persist(): void {
	try {
		localStorage.setItem(
			STORAGE_KEY,
			JSON.stringify({ themeId: themeState.themeId, mode: themeState.mode } satisfies PersistedTheme),
		);
	} catch {
		// localStorage may be unavailable (private mode); ignore.
	}
}

/** Point the shared <link id="theme-stylesheet"> at a theme's CSS asset. */
function setStylesheet(href: string): void {
	let link = document.getElementById(STYLESHEET_ID) as HTMLLinkElement | null;
	if (!link) {
		link = document.createElement('link');
		link.id = STYLESHEET_ID;
		link.rel = 'stylesheet';
		document.head.appendChild(link);
	}
	if (link.href !== href) link.href = href;
	// Keep the theme sheet AFTER the app's base stylesheet so its `:root`
	// tokens win the cascade (the pre-paint script may have inserted it early).
	document.head.appendChild(link);
}

/** Push the current themeState to the DOM (styles + mode). */
function apply(): void {
	const theme = currentTheme();
	const mode = themeState.mode;

	const root = document.documentElement;
	root.dataset.theme = theme.id;
	root.classList.toggle('dark', mode === 'dark');
	root.style.colorScheme = mode;

	// Load this theme's own stylesheet asset from its own folder.
	setStylesheet(themeCssUrl(theme.id));

	// Keep the toaster (sonner reads `mode` from mode-watcher) in sync.
	try {
		setMode(mode);
	} catch (e) {
		console.warn('Failed to sync toaster theme:', e);
	}
}

/**
 * Restore the persisted theme (or the default) and apply it. Safe to call
 * multiple times; call once at startup before mounting the app.
 */
export function initTheme(): void {
	const saved = persisted();
	const themeId = saved?.themeId ?? DEFAULT_THEME_ID;
	const theme = getTheme(themeId);
	themeState.themeId = theme.id;
	themeState.mode = saved?.mode ?? theme.defaultMode;
	apply();
	persist();
}

/** Select a theme and adopt its default mode. */
export function setTheme(id: string): void {
	const theme = getTheme(id);
	if (theme.id === themeState.themeId) return;
	themeState.themeId = theme.id;
	themeState.mode = theme.defaultMode;
	apply();
	persist();
}

/** Toggle light/dark mode within the current theme. */
export function toggleMode(): void {
	themeState.mode = themeState.mode === 'dark' ? 'light' : 'dark';
	apply();
	persist();
}

/** Reset to the default theme and clear the stored preference. */
export function resetTheme(): void {
	try {
		localStorage.removeItem(STORAGE_KEY);
	} catch {
		// ignore
	}
	const theme = getTheme(DEFAULT_THEME_ID);
	themeState.themeId = theme.id;
	themeState.mode = theme.defaultMode;
	apply();
}
