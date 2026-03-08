import { expect, test } from '@playwright/test';

test('vessel connect simulator form submit flow', async ({ page }) => {
  await page.goto('/vessel-connect');

  await expect(page.getByTestId('vc-vessel-name')).toHaveValue('');
  await expect(page.getByTestId('vc-port')).toHaveValue('');
  await expect(page.getByTestId('vc-eta')).toHaveValue('');

  await page.getByTestId('vc-vessel-name').fill('MT Frontend Test 209');
  await page.getByTestId('vc-port').fill('Rotterdam');
  await page.getByTestId('vc-eta').fill('2026-03-23T09:00:00Z');
  await page.getByTestId('vc-submit').hover();
  await page.getByTestId('vc-submit').click();

  await expect(page.getByTestId('vc-submit-status')).toContainText('Form submitted successfully');
  await expect(page.getByTestId('vc-nomination-id')).not.toHaveText('-');

  await page.getByTestId('vc-jetty').fill('Jetty-T9');
  await page.getByTestId('vc-schedule-eta').fill('2026-03-23T13:20:00Z');
  await page.getByTestId('vc-schedule-submit').hover();
  await page.getByTestId('vc-schedule-submit').click();

  await expect(page.getByTestId('vc-schedule-status')).toContainText('Schedule updated');
  await expect(page.getByTestId('vc-calendar-count')).toContainText('Calendar Events:');
});
