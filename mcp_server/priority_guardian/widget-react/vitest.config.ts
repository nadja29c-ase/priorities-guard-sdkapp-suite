import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // Cast needed: vitest bundles its own vite with different Plugin types
  plugins: [react() as any],
  define: {
    __WIDGET_BUILD_TIME__: JSON.stringify('2026-05-24T00:00:00.000Z'),  // Inc 89: mock build time for tests
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // e2e/ holds Playwright specs (real-browser regression layer, run via
    // `npm run test:e2e`) — they use @playwright/test's own runner/globals,
    // not vitest's, and must not be collected here. Vitest's own defaults
    // are repeated explicitly since setting `exclude` replaces them.
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      '**/cypress/**',
      '**/.{idea,git,cache,output,temp}/**',
      '**/{karma,rollup,webpack,vite,vitest,jest,ava,babel,nyc,cypress,tsup,build}.config.*',
      'e2e/**',
    ],
  },
})
