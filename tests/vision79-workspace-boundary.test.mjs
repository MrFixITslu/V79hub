import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parse} from '@babel/parser';
const hash=s=>createHash('sha256').update(s).digest('hex');
const read=p=>readFileSync(p,'utf8');
// Candidate presentation boundary, pinned against PR #205 head 796cea94e9b56d8fde023688a19a78adb40d0c2a.
// These checks supplement, never replace, the historical R18 release gate.
const protectedFiles={
  "server.ts": "775cf18c85c5a6c22b00ad5cb14b004ff4af44f284e23dd28d94a8f6eb37bc45",
  "src/components/Login.tsx": "eecf7fc161d7ee23ea54649e59c961e31a9859658212b4d11f989567f48121cf",
  "src/components/AppSwitcher.tsx": "2c20b1ee40dea5d10c48f913ab858509d83d765bcbf459f2d7e20a78ad529250",
  "src/lib/appLaunch.ts": "d24a477d604874742914d8678ba2aa5cd6d834b67b16a412df6678dbd2097700",
  "src/lib/dashboardTruth.ts": "ac6dba1f5aa1cd5300ee13939f86b0bb0ae3ec1ea55fa19fdfabab980dabc6cc",
  "src/lib/hubNavigation.ts": "3ecef1b3bcc6a2307a08f8c05e2b98425682a88790ea521647eeef618f56bcb3",
  "package.json": "ddcd8596ac5fa0b4b3caa2ad2f7a6069f046cf8366d170498ec95b5c1e999a9e",
  "package-lock.json": "e8effe59405b0db4e5b1528bdac239fe55542332bb590b46b1c9c3120e004161",
  "Dockerfile": "20f8dd7a5125a3319919f29e572a99dd43216d2db08128d6663b78fc28dce8ff"
};
for(const [path,pin] of Object.entries(protectedFiles)) test('Workspace v2 preserves '+path,()=>assert.equal(hash(read(path)),pin));
const eventPins={
  "src/App.tsx": "0200a264de5283ba9eaa46aa7909c0702354a6a01fba8529dc43c9b56635e879",
  "src/components/Sidebar.tsx": "1fb93182b06a98afcfa85969e2208899fb431fd0bec2f7ee7cc3b5aa2c760948"
};
function events(s){const ast=parse(s,{sourceType:'module',plugins:['typescript','jsx']});const out=[];function walk(n){if(!n||typeof n!=='object')return;if(n.type==='JSXAttribute'&&/^on[A-Z]/.test(n.name.name))out.push(n.name.name+':'+s.slice(n.value.start,n.value.end).replace(/\s+/g,''));for(const v of Object.values(n)){if(Array.isArray(v))v.forEach(walk);else if(v&&typeof v==='object')walk(v);}}walk(ast);return hash(out.sort().join('\n'));}
for(const [path,pin] of Object.entries(eventPins)) test('Workspace v2 preserves every event callback in '+path,()=>assert.equal(events(read(path)),pin));
test('Dashboard fetch, availability, filtering and metric logic unchanged',()=>assert.equal(hash(read('src/components/HubOverview.tsx').split('type ProductKey')[1].split('  return (\n    <div className=')[0]),'f7339bb077daea61b00fd509a11976c4f4e55d8d7200e03215a384432dbf5b62'));
test('Sidebar authorization logic unchanged',()=>assert.equal(hash(read('src/components/Sidebar.tsx').split('export function Sidebar')[1].split('  const buttonClass')[0]),'2136e0cf92ab30497f5b2816d8f856a3b6569d50b8f0d0c3c3e75538276fec8f'));
test('App lifecycle unchanged except presentation theme preference',()=>{
 const logic=read('src/App.tsx').split('export default function App()')[1].split('  return (\n    <div className={"hub-theme-"')[0].replace(/  const \[theme, setTheme\][\s\S]*?\n  const \[toast/, '  const [toast');
 assert.equal(hash(logic),'ecb1c1f056a58792ecf8678e395de35973729dcb9b871deea09c0dc1377f904c');
});
