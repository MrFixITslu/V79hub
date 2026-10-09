import test from "node:test";
import assert from "node:assert/strict";
import { validateIsolatedAgentStagingPlan } from "../scripts/agent-staging-preflight.mjs";

const good=() => ({
  hostKind:"dedicated-cloud-vm",provider:"Test Cloud",
  disposableVm:true,syntheticDataOnly:true,denyProductionLan:true,
  privateAppNetwork:true,outboundWritesBlocked:true,
  ephemeralKeysGeneratedInsideVm:true,noProductionMounts:true,
  ownerMfaRequired:true,destructionPlanConfirmed:true,authorizedExecutor:true,
  independentBudgetApproved:true,
  maxCostUsd:10,destroyByUtc:new Date(Date.now()+3600_000).toISOString(),
  hubCommit:"a".repeat(40),tiquetCommit:"b".repeat(40),
  hubOrigin:"hub.internal",tiquetOrigin:"tiquet.internal",databaseOrigin:"db.internal",
  localOutputPath:"/tmp/v79-agent-stage-123456789",
});

test("full synthetic dedicated VM plan is eligible for next human execution gate",()=>{
  assert.deepEqual(validateIsolatedAgentStagingPlan(good()),{ready:true,errors:[]});
});
test("missing provider, budget and safety fields all fail closed",()=>{
  const broken=good();
  delete broken.provider;delete broken.maxCostUsd;
  broken.denyProductionLan=false;
  const result=validateIsolatedAgentStagingPlan(broken);
  assert.equal(result.ready,false);
  assert.ok(result.errors.length>=3);
});
test("production endpoints, Tailscale, public URLs and raw secrets reject",()=>{
  for (const [field,value] of Object.entries({
    hubOrigin:"https://hub.v79sl.com",
    tiquetOrigin:"192.168.100.163",
    databaseOrigin:"10.1.211.192",
    productionEnvFile:"/opt/v79/hub/.env",
    productionBackupPath:"/home/firelion/ServerBackups",
    allowPublicIngress:true,enableAgentWrites:true,deployProduction:true,
  })) {
    assert.equal(validateIsolatedAgentStagingPlan({...good(),[field]:value}).ready,false,field);
  }
});
test("malformed SHAs, cost and deletion window reject",()=>{
  for (const [field,value] of Object.entries({
    hubCommit:"main",tiquetCommit:"abcd",maxCostUsd:Infinity,
    destroyByUtc:new Date(Date.now()+72*3600_000).toISOString(),
    hostKind:"production-docker",
    localOutputPath:"/opt/v79/hub",
  })) {
    assert.equal(validateIsolatedAgentStagingPlan({...good(),[field]:value}).ready,false,field);
  }
});
test("no plan or empty object fails closed",()=>{
  assert.equal(validateIsolatedAgentStagingPlan(null).ready,false);
  assert.equal(validateIsolatedAgentStagingPlan({}).ready,false);
});
