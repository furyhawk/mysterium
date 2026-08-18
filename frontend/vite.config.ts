import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import tailwindcss from '@tailwindcss/vite';

// The production bundle is emitted straight into the package's static dir,
// which FastAPI already mounts at /ui (html=True). This keeps the backend
// serving code untouched.
export default defineConfig({
  plugins: [svelte(), tailwindcss()],
  resolve: {
    alias: {
      $lib: fileURLToPath(new URL('./src/lib', import.meta.url)),
    },
  },
  // Asset URLs are resolved relative to the /ui mount point.
  base: '/ui/',
  build: {
    outDir: fileURLToPath(new URL('../mysterium/static', import.meta.url)),
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    // During `npm run dev`, proxy API calls to the FastAPI backend.
    proxy: {
      '/api': 'http://localhost:8200',
    },
  },
});
