import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
// Read-only source check. This is not deployment approval and never runs Docker/SSH.
const base='796cea94e9b56d8fde023688a19a78adb40d0c2a';
const allowed=[
  'src/App.tsx','src/components/HubOverview.tsx','src/components/Sidebar.tsx','src/workspace.css',
  'scripts/vision79-workspace-browser.mjs','scripts/vision79-workspace-preflight.mjs',
  'tests/vision79-workspace-boundary.test.mjs','docs/design/vision79-workspace-v2-review.md',
];
const changed=execFileSync('git',['diff',base,'--name-only'],{encoding:'utf8'}).trim().split('\n').filter(Boolean);
const untracked=execFileSync('git',['ls-files','--others','--exclude-standard'],{encoding:'utf8'}).trim().split('\n').filter(Boolean);
for(const p of [...changed,...untracked]) assert.ok(allowed.includes(p),'Unexpected release scope: '+p);
const hashes=Object.fromEntries(allowed.map(p=>[p,createHash('sha256').update(readFileSync(p)).digest('hex')]));
console.log(JSON.stringify({base,scope:'presentation-only candidate',changed:[...new Set([...changed,...untracked])],hashes,
  productionActions:'NONE',ownerVisualApproval:'PENDING',releaseGate:'HOLD',
  pending:['new release source acceptance','current production image/config identity','fresh rollback checkpoint','immutable image build and isolated boot','real private-session MFA and Tiquet SSO','guarded Hub-only transaction and rollback rehearsal']},null,2));
