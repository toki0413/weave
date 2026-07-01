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
          // Code splitting: separate vendor and feature chunks
          'vendor': ['vitest'],
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
