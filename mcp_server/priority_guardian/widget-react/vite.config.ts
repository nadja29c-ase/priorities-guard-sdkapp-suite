/**
 * Priority Guardian Widget Build Configuration
 *
 * DEPENDENCY NOTE: @openai/apps-sdk-ui is pinned to 0.2.1 in package.json.
 * TODO: Check for SDK updates before major releases. Breaking changes may
 * affect theme tokens, Badge/Button props, or useDocumentTheme behavior.
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { viteSingleFile } from 'vite-plugin-singlefile'

export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  build: {
    target: 'esnext',
    outDir: '../widgets',
    emptyOutDir: false,
    // Output is index.html, renamed to pg-dashboard.html by postbuild script
  }
})
