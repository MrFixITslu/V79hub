import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { validatePosTeamAcknowledgement as validate } from '../server/pos-team-acknowledgement.mjs';

const identity = { organizationId: 'synthetic-org', userId: 'synthetic-user' };
const reply = (roleKey, extra = {}) => ({
  ...identity, provisioned: true, roleKey, locationIds: ['synthetic-location'], ...extra,
});
for (const [hubRole, roleKey] of [
  ['manager', 'MANAGER'], ['staff', 'CASHIER'], ['staff', 'TECHNICIAN'], ['viewer', 'AUDITOR'],
]) {
  test('accepts ' + hubRole + ' -> ' + roleKey, () => {
    assert.deepEqual(validate(reply(roleKey), { ...identity, hubRole }),
      { roleKey, locationId: 'synthetic-location' });
  });
}
for (const [hubRole, roleKey] of [
  ['staff', 'MANAGER'], ['staff', 'AUDITOR'], ['viewer', 'TECHNICIAN'],
  ['manager', 'TECHNICIAN'], ['viewer', 'CASHIER'], ['owner', 'MANAGER'],
  ['staff', 'OWNER'], ['unknown', 'CASHIER'],
]) {
  test('rejects ' + hubRole + ' -> ' + roleKey, () => {
    assert.equal(validate(reply(roleKey), { ...identity, hubRole }), null);
  });
}
for (const [label, extra] of Object.entries({
  crossTenant: { organizationId: 'other-org' },
  wrongUser: { userId: 'other-user' },
  notProvisioned: { provisioned: false },
  noLocation: { locationIds: [] },
  twoLocations: { locationIds: ['a', 'b'] },
  badLocation: { locationIds: [42] },
  blankLocation: { locationIds: ['   '] },
})) {
  test('rejects ' + label, () => {
    assert.equal(validate(reply('TECHNICIAN', extra), { ...identity, hubRole: 'staff' }), null);
  });
}
test('rejects malformed response or missing identity', () => {
  assert.equal(validate(null, { ...identity, hubRole: 'staff' }), null);
  assert.equal(validate(reply('CASHIER'), { hubRole: 'staff' }), null);
});
test('server delegates to contract and returns acknowledged role', () => {
  const source = readFileSync(new URL('../server.ts', import.meta.url), 'utf8');
  const fn = source.slice(source.indexOf('async function provisionPosTeamMember('),
                          source.indexOf('async function deprovisionPosTeamMember('));
  assert.match(fn, /validatePosTeamAcknowledgement\(payload,/);
  assert.match(fn, /roleKey: acknowledged\.roleKey, locationId: acknowledged\.locationId/);
  assert.match(fn, /signPlatformRequest/);
  assert.match(fn, /status: 502/);
});
