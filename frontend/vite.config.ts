/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 开发模式：前端 5173，/api 代理到本地后端 8720
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // changeOrigin：代理请求 Host 改写为 127.0.0.1:8720，过服务端本机 Host 校验
      '/api': { target: 'http://127.0.0.1:8720', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
  },
  // 组件测试（审计 B1）：jsdom + RTL；setup 载入 jest-dom 匹配器；globals 开启使 RTL 自动 cleanup 生效
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
