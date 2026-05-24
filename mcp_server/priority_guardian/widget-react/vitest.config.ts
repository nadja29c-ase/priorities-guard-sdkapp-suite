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
  },
})
