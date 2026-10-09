import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const server=fs.readFileSync(path.join(root,'server.ts'),'utf8');
test('Hub declares a scoped HSTS policy and minimal CSP without widening to all subdomains',()=>{
  assert.match(server,/setHeader\("Strict-Transport-Security", "max-age=604800"\)/);
  assert.doesNotMatch(server,/setHeader\("Strict-Transport-Security", [^\n]*includeSubDomains/);
  assert.match(server,/setHeader\("Content-Security-Policy", "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"\)/);
});
