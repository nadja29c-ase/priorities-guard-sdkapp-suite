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
    rollupOptions: {
      input: 'index.html',
      output: {
        entryFileNames: 'clarity-clusters.js',
      }
    }
  }
})
