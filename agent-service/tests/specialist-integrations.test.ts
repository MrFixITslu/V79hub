import test from 'node:test';import assert from 'node:assert/strict';
import {specialistIntegrationReport} from '../src/specialist-integrations.js';
import {chatRoleRoster,resolveChatRole} from '../src/chat-roles.js';
import {buildEvidenceLedger} from '../src/evidence.js';import {answerCandidates} from '../src/evidence-answer.js';
const now=Date.now(),stamp=new Date(now).toISOString();
const context={userId:'synthetic-owner',organizationId:'synthetic-org',email:'vision79slu@gmail.com',organizationName:'Synthetic',ownerAgent:true,hubAdmin:true,allowedSystems:[]};
const snapshot=()=>({generatedAt:stamp,owner:{email:context.email,organizationId:context.organizationId},hubAdmin:{users:2,activeSessions:1},business:{website:{status:'ok',sourceReportedAt:stamp,metrics:{totalLeads:5,privateCustomerEmail:'private@example.invalid'}},tiquet:{status:'ok',sourceReportedAt:stamp,metrics:{jobs:3}}},platform:{},connections:{}});
test('all eight protected roles use their exact application scopes and expose no action authority',()=>{
 const report=specialistIntegrationReport(snapshot(),context,now);assert.equal(report.roles.length,8);
 for(const role of report.roles){assert.equal(role.approvalAuthority,'none');assert.equal(role.mode,'read-only');assert.ok(role.sources.every(s=>role.systems.includes(s.system)));assert.ok(role.skillSha.length===40);}
 assert.deepEqual(report.roles.find(r=>r.id==='sales')!.sources.map(s=>s.system),['website']);
 assert.deepEqual(report.roles.find(r=>r.id==='customer-service')!.sources.map(s=>s.system),['tiquet']);
 assert.ok(!JSON.stringify(report).includes('private@example.invalid'));assert.equal(report.evidenceGateway.status,'managed-separately');
});
test('unavailable, stale and undated sources stay explicit rather than becoming zero or ready',()=>{
 const data=snapshot();data.business.website.sourceReportedAt=new Date(now-900001).toISOString();
 const report=specialistIntegrationReport(data,context,now);assert.equal(report.roles.find(r=>r.id==='sales')!.status,'unavailable');assert.equal(report.roles.find(r=>r.id==='sales')!.sources[0]!.state,'stale');
 const unavailable=specialistIntegrationReport({...snapshot(),business:{}},context,now);assert.equal(unavailable.roles.find(r=>r.id==='finance')!.status,'unavailable');
});
test('wrong organisation and stale snapshot cannot create an integration report',()=>{
 assert.throws(()=>specialistIntegrationReport(snapshot(),{...context,organizationId:'other'},now));
 assert.throws(()=>specialistIntegrationReport({...snapshot(),generatedAt:new Date(now-900001).toISOString()},context,now));
});
test('Hub summaries become attributable facts for owner roles but remain outside finance and sales',()=>{
 const owner=buildEvidenceLedger(snapshot(),resolveChatRole('CEO:').specialist,now);assert.ok(answerCandidates(owner,now).some(c=>c.system==='hub'&&c.reportedAt===stamp));
 for(const id of ['finance','sales'])assert.ok(!buildEvidenceLedger(snapshot(),resolveChatRole(id+':').specialist,now).records.some(r=>r.system==='hub'));
});
