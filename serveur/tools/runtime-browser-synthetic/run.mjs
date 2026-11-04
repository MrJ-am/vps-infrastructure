// Four unchanged Nix frontends -> real Rust CLI -> disposable PostgreSQL.
// Every browser HTTP route is installed before any page is opened. There is no
// static-file substitute: HTML, JS, CSS and fonts all pass through the CLI.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import net from 'node:net';
import { createHash, randomBytes } from 'node:crypto';
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';
import { startServices, owner, browserCookie, csrf, password } from './services.mjs';
import { checkedPins } from './artifact_pins.mjs';

const args = process.argv.slice(2);
const literalDatabase = 'postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic';
if (process.env.MRJAM_SYNTHETIC_DATABASE_URL !== literalDatabase || Object.keys(process.env).some(name => name.startsWith('PG'))) {
  console.error(JSON.stringify({ code: 'SYNTHETIC_DATABASE_REQUIRED' })); process.exit(2);
}
if (![4, 6, 8].includes(args.length)) {
  console.error(JSON.stringify({ code: 'EXPECTED_BINARY_ARTIFACTS_ENVIRONMENT_EVIDENCE_AND_OPTIONAL_LOADER_LIBRARIES_PINS' })); process.exit(2);
}
const sha = value => createHash('sha256').update(value).digest('hex');
const here = path.dirname(fileURLToPath(import.meta.url));
const identities = {
  mateval: { host: 'principiipetit.io', mount: '/matheval/', hash: '4ba21c4b0bda422be1a60e08639dd486642829b1539d6e5c8793f9fe45345816' },
  vision: { host: 'vision.mrj.am', mount: '/', hash: 'a1b03d1a4b84ff9569ff3f914664e91d67168e548c47ca3e61bdcd9b2c5eaf5a' },
  log: { host: 'log.mrj.am', mount: '/', hash: '0da3a226c890b83fc157bae323d5f1f54525944d415e5553087818ecf084245d' },
  audition: { host: 'audition.mrj.am', mount: '/', hash: '73044b762807d1c5d6f20cdaea668ddc7c92d3b68dd0d90f4aa002759e51e587' },
};
const allowedHosts = new Set(Object.values(identities).map(item => item.host));
const types = { html: 'text/html; charset=utf-8', js: 'text/javascript; charset=utf-8', mjs: 'text/javascript; charset=utf-8', css: 'text/css; charset=utf-8', json: 'application/json', txt: 'text/plain; charset=utf-8', md: 'text/plain; charset=utf-8', svg: 'image/svg+xml', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', ico: 'image/x-icon', woff: 'font/woff', woff2: 'font/woff2', ttf: 'font/ttf', otf: 'font/otf' };
const report = {
  schema_version: 1, started_at_utc: new Date().toISOString(), status: 'failed',
  scope: 'Four unchanged Nix frontends served by the configured Rust CLI; public questionnaire and entirely invented participants, accounts, answers and content',
  production_access: false, authoritative_validation: false, deployment_authorized: false,
  artifacts: {}, checks: [], http_results: {}, browser_http_results: {}, page_errors: 0,
  route_errors: 0, blocked_external_requests: 0, blocked_websockets: 0,
  limitations: [
    'Local browser routing bridge, not a general network sandbox for arbitrary code',
    'No public DNS, TLS termination, Nginx, NixOS activation or production traffic exercised',
    'Identity gateway, embedding model and native Kanidm protocol are explicit synthetic fixtures',
    'No OIDC, real SSO, invitation, MFA, real embedding quality or backup/restoration qualification',
    'Selected UI journeys and configured capabilities only; not every business contract or account lifecycle',
  ],
};
let stage = 'validate-inputs', browser, server, services, fixtureRoot, evidence, fixtureCreated = false;
let serverExit, port, binary, binaryDigest, launcher, configuration;
const contexts = [];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const environmentNames = /^(PATH|HOME|TMPDIR|LANG|LC_ALL|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|NO_PROXY|http_proxy|https_proxy|all_proxy|no_proxy|NODE_EXTRA_CA_CERTS|SSL_CERT_FILE|SSL_CERT_DIR|REQUESTS_CA_BUNDLE|CODEX_PROXY_CERT|PLAYWRIGHT_BROWSERS_PATH|MRJAM_SYNTHETIC_DATABASE_URL)$/;
const environment = Object.fromEntries(Object.entries(process.env).filter(([name]) => environmentNames.test(name)));

function file(location, maximum = 16 * 1024 * 1024) {
  const info = fs.lstatSync(location);
  assert.ok(info.isFile() && !info.isSymbolicLink() && info.size <= maximum);
  assert.equal(fs.realpathSync(location), location);
  return fs.readFileSync(location);
}

function fixture(action, bank) {
  const child = spawnSync('python3', [path.join(here, 'fixture.py'), action, fixtureRoot, ...(bank ? [bank] : [])], { env: environment, encoding: 'utf8', timeout: 180000, maxBuffer: 65536 });
  if (child.status !== 0) {
    try { const code = JSON.parse(child.stderr).code; if (/^[A-Z_]+$/.test(code)) report.fixture_error_code = code; } catch { /* Closed diagnostic only. */ }
    throw new Error('FIXTURE_FAILED');
  }
  return JSON.parse(child.stdout);
}

function command(arguments_) {
  const commandLine = launcher ? [launcher.path, '--library-path', launcher.libraries, binary, ...arguments_] : [binary, ...arguments_];
  return [commandLine[0], commandLine.slice(1)];
}

function invoke(arguments_) {
  const [program, argumentsList] = command(arguments_);
  return spawnSync(program, argumentsList, { env: environment, timeout: 30000, encoding: 'utf8', maxBuffer: 65536 });
}

async function localRequest(host, method, pathname, headers = {}, body, fixturePort = port) {
  assert.ok(allowedHosts.has(host) || host === 'unexpected.invalid');
  assert.ok(Number.isInteger(fixturePort) && fixturePort > 0 && fixturePort <= 65535);
  assert.ok(pathname.startsWith('/') && !pathname.startsWith('//'));
  return await new Promise((resolve, reject) => {
    const request = http.request({ hostname: '127.0.0.1', port: fixturePort, path: pathname, method,
      headers: { ...headers, host, connection: 'close' }, timeout: 30000 }, response => {
      const parts = []; let size = 0;
      response.on('data', chunk => { size += chunk.length; if (size > 16 * 1024 * 1024) request.destroy(new Error('RESPONSE_LIMIT')); else parts.push(chunk); });
      response.on('error', reject);
      response.on('end', () => {
        const key = `${host}:${method}:${response.statusCode}`;
        report.http_results[key] = (report.http_results[key] || 0) + 1;
        resolve({ status: response.statusCode, headers: response.headers, body: Buffer.concat(parts) });
      });
    });
    request.on('timeout', () => request.destroy(new Error('LOCAL_TIMEOUT')));
    request.on('error', reject);
    request.end(body);
  });
}

async function check(name, action) {
  stage = name;
  await action();
  report.checks.push({ name, status: 'passed' });
  console.log(JSON.stringify({ code: 'CHECK_PASSED', check: name }));
}

async function context() {
  const result = await browser.newContext({ reducedMotion: 'reduce', serviceWorkers: 'block', viewport: { width: 1280, height: 900 } });
  contexts.push(result);
  await result.routeWebSocket('**/*', socket => { report.blocked_websockets++; socket.close(); });
  await result.route('**/*', async route => {
    try {
      const request = route.request(), url = new URL(request.url());
      if (url.protocol !== 'https:' || !allowedHosts.has(url.hostname) || url.port || url.username || url.password) {
        report.blocked_external_requests++;
        return await route.abort('blockedbyclient');
      }
      const auth = ['vision.mrj.am', 'audition.mrj.am'].includes(url.hostname) && url.pathname.startsWith('/auth/');
      const requestKey = `${url.hostname}:${request.method()}:${auth ? 'fixture-auth' : url.pathname.includes('/api') ? 'rust-api' : 'rust-assets'}`;
      report.browser_request_starts ??= {};
      report.browser_request_starts[requestKey] = (report.browser_request_starts[requestKey] || 0) + 1;
      const headers = await request.allHeaders();
      delete headers['content-length'];
      const response = await localRequest(url.hostname, request.method(), url.pathname + url.search,
        headers, request.postDataBuffer(), auth ? services.ports.identity : port);
      const key = `${url.hostname}:${auth ? 'fixture-auth' : url.pathname.includes('/api') ? 'rust-api' : 'rust-assets'}:${response.status}`;
      report.browser_http_results[key] = (report.browser_http_results[key] || 0) + 1;
      const outgoing = Object.fromEntries(Object.entries(response.headers)
        .filter(([name]) => !['connection', 'transfer-encoding', 'content-length'].includes(name))
        .map(([name, value]) => [name, Array.isArray(value) ? value.join('\n') : String(value)]));
      await route.fulfill({ status: response.status, headers: outgoing, body: response.body });
    } catch {
      report.route_errors++;
      try { await route.abort('failed'); } catch { /* Context already closed. */ }
    }
  });
  result.on('page', page => page.on('pageerror', () => report.page_errors++));
  return result;
}

async function fonts(page, name) {
  const result = await page.evaluate(async () => {
    await document.fonts.ready;
    return { loaded: [...document.fonts].filter(font => font.status === 'loaded').length,
      errors: [...document.fonts].filter(font => font.status === 'error').length,
      images_missing: [...document.images].filter(image => image.src && (!image.complete || image.naturalWidth === 0)).length };
  });
  assert.equal(result.errors, 0);
  assert.equal(result.images_missing, 0);
  assert.ok(result.loaded > 0);
  report.browser_resources ??= {};
  report.browser_resources[name] = result;
}

try {
  assert.equal(process.version, 'v24.19.0');
  binary = fs.realpathSync(args[0]);
  binaryDigest = sha(file(binary, 128 * 1024 * 1024));
  report.binary_sha256 = binaryDigest;
  const assetsRoot = fs.realpathSync(args[1]);
  const environmentRoot = fs.realpathSync(args[2]);
  evidence = path.resolve(args[3]);
  assert.ok(!fs.existsSync(evidence));
  const pins = args.length === 8 ? checkedPins(file(fs.realpathSync(args[6]), 8192), args[7]) : null;
  if (pins) {
    assert.equal(binaryDigest, pins.server_sha256);
    report.qualified_artifact_pins = { sha256: args[7], ...pins };
    for (const [name, hash] of Object.entries(pins.frontends)) identities[name].hash = hash;
  }
  const require = createRequire(import.meta.url);
  const { chromium, expect } = require(path.join(environmentRoot, 'node_modules/@playwright/test'));
  assert.equal(require(path.join(environmentRoot, 'node_modules/@playwright/test/package.json')).version, '1.64.1');
  report.playwright_version = '1.64.1';
  const artifacts = [];
  for (const [name, identity] of Object.entries(identities)) {
    const directory = path.join(assetsRoot, name);
    const manifestBytes = file(path.join(directory, 'artifact.json'));
    assert.equal(sha(manifestBytes), identity.hash);
    const manifest = JSON.parse(manifestBytes);
    const prefix = pins ? '' : `share/mrjam/${name}/`;
    if (pins) assert.equal(manifest.input_manifest_sha256, pins.proposal_sha256);
    let size = 0;
    for (const [relative, expected] of Object.entries(manifest.payload_sha256)) {
      assert.ok(relative.startsWith(prefix) && relative.split('/').every(part => part && part !== '.' && part !== '..'));
      const bytes = file(path.join(directory, relative));
      assert.equal(sha(bytes), expected); size += bytes.length;
    }
    report.artifacts[name] = { manifest_sha256: identity.hash, payload_files: Object.keys(manifest.payload_sha256).length,
      payload_bytes: size, source_commits: manifest.source_commits, style_revision: manifest.style_revision };
    artifacts.push({ name, manifest, directory, prefix, ...identity });
  }
  if (args.length >= 6) {
    launcher = { path: fs.realpathSync(args[4]), libraries: fs.realpathSync(args[5]) };
    report.execution = { kind: 'unchanged-ELF-with-explicit-copied-loader', loader_sha256: sha(file(launcher.path)), libraries_sha256: {} };
    for (const name of fs.readdirSync(launcher.libraries).sort()) report.execution.libraries_sha256[name] = sha(file(path.join(launcher.libraries, name)));
  } else report.execution = { kind: 'native-explicit-binary' };
  fixtureRoot = path.join(os.tmpdir(), `mrjam-runtime-browser-${randomBytes(8).toString('hex')}`);
  fs.mkdirSync(fixtureRoot, { mode: 0o700 });
  await check('create-isolated-synthetic-databases-and-native-TLS-fixture', async () => {
    fixtureCreated = true;
    fixture('setup', path.join(assetsRoot, 'mateval', pins ? 'data/bank.json' : 'share/mrjam/mateval/data/bank.json'));
    const state = JSON.parse(file(path.join(fixtureRoot, 'fixture.json')));
    report.database_fixture = { migration_sources_sha256: state.migration_sources_sha256,
      vision_roles_sha256: state.vision_roles_sha256,
      public_bank_sha256: state.public_bank_sha256, synthetic_corpus_digest: state.synthetic_corpus_digest,
      production_access: false, distinct_databases: 2, distinct_roles: Object.keys(state.roles).length };
    services = await startServices(fixtureRoot);
    const db = (database, username, schema) => ({ transport: { kind: 'tcp', port: 55432 }, database, username,
      password_file: path.join(fixtureRoot, 'database-password'), schema, maximum_connections: 2 });
    configuration = { schema_version: 1, public_hosts: [...allowedHosts],
      required_capabilities: ['static-assets', 'mateval-collection', 'mateval-administration', 'vision-http', 'audition-http', 'log-presentation'],
      assets: artifacts.map(item => ({ host: item.host, directory: item.directory, payload_prefix: item.prefix, manifest_sha256: item.hash, mount: item.mount })),
      mateval: { database: db(state.databases.mateval, state.roles.collecte, 'mateval'),
        administration_database: db(state.databases.mateval, state.roles.science, 'mateval'), activation_sha256_file: path.join(fixtureRoot, 'activation-sha256') },
      identity: { endpoint: `127.0.0.1:${services.ports.identity}`, protocol: 'mrj-auth-v1' },
      vision: { database: db(state.databases.vision, state.roles.vision, 'public'),
        public_mcp_url: 'https://vision.mrj.am/mcp', public_web_url: 'https://vision.mrj.am',
        embeddings: { endpoint: `127.0.0.1:${services.ports.embedding}`, model: 'synthetic-browser-3', dimensions: 3 }, deletion_journal: null, administration_database: null },
      audition: db(state.databases.vision, state.roles.audition, 'audition'),
      log: { endpoint: `127.0.0.1:${services.ports.log}`, ca_file: path.join(fixtureRoot, 'ca.pem'),
        ca_sha256: sha(file(path.join(fixtureRoot, 'ca.pem'))), aliases_database_file: path.join(fixtureRoot, 'aliases.sqlite') } };
    fs.writeFileSync(path.join(fixtureRoot, 'runtime.json'), JSON.stringify(configuration), { mode: 0o600, flag: 'wx' });
  });
  const configPath = path.join(fixtureRoot, 'runtime.json');
  await check('CLI-check-config-accepts-closed-reference-config-and-rejects-extra-field', async () => {
    const accepted = invoke(['check-config', configPath]);
    assert.equal(accepted.status, 0); assert.deepEqual(JSON.parse(accepted.stdout), { code: 'CONFIGURATION_VALID' }); assert.equal(accepted.stderr, '');
    const refusedPath = path.join(fixtureRoot, 'invalid-runtime.json');
    fs.writeFileSync(refusedPath, JSON.stringify({ ...configuration, synthetic_unknown_field: 'not-a-secret' }), { mode: 0o600, flag: 'wx' });
    const refused = invoke(['check-config', refusedPath]);
    assert.equal(refused.status, 2); assert.deepEqual(JSON.parse(refused.stderr), { code: 'INVALID_RUNTIME_CONFIGURATION' }); assert.equal(refused.stdout, '');
  });
  await check('real-CLI-starts-without-migration-and-all-configured-capabilities-ready', async () => {
    const reservation = net.createServer(); reservation.listen(0, '127.0.0.1'); await once(reservation, 'listening');
    port = reservation.address().port; await new Promise(resolve => reservation.close(resolve));
    const [program, argumentsList] = command(['serve', '--config', configPath]);
    server = spawn(program, argumentsList, { env: { ...environment, MRJAM_LISTEN_ADDR: `127.0.0.1:${port}`, MRJAM_INSTANCE: 'blue', MRJAM_WORKERS_ENABLED: 'false' }, stdio: ['ignore', 'pipe', 'pipe'] });
    serverExit = new Promise(resolve => { server.once('exit', (code, signal) => resolve({ code, signal })); server.once('error', () => resolve({ code: null, signal: 'SPAWN_FAILED' })); });
    report.server_stdout_bytes = 0; report.server_stderr_bytes = 0; report.server_error_codes = [];
    server.stdout.on('data', chunk => { report.server_stdout_bytes += chunk.length; });
    server.stderr.on('data', chunk => {
      report.server_stderr_bytes += chunk.length;
      for (const line of chunk.toString().split('\n')) {
        try { const code = JSON.parse(line).code; if (typeof code === 'string' && /^[A-Z_]+$/.test(code)) report.server_error_codes.push(code); } catch { /* No content diagnostics stored. */ }
      }
    });
    let ready;
    for (let attempt = 0; attempt < 60; attempt++) {
      if (server.exitCode !== null) throw new Error('SERVER_EXITED');
      try { ready = await localRequest('principiipetit.io', 'GET', '/readyz'); if (ready.status === 200) break; } catch { /* Poll loopback only. */ }
      await delay(250);
    }
    assert.equal(ready?.status, 200);
    const value = JSON.parse(ready.body);
    assert.equal(value.scope, 'configured-capabilities-only');
    assert.deepEqual(value.capabilities, configuration.required_capabilities);
    report.configured_capabilities = value.capabilities;
    assert.equal((await localRequest('principiipetit.io', 'GET', '/healthz')).status, 200);
    assert.equal((await localRequest('unexpected.invalid', 'GET', '/')).status, 421);
  });
  await check('all-233-static-payloads-served-byte-identically-with-correct-MIME', async () => {
    let total = 0;
    for (const item of artifacts) {
      for (const [relative, expected] of Object.entries(item.manifest.payload_sha256)) {
        const response = await localRequest(item.host, 'GET', item.mount + relative.slice(item.prefix.length));
        assert.equal(response.status, 200); assert.equal(sha(response.body), expected);
        assert.equal(response.headers['content-type'], types[path.extname(relative).slice(1)]);
        assert.equal(response.headers['x-content-type-options'], 'nosniff'); total++;
      }
    }
    assert.equal(total, 233); report.static_payloads_served = total;
  });
  browser = await chromium.launch({ headless: true });
  report.chromium_version = browser.version(); assert.equal(browser.version(), '156.0.8078.4');
  const collectionContext = await context(), collection = await collectionContext.newPage();
  const storageKey = 'matheval-participation-v1';
  const localRecord = () => collection.evaluate(key => JSON.parse(localStorage.getItem(key)), storageKey);
  const saved = async () => expect.poll(async () => { const value = await localRecord(); return Boolean(value?.revision > 0 && value.revision === value.savedRevision); }, { timeout: 15000 }).toBe(true);
  await check('Mateval-real-public-questionnaire-creates-and-persists-invented-participation', async () => {
    await collection.goto('https://principiipetit.io/matheval/');
    await collection.getByRole('checkbox', { name: '3e', exact: true }).click();
    const created = collection.waitForResponse(value => value.url().endsWith('/api/sessions') && value.request().method() === 'POST');
    await collection.getByRole('button', { name: 'Commencer', exact: true }).click();
    const response = await created; assert.equal(response.status(), 201);
    const value = await response.json(); assert.equal(value.secret, undefined); assert.equal(value.token_hash, undefined); assert.ok(value.questions.length > 0);
    await collection.getByRole('button', { name: 'Passer l’aide', exact: true }).click();
    await expect(collection.locator('#reading-card')).toBeVisible();
    await expect(collection.locator('#grade')).toHaveAttribute('aria-valuetext', 'Non noté');
    await collection.getByRole('slider', { name: 'Note sur 3' }).press('Home'); await saved();
    const record = await localRecord(); const id = await collection.locator('#reading-card').getAttribute('production-id');
    const persisted = await localRequest('principiipetit.io', 'GET', `/matheval/api/sessions/${record.id}`, { 'x-session-token': record.secret });
    assert.equal(persisted.status, 200); const stored = JSON.parse(persisted.body);
    assert.equal(stored.snapshot.answers[id].note, 0); assert.equal(stored.snapshot.answers[id].initialNote, null); assert.deepEqual(stored.snapshot, record.snapshot);
    await collection.reload(); await expect(collection.locator('#grade')).toHaveValue('0'); assert.equal((await localRecord()).id, record.id);
    assert.equal((await localRequest('principiipetit.io', 'GET', `/matheval/api/sessions/${record.id}`, { 'x-session-token': 'f'.repeat(64) })).status, 401);
    await fonts(collection, 'mateval');
  });
  const adminContext = await context(), admin = await adminContext.newPage();
  await check('Mateval-admin-setup-scientific-statistics-CSV-and-session-revocation', async () => {
    assert.equal((await localRequest('principiipetit.io', 'GET', '/matheval/api/admin/me')).status, 401);
    await admin.goto(`https://principiipetit.io/matheval/admin/index.html#activation=${'c'.repeat(64)}`);
    await expect(admin.getByRole('button', { name: 'Créer mon accès', exact: true })).toBeVisible();
    assert.equal(new URL(admin.url()).hash, '');
    await admin.getByLabel('Identifiant', { exact: true }).fill('synthetic_admin');
    await admin.getByLabel('Mot de passe', { exact: true }).fill(password);
    await admin.getByLabel('Confirmer le mot de passe', { exact: true }).fill(password);
    const setup = admin.waitForResponse(value => value.url().endsWith('/api/admin/setup'));
    await admin.getByRole('button', { name: 'Créer mon accès', exact: true }).click();
    const response = await setup; assert.equal(response.status(), 200); assert.deepEqual(await response.json(), { username: 'synthetic_admin' });
    const cookie = (await adminContext.cookies()).find(item => item.path === '/matheval/api/admin');
    assert.ok(cookie?.secure && cookie.httpOnly && cookie.sameSite === 'Strict');
    await expect(admin.getByRole('button', { name: 'Participations', exact: true })).toBeVisible();
    await admin.getByRole('button', { name: 'Participations', exact: true }).click();
    const csv = await admin.evaluate(async () => { const r = await fetch('/matheval/api/admin/exports/responses.csv'); const b = await r.arrayBuffer(); return { status: r.status, type: r.headers.get('content-type'), bytes: [...new Uint8Array(b)] }; });
    assert.equal(csv.status, 200); assert.ok(csv.type.startsWith('text/csv')); assert.deepEqual(csv.bytes.slice(0, 3), [239, 187, 191]);
    // This journey saves exactly one answer. The historical CSV contract is
    // a header followed by one CRLF-delimited row, with no trailing empty row.
    const rows = Buffer.from(csv.bytes).toString().slice(1).split('\r\n');
    assert.equal(rows.length, 2);
    assert.equal(rows[0], ['participation', 'version', 'debut', 'validation', 'niveaux', 'question', 'redaction', 'note_initiale', 'note', 'lisibilite', 'precision', 'validite', 'axes_evalues'].map(value => `"${value}"`).join(';'));
    const cells = rows[1].match(/"(?:[^"]|"")*"(?=;|$)/g);
    assert.ok(cells && cells.length === 13 && cells.join(';') === rows[1]);
    assert.equal(cells[0], `"${(await localRecord()).id}"`);
    assert.equal(cells[7], '""'); assert.equal(cells[8], '"0"');
    const blocked = await localRequest('principiipetit.io', 'POST', '/matheval/api/admin/setup', { origin: 'https://principiipetit.io', 'x-matheval-request': '1', 'content-type': 'application/json' }, JSON.stringify({ username: 'another_invented_account', password, token: 'c'.repeat(64) }));
    assert.ok([403, 409].includes(blocked.status));
    await admin.getByRole('button', { name: 'Déconnexion', exact: true }).click();
    await expect(admin.getByRole('button', { name: 'Se connecter', exact: true })).toBeVisible();
    assert.equal((await localRequest('principiipetit.io', 'GET', '/matheval/api/admin/me', { cookie: `${cookie.name}=${cookie.value}` })).status, 401);
  });
  const visionContext = await context(), vision = await visionContext.newPage();
  await check('Vision-real-Elm-authenticated-search-create-and-reload-via-Rust', async () => {
    await vision.goto('https://vision.mrj.am/');
    await vision.getByRole('link', { name: 'J’ai déjà un compte', exact: true }).click();
    await expect(vision.getByRole('button', { name: 'Se connecter', exact: true })).toBeVisible();
    await vision.getByLabel('Identifiant', { exact: true }).fill(owner);
    await vision.getByLabel('Mot de passe', { exact: true }).fill(password);
    await vision.getByRole('button', { name: 'Se connecter', exact: true }).click();
    await expect(vision.getByRole('button', { name: 'Nouvelle fiche', exact: true })).toBeVisible();
    await vision.getByRole('button', { name: 'Nouvelle fiche', exact: true }).click();
    await vision.getByLabel('Contenu de référence', { exact: true }).fill('Contenu entièrement inventé pour vérifier le transport et la persistance.');
    await vision.getByLabel('Titre', { exact: true }).fill('Fiche de qualification inventée');
    const savedResponse = vision.waitForResponse(value => value.url().endsWith('/api/web/enregistrer_fiche'));
    await vision.getByRole('button', { name: 'Enregistrer', exact: true }).click();
    assert.equal((await savedResponse).status(), 200);
    await vision.reload();
    await expect(vision.getByText('Fiche de qualification inventée', { exact: true }).first()).toBeVisible();
    await fonts(vision, 'vision');
    const denied = await localRequest('vision.mrj.am', 'POST', '/api/web/rechercher', { 'content-type': 'application/json', cookie: browserCookie, origin: 'https://vision.mrj.am' }, '{}');
    assert.equal(denied.status, 403);
  });
  const auditionContext = await context(), audition = await auditionContext.newPage();
  await check('Audition-real-Elm-context-and-group-creation-via-Rust', async () => {
    await audition.goto('https://audition.mrj.am/');
    await expect(audition.getByRole('link', { name: 'Se connecter avec Log', exact: true })).toBeVisible();
    await auditionContext.addCookies([{ name: 'mrjam-synthetic-browser', value: 'owner', domain: 'audition.mrj.am', path: '/', secure: true, httpOnly: true, sameSite: 'Strict' }]);
    await audition.reload();
    await expect(audition.getByText(`Compte métier : ${owner}`, { exact: true })).toBeVisible();
    await expect(audition.getByRole('button', { name: 'Préparer', exact: true })).toBeVisible();
    await audition.getByRole('button', { name: 'Administration', exact: true }).click();
    await audition.getByLabel('Nom du nouveau groupe', { exact: true }).fill('Second groupe entièrement inventé');
    const result = audition.waitForResponse(value => value.url().endsWith('/api/audition/creer_groupe'));
    await audition.getByRole('button', { name: 'Créer le groupe', exact: true }).click();
    assert.equal((await result).status(), 403);
    // A SQL administrator without the separate recent-MFA verification cannot
    // create a group. The fixture grants it only after this negative journey.
    await auditionContext.addCookies([{ name: 'mrjam-synthetic-mfa', value: 'recent', domain: 'audition.mrj.am', path: '/', secure: true, httpOnly: true, sameSite: 'Strict' }]);
    const approved = audition.waitForResponse(value => value.url().endsWith('/api/audition/creer_groupe'));
    await audition.getByRole('button', { name: 'Créer le groupe', exact: true }).click();
    assert.equal((await approved).status(), 200);
    await audition.reload();
    await expect(audition.getByRole('combobox', { name: 'Groupe', exact: true }).locator('option', { hasText: 'Second groupe entièrement inventé' })).toHaveCount(1);
    await fonts(audition, 'audition');
  });
  const logContext = await context(), log = await logContext.newPage();
  await check('Log-real-Elm-native-TLS-auth-cookie-token-redaction-and-logout', async () => {
    await log.goto('https://log.mrj.am/');
    await log.getByLabel('Adresse électronique ou identifiant', { exact: true }).fill('synthetic@example.invalid');
    await log.getByRole('button', { name: 'Continuer', exact: true }).click();
    await log.getByLabel('Phrase de passe', { exact: true }).fill(password);
    const success = log.waitForResponse(async value => value.url().endsWith('/presentation/api') && (await value.json().catch(() => ({}))).state?.success === '');
    await log.getByRole('button', { name: 'Se connecter', exact: true }).click();
    assert.equal((await success).status(), 200);
    await expect(log.getByText('Compte Log entièrement inventé', { exact: true })).toBeVisible();
    const cookie = (await logContext.cookies()).find(item => item.name === 'bearer');
    assert.ok(cookie?.secure && cookie.httpOnly && cookie.sameSite === 'Strict' && cookie.path === '/');
    assert.equal(await log.evaluate(() => document.cookie.includes('bearer=')), false);
    await fonts(log, 'log');
    await log.getByRole('button', { name: 'Me déconnecter de Log', exact: true }).click();
    await expect(log.getByRole('button', { name: 'Continuer', exact: true })).toBeVisible();
    assert.equal((await logContext.cookies()).some(item => item.name === 'bearer'), false);
  });
  await check('network-route-refusal-and-no-browser-or-resource-errors', async () => {
    const refused = await log.evaluate(async () => { try { await fetch('https://example.invalid/synthetic-forbidden'); return false; } catch { return true; } });
    assert.equal(refused, true); assert.equal(report.blocked_external_requests, 1);
    assert.equal(report.blocked_websockets, 0); assert.equal(report.route_errors, 0); assert.equal(report.page_errors, 0);
    for (const [key, count] of Object.entries(report.browser_http_results)) if (key.includes('rust-assets:')) assert.ok(key.endsWith(':200'), `${key}:${count}`);
    assert.equal(sha(file(binary, 128 * 1024 * 1024)), binaryDigest);
  });
  report.status = 'passed';
} catch (error) {
  report.failure_stage = stage;
  report.failure_kind = error?.name === 'TimeoutError' ? 'TIMEOUT' : error?.name === 'AssertionError' ? 'ASSERTION' : 'OTHER';
  // Closed diagnostics for invented browser fixtures; never retain field
  // values, HTML, cookies, response bodies or arbitrary exception messages.
  report.form_diagnostics = [];
  for (const context of contexts) for (const page of context.pages()) {
    try {
      report.form_diagnostics.push(await page.evaluate(() => ({
        invalid_inputs: [...document.querySelectorAll('input')].filter(input => !input.validity.valid).length,
        disabled_buttons: [...document.querySelectorAll('button')].filter(button => button.disabled).length,
        password_mismatch: document.body.textContent.includes('Les mots de passe ne correspondent pas.'),
        password_length_refused: document.body.textContent.includes('Choisissez un mot de passe de 14 à 256 caractères.'),
        username_refused: document.body.textContent.includes('Choisissez un identifiant'),
      })));
    } catch { report.form_diagnostics.push({ unavailable: true }); }
  }
  // A closed source location helps fix the harness without retaining a page,
  // response, cookie, credential or the assertion's possibly private values.
  const location = String(error?.stack || '').match(/run\.mjs:(\d+):(\d+)/);
  if (location) report.failure_source = { file: 'run.mjs', line: Number(location[1]), column: Number(location[2]) };
  report.status = 'failed';
} finally {
  if (browser) { try { await browser.close(); } catch { report.browser_cleanup_failed = true; report.status = 'failed'; } }
  if (server && server.exitCode === null) {
    // Only the synthetic child process's memory counters, never process data.
    try {
      const status = fs.readFileSync(`/proc/${server.pid}/status`, 'utf8');
      const peak = status.match(/^VmHWM:\s+(\d+) kB$/m);
      if (peak) report.server_peak_rss_kib = Number(peak[1]);
    } catch { report.server_memory_measurement_unavailable = true; }
    server.kill('SIGTERM');
    const result = await Promise.race([serverExit, delay(10000).then(() => null)]);
    if (!result) { server.kill('SIGKILL'); await serverExit; report.server_cleanup_failed = true; report.status = 'failed'; }
    else { report.server_exit = result; if (result.code !== 0) report.status = 'failed'; }
  }
  if (services) { report.synthetic_protocol_calls = services.calls; try { await services.close(); } catch { report.protocol_cleanup_failed = true; report.status = 'failed'; } }
  if (fixtureCreated && fs.existsSync(path.join(fixtureRoot, 'fixture.json'))) {
    try { report.database_cleanup = fixture('cleanup'); } catch { report.database_cleanup_failed = true; report.status = 'failed'; }
  }
  if (fixtureRoot && !report.database_cleanup_failed) { fs.rmSync(fixtureRoot, { recursive: true }); report.private_fixture_files_removed = true; }
  report.completed_at_utc = new Date().toISOString();
  if (evidence) fs.writeFileSync(evidence, JSON.stringify(report, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
  console.log(JSON.stringify({ code: report.status === 'passed' ? 'SYNTHETIC_RUNTIME_BROWSER_PASSED' : 'SYNTHETIC_RUNTIME_BROWSER_FAILED', checks: report.checks.length, stage: report.failure_stage || null }));
  if (report.status !== 'passed') process.exitCode = 1;
}
