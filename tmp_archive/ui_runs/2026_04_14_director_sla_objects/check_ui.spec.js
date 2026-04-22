const { test, expect } = require('playwright/test');

test.use({
  storageState: '/tmp/codex_playwright_storage_150.json',
  viewport: { width: 1440, height: 1400 },
  ignoreHTTPSErrors: true,
});

const shots = '/var/www/komunal-dom_ru/tmp_archive/ui_runs/2026_04_14_director_sla_objects';

test('dashboard and admin ui', async ({ page }) => {
  await page.goto('http://komunal-dom.ru/director/', { waitUntil: 'networkidle' });
  await expect(page.getByText('??????? ????????????')).toBeVisible();
  await page.screenshot({ path: `${shots}/director_dashboard.png`, fullPage: true });

  await page.goto('http://komunal-dom.ru/chief-engineer/', { waitUntil: 'networkidle' });
  await expect(page.getByText('??????? ??????')).toBeVisible();
  await page.screenshot({ path: `${shots}/chief_engineer_dashboard.png`, fullPage: true });

  await page.goto('http://komunal-dom.ru/director/service-objects/import/', { waitUntil: 'networkidle' });
  await expect(page.getByText('?????? ???????? ????????????')).toBeVisible();
  await page.screenshot({ path: `${shots}/service_object_import.png`, fullPage: true });

  await page.goto('http://komunal-dom.ru/admin/work_orders/companyroutemapping/add/', { waitUntil: 'networkidle' });
  await page.evaluate(() => {
    const select = document.querySelector('#id_company');
    if (!select) return;
    const option = document.createElement('option');
    option.value = '1';
    option.textContent = '??? ?? ??????';
    option.selected = true;
    select.appendChild(option);
    select.value = '1';
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.waitForTimeout(300);
  const optionTexts = await page.locator('#id_target_department option').allTextContents();
  console.log('TARGET_DEPARTMENT_OPTIONS=' + JSON.stringify(optionTexts));
  if (optionTexts.length < 2) throw new Error('target_department was not rebuilt after company selection');
  await page.screenshot({ path: `${shots}/company_route_mapping_add.png`, fullPage: true });
});
