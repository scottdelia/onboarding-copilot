import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Relative asset URLs, so the build works from a repository subpath on GitHub
  // Pages as well as from a domain root. An absolute "/assets/..." would 404
  // under /<repo>/.
  base: './',
});
