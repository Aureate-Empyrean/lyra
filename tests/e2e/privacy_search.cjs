// Real browser + Lyra backend + real loopback provider HTTP. No aetest or live credentials.
// node --test tests/e2e/privacy_search.cjs
// Optional: PLAYWRIGHT_PATH, PYTHON, BROWSER (chromium/firefox/webkit).
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const readline = require('node:readline');
const playwright = require(process.env.PLAYWRIGHT_PATH || path.resolve(__dirname, '../../../mnemosyne/node_modules/playwright'));
const root = path.resolve(__dirname, '../..');
let child, browser, context, page, frame, base;
let opened = 0;
const browserRequests = [];
const errors = [];
const scenario = (name, run) => test(name, { timeout: 20000 }, run);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const counts = () => page.request.get(base + '/__fixture/counts').then(r => r.json());
const mode = body => page.request.post(base + '/__fixture/mode', { data: body });
async function open(route = '/') {
  await page.goto(base + '/?nav=1&route=' + encodeURIComponent(route) + '&fixture=' + ++opened);
  frame = page.frameLocator('#lyra');
  await frame.locator('#search').waitFor();
  await page.waitForFunction(() => document.querySelector('iframe').contentWindow !== null);
  await frame.locator('#view .page, #view .hero').first().waitFor();
  await sleep(150);
}
async function search(value) {
  await frame.locator('#search').fill(value);
  await frame.getByRole('heading', { name: `Results for “${value}”`, exact: true }).waitFor();
  await sleep(80);
}
async function navigate(name) {
  await frame.locator(`nav [data-nav="${name.toLowerCase()}"]`).click();
}

before(async () => {
  child = spawn(process.env.PYTHON || path.join(root, '.venv/Scripts/python.exe'), [path.join(__dirname, 'search_harness.py')], {
    cwd: root, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
  });
  base = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('Disposable harness startup timed out')), 20000);
    child.once('error', reject);
    child.stderr.on('data', chunk => process.stderr.write(chunk));
    child.once('exit', code => reject(Error('Harness exited: ' + code)));
    readline.createInterface({ input: child.stdout }).once('line', line => {
      clearTimeout(timer);
      try { resolve(JSON.parse(line).url); } catch (error) { reject(error); }
    });
  });
  browser = await playwright[process.env.BROWSER || 'chromium'].launch({ headless: true });
  context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => browserRequests.push({ path: new URL(request.url()).pathname, method: request.method() }));
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin !== base) return route.abort();
    return route.continue();
  });
}, { timeout: 30000 });

after(async () => {
  await browser?.close();
  if (child) {
    const exited = new Promise(resolve => child.once('exit', resolve));
    child.stdin.end('\n');
    await Promise.race([exited, sleep(7000)]);
    if (child.exitCode === null) child.kill();
  }
});

scenario('mount, typing, local/empty results and cached artwork cause zero provider HTTP requests', async () => {
  await open();
  const before = await counts();
  assert.deepEqual(before, { search: 0, images: 0, details: 0, recommendations: 0 });
  await frame.locator('#search').pressSequentially('Synthetic Orbit', { delay: 25 });
  await frame.getByRole('heading', { name: 'Results for “Synthetic Orbit”', exact: true }).waitFor();
  await frame.getByRole('button', { name: /Synthetic Orbit/ }).first().waitFor();
  await sleep(500);
  assert.deepEqual(await counts(), before);
  await search('Nothing in this synthetic library');
  assert.match(await frame.locator('#view').innerText(), /Nothing in your library matches/);
  assert.deepEqual(await counts(), before);
});

scenario('explicit search sends one POST and provider request; remote results retain preview/add functionality', async () => {
  await search('Synthetic');
  const before = await counts();
  await frame.getByRole('button', { name: 'Search TMDB', exact: true }).click();
  await frame.locator('#external-results [data-preview]').waitFor();
  assert.equal((await counts()).search, before.search + 1);
  assert.ok(browserRequests.some(r => r.path === '/lyra/api/search/external' && r.method === 'POST'));
  await frame.locator('#external-results [data-preview]').first().click();
  await frame.getByRole('button', { name: 'Load details from TMDB', exact: true }).waitFor();
  const prior = await counts();
  await frame.getByRole('button', { name: 'Load details from TMDB', exact: true }).click();
  await frame.getByRole('heading', { name: 'Synthetic Discovery', exact: true }).waitFor();
  assert.equal((await counts()).details, prior.details + 1);
  await frame.getByRole('button', { name: 'Add to watchlist', exact: true }).click();
  await frame.locator('[data-notes]').waitFor();
  assert.match(await frame.locator('#view').innerText(), /Synthetic Discovery/);
});

