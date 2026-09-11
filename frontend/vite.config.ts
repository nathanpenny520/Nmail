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
})
