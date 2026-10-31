import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: './tests', timeout: 90000, workers: 1,
  outputDir: './artifacts/test-results',
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:8780', viewport: {width: 1440, height: 1000},
    permissions: ['camera'],
    launchOptions: {args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream']},
    screenshot: 'only-on-failure', trace: 'retain-on-failure',
  },
  webServer: {
    command: 'uv run --directory ../backend --extra web-recognition python -m scripts.web_demo',
    url: 'http://127.0.0.1:8780/web/session', reuseExistingServer: true, timeout: 120000,
  },
});
