import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
  },
  server: {
    host: '127.0.0.1',
    port: 63014,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:63010',
        changeOrigin: true,
      },
    },
  },
})

