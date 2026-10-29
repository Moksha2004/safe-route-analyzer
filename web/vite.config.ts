import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

const projectRoot = fileURLToPath(new URL('..', import.meta.url));

export default defineConfig({
  envDir: projectRoot,
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
});
