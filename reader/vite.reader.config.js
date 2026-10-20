import { defineConfig } from 'vite'
import { resolve } from 'node:path'
export default defineConfig({
  base: '/',
  publicDir: false,
  build: {outDir: 'dist', emptyOutDir: true,
    rollupOptions: {input: resolve(import.meta.dirname, 'local.html')}}
})
