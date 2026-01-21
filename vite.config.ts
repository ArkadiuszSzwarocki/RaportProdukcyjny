import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
 server: {
    allowedHosts: ['filipinka.myqnapcloud.com', 'mlecznadroga.mycloudnas.com'],
    port: 5173, // Zmieniono z 5178 na 5173, aby pasowało do logów
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8089/', // Zmieniono z 3000 na 8089
        changeOrigin: true,
      }
    }
  },
});