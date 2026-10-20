/*
 * @Author: yangjie
 * @Date: 2026-05-26 15:23:44
 * @LastEditors: yangjie 
 * @LastEditTime: 2026-09-16 14:36:48
 * @FilePath: \0-readmd\vite.config.js
 * @Description: 
 * 
 * Copyright (c) 2026 by bimcc, All Rights Reserved. 
 */
import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  base: './',
  server: {
    port: 8899,
    fs: {
      allow: ['..']
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, 'index.html')
    }
  }
})
