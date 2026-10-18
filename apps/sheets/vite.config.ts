import { defineConfig } from 'vite'

export default defineConfig({
  base: './',
  server: { host: '127.0.0.1', port: 5174 },
  build: { target: 'es2022', outDir: 'dist', emptyOutDir: true },
})