scenario('search refresh and real browser Back/Forward restore local state without provider requests', async () => {
  await search('Synthetic Orbit');
  await frame.getByRole('button', { name: 'Search TMDB', exact: true }).click();
  await frame.locator('#external-results [data-open]').waitFor();
  await sleep(150);
  const before = await counts();
  await navigate('Movies');
  await frame.locator('[data-filter]').first().waitFor();
  await page.goBack();
  await frame.getByRole('heading', { name: 'Results for “Synthetic Orbit”', exact: true }).waitFor();
  assert.equal(await frame.locator('#external-results').innerText(), '');
  await page.goForward();
  await frame.locator('[data-filter]').first().waitFor();
  await page.goBack();
  await frame.getByRole('button', { name: 'Search TMDB', exact: true }).waitFor();
  await page.reload();
  frame = page.frameLocator('#lyra');
  await frame.getByRole('heading', { name: 'Results for “Synthetic Orbit”', exact: true }).waitFor();
  await sleep(500);
  assert.deepEqual(await counts(), before);
});

scenario('direct Discover and preview URLs, empty queries and restores require renewed explicit intent', async () => {
  const before = await counts();
  await open('/discover');
  await frame.getByRole('button', { name: 'Browse TMDB recommendations', exact: true }).waitFor();
  assert.deepEqual(await counts(), before);
  await frame.locator('#search').fill('x');
  await sleep(450);
  await frame.locator('#search').fill('');
  await sleep(450);
  assert.deepEqual(await counts(), before);
  await frame.getByRole('button', { name: 'Browse TMDB recommendations', exact: true }).click();
  await frame.locator('#external-results .card').first().waitFor();
  assert.equal((await counts()).recommendations, before.recommendations + 3);
  const afterExplicit = await counts();
  await page.reload();
  frame = page.frameLocator('#lyra');
  await frame.getByRole('button', { name: 'Browse TMDB recommendations', exact: true }).waitFor();
  await open('/preview/movie/202');
  await frame.getByRole('button', { name: 'Load details from TMDB', exact: true }).waitFor();
  await frame.locator('#search').fill('x');
  await sleep(450);
  assert.equal(await frame.getByRole('button', { name: 'Load details from TMDB', exact: true }).isEnabled(), true);
  assert.deepEqual(await counts(), afterExplicit);
});

scenario('slow external response is ignored after query change; local error recovery still works', async () => {
  await open('/discover');
  await search('Synthetic slow request');
  await mode({ slow: true });
  const prior = await counts();
  await frame.getByRole('button', { name: 'Search TMDB', exact: true }).click();
  const deadline = Date.now() + 3000;
  while ((await counts()).search === prior.search) {
    assert.ok(Date.now() < deadline, 'explicit request reached loopback provider');
    await sleep(20);
  }
  await search('No synthetic match');
  await sleep(1000);
  assert.equal(await frame.locator('#external-results').innerText(), '');
  assert.match(await frame.locator('#view').innerText(), /Nothing in your library matches/);
  await mode({ fail: true });
  await frame.getByRole('button', { name: 'Search TMDB', exact: true }).click();
  await frame.locator('#external-results [role=alert]').waitFor();
  await search('Synthetic Orbit');
  assert.match(await frame.locator('#view').innerText(), /Synthetic Orbit/);
  await mode({});
  await frame.getByRole('button', { name: 'Search TMDB', exact: true }).click();
  await frame.locator('#external-results .card').waitFor();
});

scenario('no browser errors, unchanged filters, small-screen action and keyboard search', async () => {
  await navigate('Movies');
  await frame.locator('[data-filter=planned]').click();
  assert.equal(await frame.locator('[data-filter=planned]').getAttribute('aria-pressed'), 'true');
  await page.setViewportSize({ width: 390, height: 844 });
  await frame.locator('#search').fill('Synthetic');
  await frame.locator('#search').press('Enter');
  await frame.getByRole('button', { name: 'Search TMDB', exact: true }).waitFor();
  fs.mkdirSync(path.join(root, 'artifacts'), { recursive: true });
  await page.screenshot({ path: path.join(root, 'artifacts/wp01-search-phone.png'), fullPage: true, animations: 'disabled' });
  await page.setViewportSize({ width: 1440, height: 960 });
  await frame.getByRole('button', { name: 'Search TMDB', exact: true }).click();
  await frame.locator('#external-results .card').waitFor();
  await page.screenshot({ path: path.join(root, 'artifacts/wp01-search-desktop.png'), fullPage: true, animations: 'disabled' });
  assert.deepEqual(errors, []);
});

scenario('leaving during explicit discovery suppresses stale results and subsequent artwork requests', async () => {
  await open('/discover');
  await search('Synthetic navigation race');
  await mode({ slow: true });
  const before = await counts();
  await frame.getByRole('button', { name: 'Search TMDB', exact: true }).click();
  const deadline = Date.now() + 3000;
  while ((await counts()).search === before.search) {
    assert.ok(Date.now() < deadline);
    await sleep(20);
  }
  await navigate('Movies');
  await frame.locator('[data-filter]').first().waitFor();
  await sleep(1000);
  assert.equal(await frame.locator('#external-results').count(), 0);
  assert.equal((await counts()).images, before.images);
  await mode({});
  assert.deepEqual(errors, []);
});
