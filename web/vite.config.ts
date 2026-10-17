import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import { fileURLToPath, URL } from 'node:url'

// In dev, the BwithU server runs on :8282 and Vite proxies API/WS calls to it.
const server = process.env.BWITHU_SERVER || 'http://127.0.0.1:8282'

export default defineConfig({
  base: './',
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 2000,
  },
  server: {
    proxy: {
      '/download': { target: server, changeOrigin: true },
      '/openavatarchat': { target: server, changeOrigin: true },
      '/ws': { target: server.replace(/^http/, 'ws'), ws: true, rewriteWsOrigin: true },
    },
  },
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@renderer': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
