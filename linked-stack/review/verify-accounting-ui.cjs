const { chromium } = require('C:/Users/-PC-/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const express = require('../haspelsync/node_modules/express');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
    const root = path.resolve(__dirname, '../haspelsync/public');
    const app = express();
    app.get('/i18n/all.js', (_req, res) => res.type('js').send(['en','de','pl','uk'].map(lang => fs.readFileSync(path.join(root, 'i18n', `${lang}.js`), 'utf8')).join('\n')));
    app.use(express.static(root));
    const server = app.listen(0, '127.0.0.1');
    await new Promise(resolve => server.once('listening', resolve));
    const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' });
    try {
        const context = await browser.newContext({ locale: 'uk-UA', viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
        await context.addInitScript(() => localStorage.setItem('language', 'uk'));
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        const now = Date.now();
        const spools = [
            { id: 5, used_weight: 125, remaining_weight: 875, initial_weight: 1000, spool_weight: 220, filament: { name: 'PLA Basic · Jade White', material: 'PLA', weight: 1000, vendor: { name: 'Bambu Lab' } } },
            { id: 6, used_weight: 80, remaining_weight: 920, initial_weight: 1000, spool_weight: 200, filament: { name: 'PETG · Graphite', material: 'PETG', weight: 1000, vendor: { name: 'Polymaker' } } },
        ];
        const bookings = [
            { id: 'a'.repeat(64), printerId: 'TEST', startedAt: now - 3600000, jobName: 'Органайзер для інструментів', spoolId: 5, grams: 42.85, terminalState: 'FINISH', status: 'booked', itemKey: 'filament0', cost: { currency: 'UAH', costMinor: 3214 }, result: { filament: { name: 'PLA Basic · Jade White' } } },
            { id: 'b'.repeat(64), printerId: 'TEST', startedAt: now - 7200000, jobName: 'Тримач котушки', spoolId: 6, grams: 18.2, terminalState: 'FINISH', status: 'booked', itemKey: 'filament0', cost: { currency: 'UAH', costMinor: 1638 }, result: { filament: { name: 'PETG · Graphite' } } },
            { id: 'c'.repeat(64), printerId: 'TEST', startedAt: now - 86400000, jobName: '=HYPERLINK("unsafe")', spoolId: 5, grams: 6.45, terminalState: 'CANCEL', status: 'uncertain', itemKey: 'filament0', cost: null, result: null },
        ];
        let profiles = [{ spoolId: 5, priceMinor: 75000, basisMilligrams: 1000000, currency: 'UAH', revision: 1 }];
        const weighings = [];
        let savedPrice, savedWeight, reviewed;
        await page.route('**/api/**', async route => {
            const request = route.request(), url = new URL(request.url()), method = request.method();
            let body = { ok: true };
            if (url.pathname === '/api/printers') body = [{ id: 'TEST', name: 'Bambu Lab P1S' }];
            else if (url.pathname.endsWith('/report')) body = { ok: true, bookings, printCount: 3, grams: 61.05, reviewCount: bookings.filter(b => b.status === 'uncertain').length, unknownCostCount: 0, totals: [{ currency: 'UAH', costMinor: 4852 }] };
            else if (url.pathname === '/api/spoolman/spools') body = spools;
            else if (/\/api\/spoolman\/spool\/\d+$/.test(url.pathname)) body = spools.find(s => s.id === Number(url.pathname.split('/').at(-1)));
            else if (url.pathname === '/api/accounting') body = { ok: true, profiles, weighings };
            else if (method === 'PUT' && url.pathname.includes('/cost/')) {
                savedPrice = request.postDataJSON();
                profiles = [{ ...profiles[0], priceMinor: 85000, revision: 2 }];
                body = { ok: true, profiles, weighings };
            } else if (method === 'POST' && url.pathname.includes('/weigh/')) {
                savedWeight = request.postDataJSON();
                spools[0].remaining_weight = 605;
                spools[0].used_weight = 395;
                weighings.unshift({ id: savedWeight.requestId, spoolId: 5, netMilligrams: 605000, status: 'recorded', createdAt: now });
                body = { ok: true, record: weighings[0] };
            } else if (method === 'POST' && url.pathname.endsWith('/resolve')) {
                reviewed = request.postDataJSON();
                bookings[2].status = 'dismissed';
            }
            await route.fulfill({ json: body });
        });
        await page.goto(`http://127.0.0.1:${server.address().port}/accounting.html`);
        await page.getByRole('heading', { name: 'Кожен грам під контролем' }).waitFor();
        await page.locator('#acc-history-body tr').nth(2).waitFor();
        assert.equal(await page.locator('#acc-review').textContent(), '1');
        await page.screenshot({ path: path.join(__dirname, 'accounting-history-uk.png'), fullPage: true });
        await page.locator('#acc-only-review').check();
        assert.equal(await page.locator('#acc-history-body tr').count(), 1);
        await page.getByRole('button', { name: 'Перевірити', exact: true }).click();
        await page.locator('#acc-review-dialog').waitFor({ state: 'visible' });
        await page.locator('#acc-review-resolution').selectOption('not_applied');
        await page.locator('#acc-review-note').fill('Звірено з журналом і залишком котушки.');
        await page.getByRole('button', { name: 'Зберегти результат перевірки' }).click();
        await page.locator('#acc-review-dialog').waitFor({ state: 'hidden' });
        assert.equal(reviewed.resolution, 'not_applied');
        await page.getByRole('tab', { name: 'Котушки та зважування' }).click();
        await page.locator('#acc-price').fill('850,00');
        await page.getByRole('button', { name: 'Зберегти ціну', exact: true }).click();
        await page.getByRole('status').filter({ hasText: 'Ціну збережено' }).waitFor();
        assert.equal(savedPrice.price, '850,00');
        await page.locator('#acc-gross').fill('825');
        await page.locator('#acc-tare').fill('220');
        assert.match(await page.locator('#acc-net').textContent(), /605/);
        await page.screenshot({ path: path.join(__dirname, 'accounting-weighing-uk.png'), fullPage: true });
        await page.getByRole('button', { name: 'Застосувати зважування' }).click();
        await page.getByRole('status').filter({ hasText: 'Зважування застосовано' }).waitFor();
        assert.equal(savedWeight.expectedUsedWeight, 125);
        await page.locator('#acc-weighings-body tr').first().waitFor();
        await page.getByRole('tab', { name: 'Звіти', exact: true }).click();
        const downloadPromise = page.waitForEvent('download');
        await page.getByRole('button', { name: 'Завантажити CSV' }).click();
        const download = await downloadPromise;
        const downloadPath = path.join(__dirname, 'sample-report.csv');
        await download.saveAs(downloadPath);
        assert.ok(fs.readFileSync(downloadPath, 'utf8').includes("'=HYPERLINK"));
        await page.screenshot({ path: path.join(__dirname, 'accounting-report-uk.png'), fullPage: true });
        await page.setViewportSize({ width: 390, height: 844 });
        await page.getByRole('tab', { name: 'Котушки та зважування' }).click();
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: path.join(__dirname, 'accounting-mobile-uk.png'), fullPage: true });
        await page.locator('#dark-mode-toggle').click();
        assert.ok(await page.locator('html').evaluate(el => el.classList.contains('dark-mode')));
        await page.screenshot({ path: path.join(__dirname, 'accounting-mobile-dark-uk.png'), fullPage: true });
        assert.deepEqual(errors, []);
        console.log('Ukrainian UI, history review, price, weighing, CSV, mobile and dark theme: passed.');
    } finally {
        await browser.close();
        await new Promise(resolve => server.close(resolve));
    }
})().catch(error => { console.error(error); process.exit(1); });
