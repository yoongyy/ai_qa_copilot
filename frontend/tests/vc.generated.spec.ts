import { expect, test } from '@playwright/test';

test('qa dashboard loads endpoint workflow', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '1) API Endpoint Catalog' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '2) Test Cases' })).toBeVisible();
});
