import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 45_000,
  retries: 0,
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:5173',
    headless: process.env.PLAYWRIGHT_HEADED === '1' ? false : true,
    launchOptions: {
      slowMo: Number(process.env.PLAYWRIGHT_SLOW_MO || '120'),
    },
  },
  reporter: [['list']],
});
