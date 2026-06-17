#!/usr/bin/env bash
set -euo pipefail
RUN_ID=${1:-manual_run}
OUT_DIR=/var/www/komunal-dom_ru/tmp_archive/ui_runs/${RUN_ID}
mkdir -p $OUT_DIR
if [ ! -d /tmp/pwcheck ]; then
  mkdir -p /tmp/pwcheck
  cd /tmp/pwcheck
  npm init -y >/dev/null 2>&1
  npm install playwright >/dev/null 2>&1
  npx playwright install chromium >/dev/null 2>&1
else
  cd /tmp/pwcheck
fi
cat > /tmp/pwcheck/verify_admin_buttons.js <<'NODE'
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const runId = process.argv[2];
  const outDir = `/var/www/komunal-dom_ru/tmp_archive/ui_runs/${runId}`;
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
  await page.goto('http://komunal-dom.ru/admin/login/', { waitUntil: 'networkidle' });
  await page.fill('input[name=username]', 'Admin_Aspect');
  await page.fill('input[name=password]', 'Aspect_Admin_2025');
  await Promise.all([
    page.waitForLoadState('networkidle'),
    page.click('input[type=submit], button[type=submit]')
  ]);
  const targets = [
    { name: 'company', url: 'http://komunal-dom.ru/admin/nsi/company/5/change/' },
    { name: 'user', url: 'http://komunal-dom.ru/admin/auth/user/1/change/' },
  ];
  const report = [];
  let hasErrors = false;
  for (const target of targets) {
    await page.goto(target.url, { waitUntil: 'networkidle' });
    await page.screenshot({ path: `${outDir}/${target.name}.png`, fullPage: true });
    const state = await page.evaluate(() => {
      const isVisible = (el) => {
        const style = getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetParent !== null;
      };
      const topRow = document.querySelector('.global-submit-row');
      const visibleTopButtons = topRow ? Array.from(topRow.querySelectorAll('input, button, a')).filter(isVisible).map(el => (el.value || el.textContent || '').trim()).filter(Boolean) : [];
      const closeButton = document.querySelector('.global-submit-row .close-form-link');
      const jazzyNode = document.querySelector('#jazzy-actions');
      const jazzyVisible = !!jazzyNode && getComputedStyle(jazzyNode).display !== 'none';
      const rightColVisible = Array.from(document.querySelectorAll('.row > .col-12.col-lg-3')).some(el => getComputedStyle(el).display !== 'none');
      const pageText = document.body?.innerText || '';
      const errorMarkers = ['FieldError', 'Traceback', 'Server Error (500)', 'Exception Type', 'Exception Value'].filter(marker => pageText.includes(marker));
      const closeButtonColor = closeButton ? getComputedStyle(closeButton).color : null;
      const departmentConstraint = (() => {
        const companySelect = document.querySelector('#id_primary_company');
        const departmentSelect = document.querySelector('#id_primary_department');
        if (!companySelect || !departmentSelect) {
          return null;
        }
        let departmentsByCompany = {};
        try {
          departmentsByCompany = JSON.parse(departmentSelect.dataset.departmentsByCompany || '{}');
        } catch (error) {
          departmentsByCompany = {};
        }
        const companyIds = Object.keys(departmentsByCompany).filter((companyId) => companyId);
        const chosenCompanyId = companyIds.find((companyId) => companyId !== String(companySelect.value || '')) || companyIds[0];
        if (!chosenCompanyId) {
          return { checked: false, reason: 'no-company-map' };
        }
        companySelect.value = chosenCompanyId;
        companySelect.dispatchEvent(new Event('change', { bubbles: true }));
        const renderedOptions = Array.from(departmentSelect.options).map((option) => ({
          value: option.value,
          text: option.textContent.trim(),
        }));
        const expectedOptions = (departmentsByCompany[chosenCompanyId] || []).map((department) => ({
          value: String(department.id),
          text: department.name,
        }));
        const actualNonEmpty = renderedOptions.filter((option) => option.value);
        const matches = actualNonEmpty.length === expectedOptions.length
          && actualNonEmpty.every((option, index) => option.value === expectedOptions[index].value && option.text === expectedOptions[index].text);
        return {
          checked: true,
          chosenCompanyId,
          expectedCount: expectedOptions.length,
          actualCount: actualNonEmpty.length,
          matches,
        };
      })();
      return { topRow: !!topRow, visibleTopButtons, jazzyVisible, rightColVisible, h1: document.querySelector('h1')?.textContent?.trim() || '', url: location.href, errorMarkers, closeButtonColor, departmentConstraint };
    });
    if (
      state.errorMarkers.length > 0 ||
      (state.closeButtonColor && state.closeButtonColor !== 'rgb(255, 255, 255)') ||
      (state.departmentConstraint && state.departmentConstraint.checked && !state.departmentConstraint.matches)
    ) {
      hasErrors = true;
    }
    report.push({ target: target.name, ...state });
  }
  fs.writeFileSync(`${outDir}/report.json`, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  await browser.close();
  if (hasErrors) {
    process.exit(1);
  }
})();
NODE
node /tmp/pwcheck/verify_admin_buttons.js $RUN_ID
