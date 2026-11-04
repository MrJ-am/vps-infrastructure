// Build a disposable questionnaire view from the pinned sources, never in a gitlink.
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const [frontend, style, destination, tools, rules] = process.argv.slice(2).map(p => path.resolve(p));
if (!frontend || !style || !destination || !tools || !rules || process.argv.length !== 7) {
  throw new Error('usage: prepare.mjs FRONTEND PINNED_STYLE NEW_DESTINATION ENVIRONMENT CANONICAL_REVIEW');
}
if (fs.existsSync(destination)) throw new Error('NEW_DESTINATION_REQUIRED');
const digest = filename => createHash('sha256').update(fs.readFileSync(filename)).digest('hex');
const publicBank = path.join(frontend, 'site/data/bank.json');
const publicBankDigest = digest(publicBank);
if (publicBankDigest !== JSON.parse(fs.readFileSync(path.join(frontend, 'artifacts.lock.json'))).sha256) throw new Error('PUBLIC_ARTIFACT_LOCK_MISMATCH');
fs.mkdirSync(destination, { recursive: true });
const source = path.join(destination, 'frontend');
fs.cpSync(frontend, source, { recursive: true, filter: p => !['node_modules', 'elm-stuff', '.git', '.style-mrjam'].includes(path.basename(p)) });
const require = createRequire(import.meta.url);
process.env.STYLE_MRJAM_SOURCE = style;
const { preparerAtelier, installerIdentite } = require(path.join(source, 'scripts/style-mrjam.cjs'));
const project = path.join(destination, 'project');
fs.mkdirSync(project);
const common = preparerAtelier(project);
const compiler = path.join(tools, 'node_modules/.bin/elm');
if (execFileSync(compiler, ['--version'], { encoding: 'utf8' }).trim() !== '0.19.1') throw new Error('ELM_VERSION_MISMATCH');
if (execFileSync(path.join(tools, 'node_modules/.bin/elm-review'), ['--version'], { encoding: 'utf8' }).trim() !== '2.13.5') throw new Error('ELM_REVIEW_VERSION_MISMATCH');
const environment = Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|HOME|TMPDIR|LANG|LC_ALL|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|NO_PROXY|http_proxy|https_proxy|all_proxy|no_proxy|NODE_EXTRA_CA_CERTS|SSL_CERT_FILE|SSL_CERT_DIR|REQUESTS_CA_BUNDLE|CODEX_PROXY_CERT)$/.test(key)));
environment.ELM_HOME = path.join(destination, 'elm-home');
environment.NODE_USE_ENV_PROXY = '1';
const config = path.join(destination, 'review');
fs.mkdirSync(config);
for (const name of ['elm.json', 'ressources.json', 'src/ReviewConfig.elm', 'src/MrJam/Presentation.elm', 'tests/PresentationTest.elm']) {
  const target = path.join(config, name);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(path.join(rules, name), target);
}
execFileSync(path.join(tools, 'node_modules/.bin/elm-review'), ['prepare-offline', '--config', config, '--compiler', compiler], { cwd: project, env: environment, stdio: 'inherit' });
const site = path.join(source, 'site');
execFileSync(compiler, ['make', 'src/Survey.elm', '--optimize', `--output=${path.join(site, 'survey.js')}`], { cwd: project, env: environment, stdio: 'inherit' });
installerIdentite(common, path.join(site, 'assets/mrjam'));
const fixture = fileURLToPath(new URL('./bank.json', import.meta.url));
fs.copyFileSync(fixture, path.join(site, 'data/bank.json'));
if (digest(publicBank) !== publicBankDigest) throw new Error('SOURCE_ARTIFACT_CHANGED');
const proof = {
  schema_version: 1, scope: 'Synthetic questionnaire browser fixture only; not a distributable application build',
  frontend, style_revision: JSON.parse(fs.readFileSync(path.join(frontend, 'style-mrjam.json'))).revision,
  elm_version: '0.19.1', elm_review_cli: '2.13.5', compiled_entrypoints: ['Survey.elm'],
  bank_fixture_sha256: digest(fixture), survey_js_sha256: digest(path.join(site, 'survey.js')),
  original_public_bank_sha256: publicBankDigest, original_public_bank_unchanged: true,
  style_lock_sha256: digest(path.join(frontend, 'style-mrjam.json')),
  elm_manifest_sha256: digest(path.join(frontend, 'elm.json')),
  prepare_script_sha256: digest(fileURLToPath(import.meta.url)),
  deployment_authorized: false
};
fs.writeFileSync(path.join(destination, 'build-proof.json'), JSON.stringify(proof, null, 2) + '\n');
console.log(JSON.stringify({ status: 'built', site }));
