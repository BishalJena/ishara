import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {outDir: '../backend/web_static', emptyOutDir: true},
  server: {proxy: {
    '/web': 'http://127.0.0.1:8780', '/service-status': 'http://127.0.0.1:8780', '/health': 'http://127.0.0.1:8780',
    '/briefs': 'http://127.0.0.1:8780',
    '/calls': {target: 'http://127.0.0.1:8780', ws: true},
  }},
});
