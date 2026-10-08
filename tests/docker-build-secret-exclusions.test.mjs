import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const ignored=new Set(readFileSync(resolve(root,'.dockerignore'),'utf8')
  .split(/\r?\n/).map(s=>s.trim()).filter(Boolean));
test('Hub Docker build context excludes runtime env, private backups and key files',()=>{
  for(const required of ['.env','.env.*','**/.env','**/.env.*',
    'backups','**/backups','*.pem','*.key']){
    assert.ok(ignored.has(required), 'Missing Docker context exclusion: '+required);
  }
  assert.match(readFileSync(resolve(root,'Dockerfile'),'utf8'),/COPY \. \./);
});
