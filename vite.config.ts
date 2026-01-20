import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0', // Umożliwia dostęp z sieci (np. z QNAP)
    port: 5173,      // Port frontendu
    proxy: {
      '/api': {
        target: 'http://localhost:5001', // Przekierowanie do backendu
        changeOrigin: true,
        secure: false,
      },
    },
  },
});