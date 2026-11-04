// Reviewed byte pins for a NEW full-pipeline output. Historical pins stay fixed.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

const names = ['audition', 'log', 'mateval', 'vision'];
const hex = /^[0-9a-f]{64}$/;
const fields = ['schema_version', 'kind', 'proposal_sha256', 'rules_revision',
  'artifact_import_lock_sha256', 'server_sha256', 'frontends', 'deployment_authorized'];

export function checkedPins(raw, expectedHash) {
  assert.ok(Buffer.isBuffer(raw) && raw.length <= 8192 && hex.test(expectedHash));
  assert.equal(createHash('sha256').update(raw).digest('hex'), expectedHash);
  const value = JSON.parse(raw);
  // Canonical JSON also refuses duplicate keys and ambiguous encodings.
  assert.equal(JSON.stringify(value, null, 2) + '\n', raw.toString('utf8'));
  assert.deepEqual(Object.keys(value).sort(), [...fields].sort());
  assert.equal(value.schema_version, 1);
  assert.equal(value.kind, 'qualified-flat-frontends-v1');
  assert.equal(value.deployment_authorized, false);
  for (const key of ['proposal_sha256', 'artifact_import_lock_sha256', 'server_sha256']) assert.ok(hex.test(value[key]));
  assert.ok(/^[0-9a-f]{40}$/.test(value.rules_revision));
  assert.deepEqual(Object.keys(value.frontends).sort(), names);
  for (const hash of Object.values(value.frontends)) assert.ok(typeof hash === 'string' && hex.test(hash));
  return value;
}
