// Browser -> local TCP HTTP -> Rust -> the literal synthetic PostgreSQL fixture.
// Application HTTP and WebSocket requests are intercepted before opening a page.
// This fixture bridge is not a general network sandbox for arbitrary code.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { createInterface } from 'node:readline';
import { once } from 'node:events';
import assert from 'node:assert/strict';

const [siteArgument, binaryArgument, toolsArgument, evidenceArgument] = process.argv.slice(2);
if (process.argv.length !== 6) throw new Error('usage: run.mjs SITE SYNTHETIC_BINARY ENVIRONMENT EVIDENCE_JSON');
if (process.env.MRJAM_SYNTHETIC_DATABASE_URL !== 'postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic') {
  console.error(JSON.stringify({ code: 'SYNTHETIC_DATABASE_REQUIRED' }));
  process.exit(2);
}
const site = fs.realpathSync(siteArgument);
const binary = fs.realpathSync(binaryArgument);
const tools = fs.realpathSync(toolsArgument);
const require = createRequire(import.meta.url);
const { chromium, expect } = require(path.join(tools, 'node_modules/@playwright/test'));
assert.equal(require(path.join(tools, 'node_modules/@playwright/test/package.json')).version, '1.64.1');
const origin = 'https://principiipetit.io';
const storageKey = 'matheval-participation-v1';
const sha = value => createHash('sha256').update(value).digest('hex');
const report = {
  schema_version: 1, started_at_utc: new Date().toISOString(), status: 'failed',
  scope: 'Synthetic questionnaire only, browser routes bridged to real local HTTP and PostgreSQL',
  production_access: false, deployment_authorized: false, authoritative_validation: false,
  playwright_version: '1.64.1', binary_sha256: sha(fs.readFileSync(binary)),
  survey_sha256: sha(fs.readFileSync(path.join(site, 'survey.js'))),
  bank_fixture_sha256: sha(fs.readFileSync(path.join(site, 'data/bank.json'))),
  checks: [], http_results: {}, blocked_external_requests: 0, blocked_websockets: 0, missing_static_resources: 0,
  limitations: ['No production TLS, Nginx, DNS or deployment exercised', 'Public questionnaire replaced only in disposable view by declared synthetic bank', 'Scientific administration, exports and all other frontends remain unqualified']
};
let browser, child, exit, port, dropNextSave = false, blockSaves = false, lostPayload, lostPath, repeatedPayload = false;
const pageErrors = [];
const allowedEnvironment = /^(PATH|HOME|TMPDIR|LANG|LC_ALL|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|NO_PROXY|http_proxy|https_proxy|all_proxy|no_proxy|NODE_EXTRA_CA_CERTS|SSL_CERT_FILE|SSL_CERT_DIR|REQUESTS_CA_BUNDLE|CODEX_PROXY_CERT|PLAYWRIGHT_BROWSERS_PATH|MRJAM_SYNTHETIC_DATABASE_URL)$/;
const environment = Object.fromEntries(Object.entries(process.env).filter(([name]) => allowedEnvironment.test(name)));
function localRequest(method, pathname, headers = {}, body) {
  return new Promise((resolve, reject) => {
    const request = http.request({ hostname: '127.0.0.1', port, path: pathname, method, headers: { ...headers, host: '127.0.0.1', connection: 'close' }, timeout: 15000 }, response => {
      const chunks = []; let size = 0;
      response.on('data', chunk => { size += chunk.length; if (size > 8 * 1024 * 1024) request.destroy(new Error('LOCAL_RESPONSE_LIMIT')); else chunks.push(chunk); });
      response.on('error', reject);
      response.on('end', () => {
        const key = `${method}:${response.statusCode}`;
        report.http_results[key] = (report.http_results[key] || 0) + 1;
        resolve({ status: response.statusCode, headers: response.headers, body: Buffer.concat(chunks) });
      });
    });
    request.on('timeout', () => request.destroy(new Error('LOCAL_REQUEST_TIMEOUT')));
    request.on('error', reject);
    request.end(body);
  });
}
async function context(storageState) {
  const result = await browser.newContext({ reducedMotion: 'reduce', serviceWorkers: 'block', viewport: { width: 1280, height: 900 }, storageState });
  await result.routeWebSocket('**/*', socket => { report.blocked_websockets++; socket.close(); });
  await result.route('**/*', async route => {
    try {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin || !url.pathname.startsWith('/matheval/')) {
      report.blocked_external_requests++;
      return await route.abort('blockedbyclient');
    }
    if (url.pathname.startsWith('/matheval/api/')) {
      if (blockSaves && request.method() === 'PUT') return await route.abort('internetdisconnected');
      const body = request.postDataBuffer();
      const response = await localRequest(request.method(), url.pathname + url.search, request.headers(), body);
      if (request.method() === 'POST' && url.pathname === '/matheval/api/sessions') {
        assert.equal(request.headers().authorization, undefined);
        assert.equal(request.headers().origin, origin);
      }
      if (request.method() === 'PUT' && response.status === 200 && dropNextSave) {
        dropNextSave = false; lostPayload = body; lostPath = url.pathname;
        return await route.abort('failed'); // The transaction has committed; only its acknowledgement is lost.
      }
      if (request.method() === 'PUT' && lostPayload && url.pathname === lostPath && Buffer.compare(body, lostPayload) === 0) repeatedPayload = true;
      const headers = Object.fromEntries(Object.entries(response.headers).filter(([name, value]) => !['connection', 'transfer-encoding', 'content-length'].includes(name) && typeof value === 'string'));
      return await route.fulfill({ status: response.status, headers, body: response.body });
    }
    let filename;
    try {
      const relative = decodeURIComponent(url.pathname.slice('/matheval/'.length)) || 'index.html';
      filename = fs.realpathSync(path.join(site, relative));
      if (!filename.startsWith(site + path.sep) || !fs.statSync(filename).isFile()) throw new Error('STATIC_PATH_REFUSED');
    } catch {
      report.missing_static_resources++;
      return await route.fulfill({ status: 404, body: 'SYNTHETIC_RESOURCE_MISSING' });
    }
    const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf' };
    return await route.fulfill({ status: 200, contentType: types[path.extname(filename)] || 'application/octet-stream', body: fs.readFileSync(filename) });
    } catch {
      report.route_failure = true;
      try { await route.abort('failed'); } catch { /* The browser may already be closed. */ }
    }
  });
  return result;
}
const localRecord = page => page.evaluate(key => JSON.parse(localStorage.getItem(key)), storageKey);
async function saved(page) {
  await expect.poll(async () => { const local = await localRecord(page); return Boolean(local?.revision > 0 && local.savedRevision === local.revision); }, { timeout: 15000 }).toBe(true);
}
async function remote(record, suffix = '') {
  const response = await localRequest('GET', `/matheval/api/sessions/${record.id}${suffix}`, { 'x-session-token': record.secret });
  assert.equal(response.status, 200);
  assert.equal(response.headers['cache-control'], 'no-store');
  return JSON.parse(response.body);
}
try {
  child = spawn(binary, [], { stdio: ['ignore', 'pipe', 'pipe'], env: environment });
  exit = once(child, 'exit');
  let stderrBytes = 0;
  child.stderr.on('data', chunk => { stderrBytes += chunk.length; }); // Never re-emit diagnostics.
  const lines = createInterface({ input: child.stdout });
  const ready = await Promise.race([once(lines, 'line'), exit.then(() => { throw new Error('SYNTHETIC_SERVER_EXITED'); }), new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error('SYNTHETIC_SERVER_START_TIMEOUT')), 30000); timer.unref(); })]);
  const data = JSON.parse(ready[0]);
  assert.equal(data.status, 'ready');
  assert.equal(Number.isInteger(data.port) && data.port > 1024 && data.port <= 65535, true);
  port = data.port;
  browser = await chromium.launch({ headless: true });
  report.chromium_version = browser.version();
  assert.equal(browser.version(), '156.0.8078.4');
  let session = await context();
  let page = await session.newPage();
  page.on('pageerror', () => pageErrors.push('PAGE_ERROR'));
  await page.goto(`${origin}/matheval/`);
  const checkbox = page.getByRole('checkbox', { name: '3e', exact: true });
  await checkbox.click();
  await expect(checkbox).toBeChecked();
  const createdPromise = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/api/sessions'));
  await page.getByRole('button', { name: 'Commencer', exact: true }).click();
  const createdResponse = await createdPromise;
  assert.equal(createdResponse.status(), 201);
  const created = await createdResponse.json();
  assert.equal(created.secret, undefined);
  assert.equal(created.token_hash, undefined);
  assert.equal(created.questions.length, 2);
  report.checks.push('public_pseudonymous_creation_persisted_without_sso_or_secret_echo');
  await page.getByRole('button', { name: 'Passer l’aide', exact: true }).click();
  await expect(page.locator('#reading-card')).toBeVisible();
  await expect(page.locator('#grade')).toHaveAttribute('aria-valuetext', 'Non noté');
  const firstId = await page.locator('#reading-card').getAttribute('production-id');
  await page.getByRole('slider', { name: 'Note sur 3' }).press('Home');
  await expect(page.locator('#grade')).toHaveValue('0');
  await saved(page);
  let record = await localRecord(page);
  let stored = await remote(record);
  assert.equal(stored.snapshot.answers[firstId].note, 0);
  assert.equal(stored.snapshot.answers[firstId].initialNote, null);
  assert.deepEqual(stored.snapshot, record.snapshot);
  report.checks.push('zero_grade_and_null_initial_grade_survive_postgresql_round_trip');
  await page.reload();
  await expect(page.locator('#grade')).toHaveValue('0');
  assert.equal((await localRecord(page)).id, record.id);
  report.checks.push('browser_reload_restores_same_participation_and_answer');
  // resume() schedules a flush after 300 ms. Let that prior operation finish
  // before injecting a distinct acknowledgement loss, otherwise it may retry
  // automatically before a human can activate the transient retry button.
  await page.waitForTimeout(500);
  await saved(page);
  dropNextSave = true;
  await page.getByRole('slider', { name: 'Note sur 3' }).press('ArrowRight');
  await expect(page.getByRole('button', { name: 'Réessayer l’enregistrement', exact: true })).toBeVisible();
  assert.ok(lostPayload);
  record = await localRecord(page);
  assert.ok(record.revision > record.savedRevision);
  assert.equal((await remote(record)).snapshot.answers[firstId].note, 0.25);
  const journalBeforeRetry = await remote(record, '/events');
  // Diagnose the pointer path separately from the tested keyboard retry.
  const retryButton = page.getByRole('button', { name: 'Réessayer l’enregistrement', exact: true });
  let retryScrollable = true;
  try { await retryButton.scrollIntoViewIfNeeded({ timeout: 2000 }); } catch { retryScrollable = false; }
  report.pointer_retry = await retryButton.evaluate(element => {
    const box = element.getBoundingClientRect();
    const top = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return { top_is_retry_button: Boolean(top && element.contains(top)), covered_by_reading_card: Boolean(top?.closest('#reading-card')), top_tag: top?.tagName || null, top_id: top?.id || null, button_y: box.y, button_height: box.height, viewport_height: innerHeight, document_height: document.documentElement.scrollHeight, body_overflow: getComputedStyle(document.body).overflow, html_overflow: getComputedStyle(document.documentElement).overflow };
  });
  report.pointer_retry.scrollable = retryScrollable;
  try { await retryButton.click({ trial: true, timeout: 2000 }); report.pointer_retry.actionable = true; }
  catch { report.pointer_retry.actionable = false; }
  await page.getByRole('button', { name: 'Réessayer l’enregistrement', exact: true }).press('Enter');
  await saved(page);
  assert.equal(repeatedPayload, true);
  assert.deepEqual(await remote(await localRecord(page), '/events'), journalBeforeRetry);
  report.checks.push('lost_commit_acknowledgement_retries_identical_revision_without_duplicate_events');
  // A second, pre-commit transport outage tests retry from the ordinary workspace.
  blockSaves = true;
  await page.locator('#validate-reading').click();
  await expect(page.locator('#reading-card')).toHaveCount(0);
  const ordinaryRetry = page.getByRole('button', { name: 'Réessayer l’enregistrement', exact: true });
  await expect(ordinaryRetry).toBeVisible();
  await ordinaryRetry.click({ trial: true });
  report.pointer_retry.actionable_after_closing_reader = true;
  blockSaves = false;
  await ordinaryRetry.click();
  await saved(page);
  report.checks.push('pre_commit_outage_preserves_local_copy_and_pointer_retry_works_after_closing_reader');
  await page.getByRole('button', { name: 'Rédaction 1', exact: true }).click();
  await saved(page);
  record = await localRecord(page);
  const storageState = await session.storageState();
  await session.close();
  session = await context(storageState);
  page = await session.newPage();
  page.on('pageerror', () => pageErrors.push('PAGE_ERROR'));
  await page.goto(`${origin}/matheval/`);
  await expect(page.locator('#grade')).toHaveValue('0.25');
  await expect(page.locator('#reading-card')).toHaveAttribute('production-id', firstId);
  assert.equal((await localRecord(page)).id, record.id);
  report.checks.push('fresh_browser_context_restores_saved_local_record_against_durable_session');
  const otherSecret = 'f'.repeat(64);
  assert.notEqual(otherSecret, record.secret);
  const otherCreated = await localRequest('POST', '/matheval/api/sessions', { origin, 'x-matheval-request': '1', 'content-type': 'application/json' }, JSON.stringify({ id: '00000000-0000-4000-8000-000000000099', secret: otherSecret, bankVersion: '1.0.0', levels: ['3e'], seed: 2 }));
  assert.equal(otherCreated.status, 201);
  const denied = await localRequest('GET', `/matheval/api/sessions/${record.id}`, { 'x-session-token': otherSecret });
  assert.equal(denied.status, 401);
  assert.deepEqual(JSON.parse(denied.body), { error: 'Accès à cette participation refusé.' });
  const admin = await localRequest('GET', '/matheval/api/admin');
  assert.equal(admin.status, 503);
  report.checks.push('other_participation_secret_refused_and_scientific_administration_closed');
  // Finish through the real interface, deliberately leave some answers absent.
  for (let step = 0; step < 2; step++) {
    await page.locator('#validate-reading').click();
    await expect(page.locator('#reading-card')).toHaveCount(0);
    if (await page.locator('[data-testid="context-help"]').count()) await page.locator('[data-testid="context-help"]').getByRole('button', { name: /Compris|Fermer/ }).click();
    await page.locator('#next-production').click();
    await page.getByRole('button', { name: 'Passer quand même', exact: true }).click();
    if (step === 0) await expect(page.locator('#reading-card')).toBeVisible();
  }
  await expect(page.locator('[data-testid="finish-panel-mrjam"]')).toBeVisible();
  const finalPromise = page.waitForResponse(response => response.request().method() === 'PUT' && response.request().postDataJSON()?.final === true);
  await page.getByRole('button', { name: 'Valider ma participation', exact: true }).click();
  const finalResponse = await finalPromise;
  assert.equal(finalResponse.status(), 200);
  assert.ok((await finalResponse.json()).completedAt);
  await expect(page.getByText('Vos réponses ont bien été reçues.', { exact: false })).toBeVisible();
  record = await localRecord(page);
  stored = await remote(record);
  assert.ok(stored.completedAt);
  assert.deepEqual(stored.snapshot, record.snapshot);
  assert.equal(Object.values(stored.snapshot.answers).some(answer => answer.note === null), true);
  assert.deepEqual(await remote(record, '/events'), record.events);
  await page.reload();
  await expect(page.getByText('Vos réponses ont bien été reçues.', { exact: false })).toBeVisible();
  report.checks.push('final_validation_commits_snapshot_and_event_journal_and_survives_reload');
  assert.deepEqual(pageErrors, []);
  assert.equal(report.blocked_external_requests, 0);
  assert.equal(report.blocked_websockets, 0);
  assert.notEqual(report.route_failure, true);
  assert.equal(report.missing_static_resources, 0);
  assert.equal(stderrBytes, 0);
  report.checks.push('all_static_resources_local_no_page_exception_no_server_diagnostic');
  await session.close();
  report.status = 'passed';
} catch (error) {
  // Fail without serializing synthetic participation IDs, tokens, answers or diagnostics.
  report.failure_code = 'BROWSER_QUALIFICATION_FAILED';
  report.failure_kind = error?.constructor?.name || 'Error';
  report.failure_line = Number(error?.stack?.match(/run\.mjs:(\d+):/)?.[1]) || null;
  console.error(JSON.stringify({ status: 'failed', completed_checks: report.checks, failure_kind: report.failure_kind, failure_line: report.failure_line }));
  process.exitCode = 1;
} finally {
  if (browser) {
    try { await browser.close(); }
    catch { report.status = 'failed'; report.failure_code = 'BROWSER_CLEANUP_FAILED'; process.exitCode = 1; }
  }
  if (child && child.exitCode === null) child.kill('SIGTERM');
  if (exit) {
    const stopped = await Promise.race([exit, new Promise(resolve => { const timer = setTimeout(() => resolve(null), 15000); timer.unref(); })]);
    if (!stopped || stopped[0] !== 0) { report.status = 'failed'; report.failure_code = 'SYNTHETIC_SERVER_CLEANUP_FAILED'; process.exitCode = 1; if (!stopped) child.kill('SIGKILL'); }
    else report.checks.push('synthetic_server_graceful_shutdown_and_own_schema_cleanup');
  }
  report.finished_at_utc = new Date().toISOString();
  report.runner_sha256 = sha(fs.readFileSync(new URL(import.meta.url)));
  fs.writeFileSync(evidenceArgument, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ status: report.status, checks: report.checks.length }));
}
