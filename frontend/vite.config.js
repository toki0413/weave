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
        manualChunks: {
          // nlp 和 UI 面板按需加载，减少首屏体积
          'nlp': ['./src/nlp/parse.js', './src/nlp/entity.js', './src/nlp/fmm.js', './src/nlp/anomaly.js'],
          'ui-panels': ['./src/ui/panels/leftPanel.js', './src/ui/panels/rightPanel.js', './src/ui/panels/header.js', './src/ui/panels/timeline.js'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
  },
});
