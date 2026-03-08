import { expect, test } from '@playwright/test';

test('POST /vc/nominations ui smoke', async ({ page, request }) => {
  const base = process.env.BASE_URL || 'http://localhost:5173';
  await page.goto(`${base}/vessel-connect`);

  await page.getByTestId('vc-vessel-name').fill('MT Playwright Live');
  await page.getByTestId('vc-port').fill('Singapore');
  await page.getByTestId('vc-eta').fill('2026-03-16T10:00:00Z');
  await page.getByTestId('vc-submit').click();

  await expect(page.getByTestId('vc-submit-status')).toContainText('Form submitted successfully');
  await expect(page.getByTestId('vc-nomination-id')).not.toHaveText('-');

  await page.getByTestId('vc-jetty').fill('Jetty-PW-1');
  await page.getByTestId('vc-schedule-eta').fill('2026-03-16T12:00:00Z');
  await page.getByTestId('vc-schedule-submit').click();
  await expect(page.getByTestId('vc-schedule-status')).toContainText('Schedule updated');

  // Keep browser open briefly so humans can observe the flow in headed mode.
  const holdMs = Number(process.env.PLAYWRIGHT_HOLD_MS || '8000');
  await page.waitForTimeout(holdMs);
});
