import { expect, test } from '@playwright/test';

test('POST /vc/nominations ui smoke', async ({ page, request }) => {
  await page.goto(process.env.BASE_URL || 'http://localhost:5173');
  await expect(page.getByRole('heading', { name: '2) Test Cases' })).toBeVisible();
  await page.getByRole('button', { name: 'Create New Test Case' }).click();
  await expect(page.getByRole('heading', { name: 'Create New AI Test Case' })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByRole('heading', { name: '3) Execution Results' })).toBeVisible();
});
