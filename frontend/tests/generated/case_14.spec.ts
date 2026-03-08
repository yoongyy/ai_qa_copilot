import { expect, test } from '@playwright/test';

test('POST /vc/nominations ui smoke', async ({ page, request }) => {
  await page.goto(process.env.BASE_URL || 'http://localhost:5173');
  await expect(page.locator('text=AI QA Copilot')).toBeVisible();
});
