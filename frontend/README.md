# Mysterium Frontend

The browser UI for Mysterium — a [Svelte 5](https://svelte.dev) + [Vite](https://vite.dev) +
TypeScript app styled with [shadcn-svelte](https://shadcn-svelte.com) (Bits UI + Tailwind CSS v4).

## Overview

- **Tabs**: Upload, Search, Research, Chat, History — a single-page app with client-side tab
  switching (no router dependency).
- **Shared stores** (`src/lib/app/store.svelte.ts`, `src/lib/chat/store.svelte.ts`): Svelte 5
  runes at module scope, exposed through action functions.
- **Themes** (`src/themes/`): a multi-theme system. Each theme is a self-contained folder with
  its own `theme.css`, compiled to a standalone stylesheet served from its own path
  (`<base>themes/<id>/theme.css`). Themes are auto-discovered; add a folder to add a theme.
  See `src/themes/README.md`.
- **API layer** (`src/lib/api`): typed REST client + a generic Server-Sent Events helper used by
  both the research report stream and the chat stream.
- **Markdown** (`src/lib/markdown`): a self-contained, XSS-safe renderer and a report exporter.
- **Build output** is written straight into `../mysterium/static/`, which FastAPI mounts at `/ui`.
  Theme stylesheets are emitted to `../mysterium/static/themes/<id>/theme.css`.

## Scripts

```bash
npm install   # install dependencies
npm run dev   # Vite dev server with HMR (proxies /api to http://localhost:8200)
npm run build # production build into ../mysterium/static
npm run check # svelte-check + tsc type-check
npm test      # run unit tests (Vitest)
```

> The production bundle is committed in `mysterium/static/`, so the backend runs without a Node
> toolchain. Rebuild it (`npm run build`) after editing these sources.

## Project structure

```
src/
  App.svelte                 # shell: nav bar, tab switching, toaster
  components/
    UploadTab.svelte         # drag-drop upload + documents list
    SearchTab.svelte         # vector/hybrid search
    ResearchTab.svelte       # live streaming research report generation
    ReportView.svelte        # shared report renderer (research + history)
    ChatTab.svelte           # multi-turn streaming chat
    ChatMessage.svelte       # assistant/user bubble (markdown, sources, images)
    HistoryTab.svelte        # saved reports + conversations
  lib/
    api/                     # types, REST client, SSE streaming helper
    markdown/                # XSS-safe markdown renderer + report exporter
    app/store.svelte.ts      # global app state (tab, version, collections, ...)
    app/theme.svelte.ts      # theme manager (selection, persistence, DOM apply)
    chat/store.svelte.ts     # chat conversation state
    components/ui/           # shadcn-svelte components (generated)
  themes/                    # multi-theme system (see themes/README.md)
    registry.ts              # auto-discovers themes + their CSS assets
    <theme-id>/index.ts      # theme metadata
    <theme-id>/theme.css     # design tokens for that theme
```

## Key Svelte 5 notes

- Module-level state uses `export const x = $state({ ... })` and is mutated only through exported
  action functions — Svelte forbids exporting reassigned/derived `$state` bindings.
- Store modules use the `.svelte.ts` extension so the Svelte compiler processes their runes.
