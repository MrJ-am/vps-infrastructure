import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { checkedPins } from './artifact_pins.mjs';

const sha = raw => createHash('sha256').update(raw).digest('hex');
const fixture = () => ({ schema_version: 1, kind: 'qualified-flat-frontends-v1',
  proposal_sha256: '1'.repeat(64), rules_revision: '2'.repeat(40), artifact_import_lock_sha256: '3'.repeat(64),
  server_sha256: '4'.repeat(64), frontends: Object.fromEntries(['audition', 'log', 'mateval', 'vision'].map(name => [name, '5'.repeat(64)])), deployment_authorized: false });
const encode = value => Buffer.from(JSON.stringify(value, null, 2) + '\n');

test('explicit independently supplied byte pin is required', () => {
  const raw = encode(fixture());
  assert.deepEqual(checkedPins(raw, sha(raw)), fixture());
  assert.throws(() => checkedPins(raw, '0'.repeat(64)));
  assert.throws(() => checkedPins(Buffer.from(raw).fill(32, 10, 11), sha(raw)));
});
test('missing or additional frontend cannot reduce or enlarge scope', () => {
  for (const name of ['audition', 'log', 'mateval', 'vision']) {
    const value = fixture(); delete value.frontends[name];
    const raw = encode(value); assert.throws(() => checkedPins(raw, sha(raw)));
  }
  const value = fixture(); value.frontends.other = '6'.repeat(64);
  const raw = encode(value); assert.throws(() => checkedPins(raw, sha(raw)));
});
test('invalid content bindings and claimed deployment approval are refused', () => {
  for (const [field, invalid] of [['server_sha256', 'not-a-hash'], ['rules_revision', 'main'],
    ['deployment_authorized', true], ['kind', 'anything'], ['proposal_sha256', null]]) {
    const value = fixture(); value[field] = invalid;
    const raw = encode(value); assert.throws(() => checkedPins(raw, sha(raw)));
  }
});
test('duplicate JSON keys and extra settings are refused even when byte-pinned', () => {
  const raw = Buffer.from(encode(fixture()).toString().replace('"schema_version": 1,', '"schema_version": 1,\n  "schema_version": 1,'));
  assert.throws(() => checkedPins(raw, sha(raw)));
  const additional = encode({ ...fixture(), skip_tests: true });
  assert.throws(() => checkedPins(additional, sha(additional)));
});
