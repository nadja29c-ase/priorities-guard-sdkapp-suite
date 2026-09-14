import { defineConfig, devices } from '@playwright/test'

// Regression layer for inc_card_size_fix.md — resolved CSS at representative
// viewport widths, against the COMMITTED bundle (../widgets/pg-dashboard.html),
// not the dev server. Run `npm run build` first (see package.json "test:e2e").
//
// This serves the standalone widget document directly in a Chromium tab, not
// inside a ChatGPT host iframe. It is a real-browser regression check on the
// CSS rules themselves — it is NOT a substitute for manual verification in an
// actual ChatGPT session (narrow mobile / standard desktop / wide desktop-Canvas),
// which is the required primary evidence per inc_card_size_fix.md and is the
// one thing this layer cannot provide (it cannot reproduce ChatGPT's actual
// iframe/container sizing behavior).
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4321',
  },
  webServer: {
    command: 'python3 -m http.server 4321 --directory ../widgets --bind 127.0.0.1',
    url: 'http://127.0.0.1:4321/pg-dashboard.html',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
