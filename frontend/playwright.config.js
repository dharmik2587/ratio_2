import { defineConfig } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

// RATIO Phase 3 browser E2E. The workspace ships its own Chromium bootstrap:
// scripts/bootstrap_e2e_browser.sh extracts @sparticuz/chromium into
// frontend/.e2e-chromium/ and builds the NSS/NSPR runtime libraries that the
// sandbox host may lack. Override with RATIO_CHROMIUM_PATH for a system Chrome.
const chromiumPath = process.env.RATIO_CHROMIUM_PATH
  || path.resolve(process.cwd(), '.e2e-chromium', 'chrome')
const libDir = path.resolve(process.cwd(), '.e2e-chromium', 'lib')
const hasLibs = fs.existsSync(path.join(libDir, 'libnss3.so'))

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  retries: 0,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'test-results/results.json' }]],
  use: {
    baseURL: process.env.RATIO_E2E_BASE || 'http://localhost:5173',
    trace: 'retain-on-failure',
    launchOptions: {
      executablePath: fs.existsSync(chromiumPath) ? chromiumPath : undefined,
      args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
      env: hasLibs ? { ...process.env, LD_LIBRARY_PATH: libDir } : process.env,
    },
  },
  webServer: [
    {
      command: 'PYTHONPATH=.. ../.venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000',
      url: 'http://localhost:8000/api/health/phase3',
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
})
