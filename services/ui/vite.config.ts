import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Voice service - direct connection for WebSocket streaming
      '/api/voice': {
        target: 'http://localhost:8410',
        changeOrigin: true,
        ws: true,  // WebSocket for real-time voice streaming
      },
      // Route other API requests through HAProxy/Gateway (3 load-balanced instances)
      // Gateway handles: io-control, fabrication, images, research, vision, etc.
      // Gateway proxies to brain for: query, conversations, autonomy, memory, etc.
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        ws: true,  // Enable WebSocket proxying for research streaming
      }
    }
  },
  preview: {
    port: 4173,
    proxy: {
      // Voice service - direct connection for WebSocket streaming
      '/api/voice': {
        target: 'http://localhost:8410',
        changeOrigin: true,
        ws: true,
      },
      // Gateway for other APIs
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        ws: true,
      }
    }
  }
});
