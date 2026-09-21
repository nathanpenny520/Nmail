/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import { defineConfig, type Plugin } from 'vite'

// 构建指纹（S-0921「新构建已就绪」浮条）：编译期注入前端（__BUILD_ID__），
// 同时写入 dist/build-id.json 由后端 /api/meta 下发——前端轮询比对两者，
// 不一致说明后端已换新前端，提示用户刷新。每次 build 唯一。
const BUILD_ID = Date.now().toString(36)

function buildIdPlugin(): Plugin {
  return {
    name: 'write-build-id',
    closeBundle() {
      fs.mkdirSync('dist', { recursive: true })
      fs.writeFileSync('dist/build-id.json', JSON.stringify({ id: BUILD_ID }))
    },
  }
}

// 开发模式：前端 5173，/api 代理到本地后端 8720
export default defineConfig({
  plugins: [react(), tailwindcss(), buildIdPlugin()],
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID),
  },
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
