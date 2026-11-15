import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../server.ts',import.meta.url),'utf8');
test('Marketing rename is explicitly disabled unless opted in before global auth',()=>{
  const flag=source.indexOf('if (process.env.V79_ORG_NAME_RENAME_ENABLED === "1") {');
  const route=source.indexOf('app.post("/api/platform/organization/rename"');
  const globalAuth=source.indexOf('app.use("/api", requireAuth)');
  assert.ok(flag>0 && route>flag && globalAuth>route, 'Signed route must be behind opt-in and before global browser auth');
  const scope=source.slice(flag,globalAuth);
  assert.match(scope,/storePersistence.mode !== "postgres"/);
  assert.match(scope,/V79_MARKETING_LAUNCH_SECRET/);
  assert.match(scope,/createMarketingRenameHandler/);
});
test('Delivery lifecycle is controlled by default-off flag',()=>{
  const env=readFileSync(new URL('../.env.example',import.meta.url),'utf8');
  assert.match(env,/^V79_ORG_NAME_RENAME_ENABLED=0$/m);
  assert.match(env,/^V79_ORG_NAME_DELIVERY_ENABLED=0$/m);
  const worker=readFileSync(new URL('../server/organization-name-worker-lifecycle.mjs',import.meta.url),'utf8');
  assert.match(worker,/if \(enabled === "0"\)/);
});
