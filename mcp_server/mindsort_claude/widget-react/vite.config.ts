/**
 * MindSort Claude Widget Build Configuration
 *
 * Uses @modelcontextprotocol/ext-apps for Claude MCP Apps standard.
 * Builds to single self-contained HTML file via vite-plugin-singlefile.
 * Output: ../widgets/mindsort-dashboard-claude.html (replaces Widget-0 placeholder)
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: {
    target: 'esnext',
    outDir: '../widgets',
    emptyOutDir: false,
    rollupOptions: {
      input: 'mindsort-dashboard-claude.html',
    },
  },
})
