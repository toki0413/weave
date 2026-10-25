import { defineConfig } from 'vite';

export default defineConfig({
  root: 'src',
  base: './',
  publicDir: '../public',
  build: {
    outDir: '../../dist',
    emptyOutDir: true,
    modulePreload: false,
    rollupOptions: {
      external: ['@sentry/browser'],
      output: {
        // vite 8 rolldown 引擎要求 manualChunks 为函数形式
        manualChunks(id) {
          if (id.includes('/src/nlp/')) return 'nlp';
          if (id.includes('/src/ui/panels/')) return 'ui-panels';
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    // runner 边界（单一事实源）：*.test.js 归 vitest；*.spec.mjs 归 node:test
    // （CI 里 node --test "src/tests/*.spec.mjs"）。曾因 vitest 误捡 spec.mjs
    // 导致 4 个文件级失败、套件退出码非零、CI 常红——rebase 引入 node:test
    // spec 后暴露。路径相对 root:'src'。
    include: ['tests/*.test.js'],
  },
});
