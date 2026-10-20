import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  base: './',
  build: {
    outDir: 'dist-lib',
    emptyOutDir: false,
    lib: {
      entry: resolve(__dirname, 'src/index.js'),
      name: 'ReadMarkdownEngine',
      formats: ['es'],
      fileName: () => 'read-markdown-engine.mjs'
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true
      }
    }
  }
})
