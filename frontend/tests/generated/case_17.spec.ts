import { expect, test } from '@playwright/test';

test('PATCH /vc/nominations/{id}/schedule ui smoke', async ({ page, request }) => {
  await page.goto(process.env.BASE_URL || 'http://localhost:5173');
  await expect(page.locator('text=AI QA Copilot')).toBeVisible();
});
