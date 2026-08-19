# Frontend themes

Mysterium ships with a **multi-theme** system for the browser UI. Each theme
lives in its **own folder** under `src/themes/`, is compiled to a **standalone
stylesheet served from its own path** (`<base>themes/<id>/theme.css` in
production), and is **auto-discovered** — no core code needs to change when a
theme is added.

## How it works

```
src/themes/
  types.ts              # Theme contract (id, label, description, defaultMode)
  registry.ts           # auto-discovers themes via import.meta.glob
  README.md             # this file
  <theme-id>/
    index.ts            # exports `theme: Theme` metadata
    theme.css           # :root design-token overrides (the theme's look)
```

- `registry.ts` globs every `<theme-id>/index.ts` and `<theme-id>/theme.css`.
  The CSS is imported with `?url`, so Vite emits each theme as its own asset
  into `mysterium/static/themes/<id>/theme.css` (see `vite.config.ts`
  `rollupOptions.output.assetFileNames`). In dev, the same URL is served from
  source automatically.
- The theme manager (`src/lib/app/theme.svelte.ts`) applies the selected theme
  at runtime:
  - sets `data-theme` on `<html>`,
  - toggles the `.dark` class + `color-scheme` for the theme's default mode
    (keeps shadcn `dark:` variants and the toaster consistent),
  - points `<link id="theme-stylesheet">` at the theme's own CSS asset
    (kept **after** the base stylesheet so its `:root` tokens win).
  - persists the choice in `localStorage` (`mysterium.theme`).
- The picker lives in the header (`App.svelte`) and lists every discovered
  theme. A tiny pre-paint script in `index.html` restores the stored theme
  before first render to avoid a flash.

## Adding a theme

1. **Create a folder** `src/themes/<id>/` (the `<id>` becomes the URL path and
   must be unique).
2. **Add `index.ts`** exporting a `theme` object:

   ```ts
   import type { Theme } from '../types';

   export const theme: Theme = {
     id: 'my-theme',
     label: 'My Theme',
     description: 'Optional short description.',
     defaultMode: 'dark', // or 'light'
   };
   ```

3. **Add `theme.css`** with the design tokens. Plain CSS custom properties on
   `:root` — every shadcn-svelte component picks them up automatically:

   ```css
   :root {
     --background: #0d1117;
     --foreground: #e6edf3;
     --card: #161b22;
     /* ... all tokens listed below ... */
     color-scheme: dark;
   }
   ```

4. **Rebuild** (`npm run build`). The theme appears in the picker and its CSS
   is emitted at `mysterium/static/themes/<id>/theme.css`. No wiring needed.

## Available tokens

Override any subset of the shadcn-svelte token set; anything you omit falls
back to the base palette in `src/app.css`.

| Token | Purpose |
| --- | --- |
| `--background` / `--foreground` | page background / text |
| `--card` / `--card-foreground` | cards |
| `--popover` / `--popover-foreground` | popovers, menus, toasts |
| `--primary` / `--primary-foreground` | primary actions |
| `--secondary` / `--secondary-foreground` | secondary surfaces |
| `--muted` / `--muted-foreground` | subdued surfaces / text |
| `--accent` / `--accent-foreground` | hover/accent surfaces |
| `--destructive` / `--destructive-foreground` | destructive actions |
| `--border` / `--input` / `--ring` | borders, inputs, focus rings |
| `--chart-1` … `--chart-5` | chart/status colors |
| `--radius` | global border radius |
| `--sidebar-*` | sidebar surfaces (used by `Sidebar*` components) |
| `color-scheme` | native scrollbars, form controls, `color-scheme` meta |

## Notes

- Themes are **plain CSS by design** — keep `theme.css` free of Tailwind
  directives so each file stays small, cacheable, and independently loadable.
- The base fallback palette in `src/app.css` is GitHub Dark, so the app renders
  correctly even before a theme stylesheet loads.
