import { expect, test } from '@playwright/test';

test('PAGE /vessel-connect ui smoke', async ({ page }) => {
  const base = process.env.BASE_URL || 'http://localhost:5173';
  const stepMs = Number(process.env.PLAYWRIGHT_STEP_MS || '450');

  const moveMouseTo = async (testId: string) => {
    const locator = page.getByTestId(testId);
    const box = await locator.boundingBox();
    if (!box) return;
    await page.mouse.move(box.x - 45, box.y - 20);
    await page.waitForTimeout(Math.max(200, Math.floor(stepMs / 2)));
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 22 });
  };

  await test.step('Open Vessel Connect simulator', async () => {
    await page.goto(`${base}/vessel-connect`);
    await expect(page.getByTestId('vc-vessel-name')).toHaveValue('');
    await expect(page.getByTestId('vc-port')).toHaveValue('');
    await expect(page.getByTestId('vc-eta')).toHaveValue('');
    await page.waitForTimeout(stepMs);
  });

  await test.step('Fill nomination form with visible pacing', async () => {
    await page.getByTestId('vc-vessel-name').click();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-vessel-name').fill('MT Playwright Live 101');
    await page.waitForTimeout(stepMs);

    await page.getByTestId('vc-port').click();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-port').fill('Rotterdam');
    await page.waitForTimeout(stepMs);

    await page.getByTestId('vc-eta').click();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-eta').fill('2026-03-21T09:15:00Z');
    await page.waitForTimeout(stepMs);
  });

  await test.step('Hover and submit nomination', async () => {
    await moveMouseTo('vc-submit');
    await page.getByTestId('vc-submit').hover();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-submit').click();
    await page.waitForTimeout(stepMs);
    await expect(page.getByTestId('vc-submit-status')).toContainText('Form submitted successfully');
    await expect(page.getByTestId('vc-nomination-id')).not.toHaveText('-');
  });

  await test.step('Fill schedule form and hover-click update', async () => {
    await page.getByTestId('vc-jetty').click();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-jetty').fill('Jetty-Blue-7');
    await page.waitForTimeout(stepMs);

    await page.getByTestId('vc-schedule-eta').click();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-schedule-eta').fill('2026-03-21T11:45:00Z');
    await page.waitForTimeout(stepMs);

    await moveMouseTo('vc-schedule-submit');
    await page.getByTestId('vc-schedule-submit').hover();
    await page.waitForTimeout(stepMs);
    await page.getByTestId('vc-schedule-submit').click();
    await page.waitForTimeout(stepMs);
    await expect(page.getByTestId('vc-schedule-status')).toContainText('Schedule updated');
    await expect(page.getByTestId('vc-calendar-count')).toContainText('Calendar Events:');
  });

  // Keep browser open briefly so humans can observe the flow in headed mode.
  const holdMs = Number(process.env.PLAYWRIGHT_HOLD_MS || '10000');
  await page.waitForTimeout(holdMs);
});
