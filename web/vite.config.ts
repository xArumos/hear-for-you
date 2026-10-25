import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  if (mode === 'ios') {
    const env = loadEnv(mode, process.cwd(), 'VITE_');
    if (env.VITE_USE_FIXTURES === '1') throw new Error('iOS builds require the real backend; unset VITE_USE_FIXTURES.');
    const endpoint = env.VITE_API_BASE_URL;
    if (!endpoint) throw new Error('Set VITE_API_BASE_URL in .env.ios.local before building the iOS app.');
    const url = new URL(endpoint);
    if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' || url.search || url.hash
      || ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
      throw new Error('iOS requires a reachable HTTPS backend origin without credentials or a path.');
    }
  }
  return {
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    strictPort: true,
  },
  };
});
