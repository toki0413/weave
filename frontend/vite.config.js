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
  },
});
