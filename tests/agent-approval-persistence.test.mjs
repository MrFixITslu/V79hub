import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { newDb } from "pg-mem";
import { createHubStorePersistence } from "../server/runtime-store.mjs";
import { PostgresStoreRepository, migrateJsonState } from "../server/postgres-store.mjs";
import { createAgentProposal, decideAgentProposal } from "../server/agent-approval-ledger.mjs";
import { createAgentApprovalAuditChain } from "../server/agent-approval-audit-chain.mjs";

const keyedAudit = createAgentApprovalAuditChain("synthetic-approval-audit-hmac-key-for-tests-1234");

const owner={organizationId:"v79-test-owner",actorUserId:"test-founder"};
const proposal={operation:"draft_operational_report",targetSystem:"hub",
 summary:"Review business priorities for next week",
 rationale:"Prepare a read-only report based on checked aggregate evidence.",
 idempotencyKey:"phase3-persistence-proof-key-001"};
const normalize=raw=>({
 users:Array.isArray(raw.users)?raw.users:[],
 agentActionProposals:Array.isArray(raw.agentActionProposals)?raw.agentActionProposals:[],
 auditEvents:Array.isArray(raw.auditEvents)?raw.auditEvents:[],
 agentProposalAuditTrail:Array.isArray(raw.agentProposalAuditTrail)?raw.agentProposalAuditTrail:[],
});

test("JSON restart keeps approved draft decisions and execution stays disabled",async t=>{
 const dir=await mkdtemp(join(tmpdir(),"v79-agent-json-reload-"));
 t.after(()=>rm(dir,{recursive:true,force:true}));
 const file=join(dir,"hub-store.json");
 const before=createHubStorePersistence({backend:"json",storeFile:file});
 let store=await before.load(normalize,()=>({users:[],agentActionProposals:[],auditEvents:[],agentProposalAuditTrail:[]}));
 const created=createAgentProposal(store.agentActionProposals,proposal,owner);
 assert.equal(created.kind,"created");
 assert.equal(decideAgentProposal(store.agentActionProposals,{
  id:created.proposal.id,...owner,decision:"approve",expectedRevision:1
 }).kind,"decided");
 keyedAudit.append(store.agentProposalAuditTrail,store.agentActionProposals[0],owner.actorUserId);
 await before.save(store);await before.close();
 const after=createHubStorePersistence({backend:"json",storeFile:file});
 store=await after.load(normalize,()=>{throw Error("should never replace existing state");});
 assert.equal(store.agentActionProposals.length,1);
 assert.equal(store.agentActionProposals[0].status,"approved");
 assert.equal(store.agentActionProposals[0].revision,2);
 assert.equal(store.agentActionProposals[0].executionStatus,"disabled");
 assert.equal(store.agentProposalAuditTrail.length,1);
 assert.equal(keyedAudit.verify(store.agentProposalAuditTrail),true);
 assert.equal(readFileSync(file,"utf8").includes("phase3-persistence-proof-key-001"),true);
 await after.close();
});

test("PostgreSQL restart retains proposal and rejects old revision in a competing writer",async t=>{
 const db=newDb({autoCreateForeignKeyIndices:true,noAstCoverageCheck:true});
 const adapter=db.adapters.createPg();
 const pool=new adapter.Pool();t.after(()=>pool.end());
 const repository=new PostgresStoreRepository(pool);
 await migrateJsonState(repository,{users:[],agentActionProposals:[],auditEvents:[],agentProposalAuditTrail:[]});
 const dir=await mkdtemp(join(tmpdir(),"v79-agent-pg-reload-"));
 t.after(()=>rm(dir,{recursive:true,force:true}));
 const cfg={backend:"postgres",storeFile:join(dir,"unused.json"),pool};
 const writer=createHubStorePersistence(cfg);
 const original=await writer.load(normalize,()=>({users:[],agentActionProposals:[],auditEvents:[],agentProposalAuditTrail:[]}));
 const stale=createHubStorePersistence(cfg);
 const staleData=await stale.load(normalize,()=>({users:[],agentActionProposals:[],auditEvents:[],agentProposalAuditTrail:[]}));
 assert.equal(createAgentProposal(original.agentActionProposals,proposal,owner).kind,"created");
 keyedAudit.append(original.agentProposalAuditTrail,original.agentActionProposals[0],owner.actorUserId);
 await writer.save(original);
 assert.equal(writer.revision(),2);
 const restarted=createHubStorePersistence(cfg);
 const loaded=await restarted.load(normalize,()=>{throw Error("should not seed migrated Postgres");});
 assert.equal(loaded.agentActionProposals.length,1);
 assert.equal(loaded.agentActionProposals[0].status,"pending");
 assert.equal(loaded.agentActionProposals[0].executionStatus,"disabled");
 assert.equal(loaded.agentProposalAuditTrail.length,1);
 assert.equal(keyedAudit.verify(loaded.agentProposalAuditTrail),true);
 staleData.auditEvents.push({id:"stale-write"});
 await assert.rejects(stale.save(staleData));
 assert.equal((await repository.load()).state.agentActionProposals.length,1);
 await writer.close();await restarted.close();await stale.close();
});
