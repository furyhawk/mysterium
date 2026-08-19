/**
 * Theme registry.
 *
 * Discovers every theme folder under `src/themes/` at build time using
 * Vite's `import.meta.glob`, so adding a theme never requires touching this
 * file. Each theme folder must export a `theme` metadata object and provide
 * a `theme.css` file with its design-token overrides.
 *
 * The CSS files are imported with `?url`, which makes Vite emit each one as
 * a standalone asset served from its own path (`<base>themes/<id>/theme.css`
 * in production, `<base>src/themes/<id>/theme.css` in dev). This keeps every
 * theme loadable in its own folder, independent of the main bundle.
 */

import type { Theme } from './types';

// `{ eager: true }` pulls every theme's metadata into the app bundle.
const metaModules = import.meta.glob<{ theme: Theme }>('./*/index.ts', {
	eager: true,
});

// `{ query: '?url' }` yields the emitted asset URL for each theme's CSS.
const cssModules = import.meta.glob<string>('./*/theme.css', {
	eager: true,
	query: '?url',
	import: 'default',
});

function themeIdFromPath(path: string): string {
	// Paths look like "./<id>/index.ts" or "./<id>/theme.css".
	const parts = path.split('/');
	return parts[1] ?? '';
}

/** All discovered themes, in folder order. */
export const themes: Theme[] = Object.keys(metaModules).map((path) => {
	const meta = metaModules[path].theme;
	return { ...meta, id: themeIdFromPath(path) || meta.id };
});

/** themeId -> emitted CSS asset URL. */
const cssUrlByTheme: Record<string, string> = Object.fromEntries(
	Object.entries(cssModules).map(([path, url]) => [themeIdFromPath(path), url]),
);

/** Id of the fallback theme used when no persisted choice exists. */
const FALLBACK_THEME_ID = 'github-dark';
export const DEFAULT_THEME_ID: string = themes.some((t) => t.id === FALLBACK_THEME_ID)
	? FALLBACK_THEME_ID
	: themes[0]?.id ?? FALLBACK_THEME_ID;

/** Look up a theme by id (falls back to the default theme). */
export function getTheme(id: string | null | undefined): Theme {
	const theme = themes.find((t) => t.id === id);
	return theme ?? themes[0] ?? { id: 'github-dark', label: 'GitHub Dark', defaultMode: 'dark' };
}

/** URL of the CSS asset for a theme id. */
export function themeCssUrl(id: string): string {
	return cssUrlByTheme[id] ?? '';
}

/** Theme ids, for validation / iteration. */
export const themeIds: string[] = themes.map((t) => t.id);
