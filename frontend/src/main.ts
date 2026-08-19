import { mount } from 'svelte';
import './app.css';
import { initTheme } from './lib/app/theme.svelte';
import App from './App.svelte';

// Apply the persisted (or default) theme before first render so there is no
// flash of the wrong palette. The <link id="theme-stylesheet"> that the
// pre-paint script in index.html creates is reused/updated here.
initTheme();

const app = mount(App, {
	target: document.getElementById('app')!,
});

export default app;
