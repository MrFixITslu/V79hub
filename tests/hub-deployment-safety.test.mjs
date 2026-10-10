import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root=resolve(".");
const workflow=readFileSync(join(root,".github/workflows/v79-ci-cd.yml"),"utf8");
const direct=readFileSync(join(root,"scripts/deploy-server.sh"),"utf8");
const ecosystem=readFileSync(join(root,"scripts/deploy-ecosystem-release.sh"),"utf8");
const files=[
  "server/sentinel-qa-routes.mjs",
  "server/sentinel-qa-cleanup.mjs",
  "server/sentinel-write-fence.mjs",
  "server/sentinel-audit-retention.mjs",
];

function runGuard({mode="protected",omitted=[]}={}){
  const dir=mkdtempSync(join(tmpdir(),"v79-guard-test-"));
  try {
    const stage=join(dir,"release");
    const bin=join(dir,"bin");
    mkdirSync(stage,{recursive:true});
    mkdirSync(bin);
    writeFileSync(join(stage,"server.ts"),"// synthetic release fixture\n");
    for (const p of files.filter(x=>!omitted.includes(x))) {
      mkdirSync(join(stage,"server"),{recursive:true});
      writeFileSync(join(stage,p),"// synthetic file\n");
    }
    const docker=join(bin,"docker");
    writeFileSync(docker,[
      "#!/usr/bin/env bash",
      'case "$1" in',
      '  inspect) if [ "$FAKE_MODE" = "none" ]; then exit 1; fi',
      '    if [ "${3:-}" = "{{.State.Status}}" ]; then :; fi',
      '    if [ "$FAKE_MODE" = "stopped" ]; then echo exited; else echo running; fi;;',
      '  exec) if [ "$5" = "/app/server" ]; then exit 0; fi',
      '    if [ "$FAKE_MODE" = "absent" ]; then exit 1; fi',
      '    case "$5" in /app/server/sentinel-qa-routes.mjs|/app/server/sentinel-qa-cleanup.mjs|/app/server/sentinel-write-fence.mjs|/app/server/sentinel-audit-retention.mjs) exit 0;; *) exit 1;; esac;;',
      '  *) exit 100;;',
      'esac',
      '',
    ].join("\n"));
    chmodSync(docker,0o700);
    return spawnSync("bash",[join(root,"scripts/verify-sentinel-preservation.sh"),stage,"v79-hub"],{
      env:{...process.env,PATH:bin+":"+process.env.PATH,FAKE_MODE:mode},encoding:"utf8",timeout:4500
    });
  } finally {
    rmSync(dir,{recursive:true,force:true});
  }
}
test("normal main pushes validate but cannot deploy or publish images automatically",()=>{
  assert.match(workflow,/on:\n\s*pull_request:/);
  assert.match(workflow,/push:\n\s*branches: \[main\]/);
  const bundle=workflow.match(/- name: Create delivery bundle[\s\S]*?- name: Upload delivery bundle/)?.[0]||"";
  assert.match(bundle,/workflow_dispatch/);
  assert.doesNotMatch(bundle,/github.event_name == 'push'/);
  for(const name of ["deliver-container","deploy"]){
    const re=new RegExp("  "+name+":\\n[\\s\\S]*?    if: ([^\\n]+)");
    assert.match(workflow.match(re)?.[1]||"",/workflow_dispatch/);
  }
  assert.match(workflow,/release-approval:\n/);
  assert.match(workflow,/needs: \[validate, release-approval, deliver-container\]/);
  assert.match(workflow,/APPROVED_SHA: \$\{\{ vars\.V79_HUB_APPROVED_SHA \}\}/);
  assert.match(workflow,/REQUESTED_SHA: \$\{\{ inputs\.approved_sha \}\}/);
  assert.match(workflow,/APPROVED_SHA.*GITHUB_SHA/);
  assert.match(workflow,/environment: production/);
});
test("both release mechanisms check existing live image before file synchronization",()=>{
  const guard='bash "$stage/scripts/verify-sentinel-preservation.sh" "$stage"';
  assert.ok(direct.includes(guard+' v79-hub'));
  assert.ok(ecosystem.includes(guard+' "$container"'));
  assert.ok(direct.indexOf(guard)<direct.indexOf("rsync -a --delete"));
  assert.ok(ecosystem.indexOf(guard)<ecosystem.indexOf("  rsync -a"));
  for(const f of files)assert.ok(readFileSync(join(root,"scripts/verify-sentinel-preservation.sh"),"utf8").includes(f));
});
test("retains every protected Sentinel file when current container uses it",()=>{
  const r=runGuard();assert.equal(r.status,0,r.stderr);
});
test("fails closed when an incoming release omits a currently live Sentinel module",()=>{
  for(const f of files){
    const r=runGuard({omitted:[f]});
    assert.equal(r.status,34,`${f}: ${r.stdout} ${r.stderr}`);
    assert.match(r.stderr,/BLOCKED: release would remove/);
  }
});
test("fails closed when current container is stopped",()=>{
  const r=runGuard({mode:"stopped"});
  assert.equal(r.status,33,r.stderr);
});
test("does not block a fresh Hub installation with no current image",()=>{
  const r=runGuard({mode:"none",omitted:files});
  assert.equal(r.status,0,r.stderr);
});
test("does not require old Sentinel modules when they were not deployed",()=>{
  const r=runGuard({mode:"absent",omitted:files});
  assert.equal(r.status,0,r.stderr);
});
