import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const code = readFileSync(new URL("../server.ts", import.meta.url), "utf8");
const persistence = readFileSync(new URL("../server/runtime-store.mjs", import.meta.url), "utf8");

test("all four external product activations inherit the source store revision, never an old request revision", () => {
  const begin = code.indexOf("async function commitProvisionedTenantMapping(");
  const start = code.indexOf("async function provisionCustomerProduct(");
  const end = code.indexOf('app.get("/api/admin/customers"', start);
  assert.ok(begin >= 0 && begin < start && end > start);
  const helper = code.slice(begin, start);
  const handler = code.slice(start, end);
  assert.match(helper, /snapshotRevision\.get\(sourceStore\)/);
  assert.match(helper, /snapshotRevision\.set\(nextStore, originatingRevision\)/);
  assert.match(helper, /originatingRevision === undefined/);
  assert.match(helper, /throw new Error\("Cannot persist tenant provisioning without the source-store revision\."/);
  assert.match(helper, /await commitStore\(nextStore\)/);
  for (const product of ["Pos", "Ffpro", "Tiquet", "Marketing"]) {
    assert.match(handler, new RegExp("await commitProvisionedTenantMapping\\(activate" + product + "TenantMapping\\(store,"));
  }
  assert.doesNotMatch(handler, /await commitStore\(activate(?:Pos|Ffpro|Tiquet|Marketing)TenantMapping/);
  assert.match(code, /snapshotRevision\.set\(nextStore, storePersistence\.revision\(\)\)/);
});

test("source revision remains a mandatory PostgreSQL compare-and-swap precondition", () => {
  assert.match(code, /snapshotRevision\.get\(nextStore\) \?\? hubRequestRevision\.getStore\(\)\?\.revision/);
  assert.match(code, /storePersistence\.save\(nextStore, \{ expectedRevision \}\)/);
  assert.match(persistence, /if \(expectedRevision !== revision\)/);
  assert.match(persistence, /repository\.replace\(expectedRevision, persisted\)/);
});
