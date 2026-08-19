/**
 * Theme contract.
 *
 * A theme is a self-contained folder under `src/themes/<id>/` containing:
 *
 *   - `index.ts`   — exports a `theme: Theme` metadata object
 *   - `theme.css`  — CSS custom properties (design tokens) overriding the
 *                    shadcn-svelte token names on `:root`
 *
 * The registry auto-discovers every folder via `import.meta.glob`, so adding
 * a theme is purely additive: drop a new folder in and rebuild — no wiring in
 * core code required. See `themes/README.md`.
 */
export interface Theme {
	/** Unique machine id. Must match the folder name (used as the URL path). */
	id: string;
	/** Human-readable label shown in the theme picker. */
	label: string;
	/** Optional short description shown as a tooltip. */
	description?: string;
	/** Color mode applied while this theme is active (drives the toaster). */
	defaultMode: 'light' | 'dark';
}

export type ThemeMode = Theme['defaultMode'];
