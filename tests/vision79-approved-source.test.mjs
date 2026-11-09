import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const approval=JSON.parse(readFileSync('docs/release/vision79-v3-approved-source.json','utf8'));
const rootFiles=new Set(['server.ts','package.json','package-lock.json','Dockerfile','.dockerignore','tsconfig.json','vite.config.ts','index.html']);
const runtime=p=>/^(src|shared|lib|agent-service|public)\//.test(p)||rootFiles.has(p);
test('approved v3 runtime bytes and tracked runtime scope exactly match the reviewed commit',()=>{
 assert.equal(approval.approved_visual_source,'114841271d4f8b9c4b63df6aedfd55bde2e82f40');
 const current=execFileSync('git',['ls-files'],{encoding:'utf8'}).trim().split('\n').filter(runtime).sort();
 assert.deepEqual(current,Object.keys(approval.runtime_files_sha256).sort());
 for(const [path,pin] of Object.entries(approval.runtime_files_sha256))assert.equal(createHash('sha256').update(readFileSync(path)).digest('hex'),pin,path);
 assert.equal(approval.production_deployment,false,'Visual approval is not evidence of deployment');
});
