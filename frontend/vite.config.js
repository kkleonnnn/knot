import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../knot/static',
    emptyOutDir: true,
    // v0.7.44 B5.2 — echarts 切独立 vendor chunk（与 app 代码分离 → app 重发不重下 echarts）
    rollupOptions: {
      output: {
        manualChunks: (id) => (id.includes('node_modules/echarts') ? 'echarts' : undefined),
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  // v0.7.43 B5.1 — vitest 纯逻辑测试（node 环境；测试文件显式 import 自 'vitest'，无需 globals/jsdom）
  test: {
    environment: 'node',
    include: ['src/**/*.test.{js,jsx}'],
  },
})
