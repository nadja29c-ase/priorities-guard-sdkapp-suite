import { defineConfig, devices } from '@playwright/test'

// Regression layer for inc_card_size_fix.md — resolved CSS at representative
// viewport widths, against the built bundle on disk (../widgets/pg-dashboard.html),
// not the dev server. `npm run test:e2e` rebuilds automatically before running
// (see package.json), so it always exercises the current working tree — that is
// only "the committed bundle" if the tree is clean at that path when you run it.
// Running `playwright test` directly instead uses whatever is on disk already,
// stale or not.
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
