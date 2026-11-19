// Actual application HTTP journey. All identities, funds and data are CI fixtures.
// No payment provider, live account, mail delivery or public origin is contacted.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {request as httpRequest} from 'node:http';
const env=process.env;
assert.equal(env.GITHUB_ACTIONS,'true');
assert.equal(env.V79_EPHEMERAL_CI,'1');
assert.ok(!env.RESEND_API_KEY&&env.V79_TRIAL_REMINDERS_ENABLED!=='1');
for(const k of ['STAGE_ADMIN_PASSWORD','STAGE_CUSTOMER_PASSWORD','STAGE_SITE_ADMIN_PASSWORD','STAGE_INTAKE_SECRET','STAGE_PAYMENT_SECRET'])assert.ok(env[k]?.length>=24,k);
const endpoints={hub:'http://v79-hub:3040',website:'http://website:3000',tiquet:'http://tiquet:3050',ffpro:'http://ffpro:3010'};
const publicOrigins={hub:'https://hub.v79sl.com',website:endpoints.website,tiquet:'https://tiquet.v79sl.com',ffpro:'https://ffpro.v79sl.com'};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function call(app,path,{method='GET',body,cookie,headers={}}={}){
  assert.ok(path.startsWith('/')&&!path.startsWith('//'));
  const url=new URL(path,endpoints[app]);
  assert.equal(url.origin,endpoints[app]);
  const h={accept:'application/json',origin:publicOrigins[app],...headers};
  if(cookie)h.cookie=cookie;
  if(body!==undefined)h['content-type']='application/json';
  const options={method,headers:h,body:body===undefined?undefined:JSON.stringify(body),redirect:'manual',signal:AbortSignal.timeout(18000)};
  if(app!=='ffpro')return fetch(url,options);
  // Emulate the existing HTTPS reverse proxy while connecting exclusively
  // to the disposable internal FFPRO listener, not the public DNS name.
  return new Promise((resolve,reject)=>{
    const req=httpRequest(url,{method,headers:{...h,host:'ffpro.v79sl.com','x-forwarded-proto':'https','x-forwarded-host':'ffpro.v79sl.com'},signal:options.signal},r=>{
      const chunks=[];r.on('data',b=>chunks.push(b));r.on('error',reject);
      r.on('end',()=>{const result=new Headers();for(const [k,v] of Object.entries(r.headers)){for(const item of Array.isArray(v)?v:[v])if(item!==undefined)result.append(k,String(item));}resolve(new Response(Buffer.concat(chunks),{status:r.statusCode||502,headers:result}));});
    });
    req.on('error',reject);req.end(options.body);
  });
}
async function checked(app,path,options={},statuses=[200]){
  const r=await call(app,path,options);
  // Never print response bodies or session cookies on failure.
  assert.ok(statuses.includes(r.status),app+' '+options.method+' '+path.replace(/\/portal\/[^/]+/,'/portal/[token]')+' HTTP '+r.status);
  return r;
}
const json=async(...a)=>(await checked(...a)).json();
function cookie(r,name){
  const values=r.headers.getSetCookie?.()||[r.headers.get('set-cookie')||''];
  const v=values.find(x=>name?x.startsWith(name+'='):x.includes('='));
  assert.ok(v,'session cookie missing');
  return v.split(';')[0];
}
async function poll(label,fn,seconds=145){
  for(let i=0;i<seconds;i++){const v=await fn();if(v)return v;await sleep(1000);}
  throw Error('Timeout: '+label);
}
async function health(app,path){await poll(app+' readiness',async()=>{try{return(await call(app,path)).ok}catch{return false}},100);}
async function loginHub(username,password,organizationId){
  return cookie(await checked('hub','/api/auth/login',{method:'POST',body:{username,password,...(organizationId?{organizationId}:{})}}),'v79_hub_session');
}
async function launch(app,hubCookie){
  const grant=await checked('hub','/api/apps/'+app+'/launch',{cookie:hubCookie},[302]);
  const target=new URL(grant.headers.get('location'));assert.equal(target.origin,publicOrigins[app]);
  assert.equal(target.pathname,'/api/platform/launch');
  const ticket=target.searchParams.get('ticket');assert.ok(ticket);
  return cookie(await checked(app,target.pathname+'?ticket='+encodeURIComponent(ticket),{},[302]),app==='tiquet'?'tiquet_session':'ffpro.sid');
}
for(const [a,p] of [['hub','/api/health'],['tiquet','/health'],['ffpro','/api/health']])await health(a,p);
if(process.argv.includes('--provision')){
  const admin=await loginHub('admin',env.STAGE_ADMIN_PASSWORD);
  const p=await json('hub','/api/admin/customers/synthetic-customer-a/provision',{method:'POST',cookie:admin,body:{appIds:['app-tiquet','app-ffpro']}});
  assert.ok(p.results?.length===2&&p.results.every(x=>x.status==='active'&&x.skipped!==true),'real provisioners required');
  const user=await loginHub('owner-a@example.invalid',env.STAGE_CUSTOMER_PASSWORD,'synthetic-customer-a');
  const c=await launch('tiquet',user);
  const me=await json('tiquet','/api/auth/me',{cookie:c});
  assert.match(me.account_id,/^[0-9a-f-]{36}$/i);
  // Only this disposable workspace identifier is passed to the runner.
  console.log('INTAKE_ACCOUNT_ID='+me.account_id);
  process.exit(0);
}
await health('website','/api/ready');
const hubCookie=await loginHub('owner-a@example.invalid',env.STAGE_CUSTOMER_PASSWORD,'synthetic-customer-a');
const tc=await launch('tiquet',hubCookie),fc=await launch('ffpro',hubCookie);
const tiquetMe=await json('tiquet','/api/auth/me',{cookie:tc});assert.match(tiquetMe.account_id,/^[0-9a-f-]{36}$/i);
const csrf=await json('ffpro','/api/auth/csrf',{cookie:fc});assert.ok(csrf.csrfToken);
const fh={'x-csrf-token':csrf.csrfToken};
const foptions={cookie:fc,headers:fh};
const listJobs=()=>json('tiquet','/api/jobs',{cookie:tc});
const listProjects=async()=>(await json('ffpro','/api/projects',foptions)).projects;
const email='journey-'+randomUUID()+'@example.invalid';
const enquiry={name:'Synthetic Journey Customer',company:'Synthetic Journey Company',email,phone:'5550100',serviceRequested:'Isolated ICT acceptance',message:'CI-only customer journey'};
const key=randomUUID();
const created=await json('website','/api/leads',{method:'POST',headers:{'idempotency-key':key},body:enquiry},[201]);
assert.ok(Number(created.crmLeadId)>0);
const lead=created.crmLeadId;
const repeat=await json('website','/api/leads',{method:'POST',headers:{'idempotency-key':key},body:enquiry});
assert.equal(repeat.crmLeadId,lead);
const matchedJobs=async()=>(await listJobs()).filter(x=>x.clientEmail===email);
assert.equal((await matchedJobs()).length,0);
await checked('website','/api/admin/crm/leads/'+lead+'/convert',{method:'POST',body:{}},[401]);
await checked('tiquet','/api/public/intake',{method:'POST',headers:{'X-Intake-Secret':env.STAGE_INTAKE_SECRET},body:{...enquiry,source:'website2026',eventId:randomUUID()}},[422]);
console.log('JOURNEY_PASS enquiry_crm_only_idempotent_no_ticket');
let site=cookie(await checked('website','/api/admin/login',{method:'POST',body:{password:env.STAGE_SITE_ADMIN_PASSWORD}}));
site=cookie(await checked('website','/api/admin/change-password',{method:'POST',cookie:site,body:{currentPassword:env.STAGE_SITE_ADMIN_PASSWORD,newPassword:randomUUID()+randomUUID()}}));
const crm='/api/admin/crm/leads/'+lead;
const before=await json('website',crm+'/tiquet-sync',{cookie:site});assert.equal(before.status,'awaiting_conversion');
await checked('website',crm+'/tiquet/retry',{method:'POST',cookie:site,body:{}},[409]);
assert.equal((await matchedJobs()).length,0);
const conv=await json('website',crm+'/convert',{method:'POST',cookie:site,body:{contractValue:1000,billingEmail:email}});
assert.ok(conv.isConverted);assert.equal(conv.stage,'Won');
await checked('website',crm+'/convert',{method:'POST',cookie:site,body:{contractValue:1000,billingEmail:email}});
const delivered=await poll('CRM conversion delivery',async()=>{const s=await json('website',crm+'/tiquet-sync',{cookie:site});return s.status==='sent'&&s});
const job=await poll('real Tiquet job',async()=>{const jobs=await matchedJobs();assert.ok(jobs.length<=1);return jobs[0]});
assert.equal(job.intakeEventId,delivered.eventId);
assert.equal((await matchedJobs()).length,1);
assert.ok(job.secureToken);
const jobPath='/api/jobs/'+encodeURIComponent(job.id);
const currentJob=async()=>{const j=(await matchedJobs()).find(x=>x.id===job.id);assert.ok(j);return j};
const payments=()=>json('tiquet','/api/payments?jobId='+encodeURIComponent(job.id),{cookie:tc});
const jobProjects=async()=>(await listProjects()).filter(p=>String(p.name).includes(job.id));
assert.equal((await jobProjects()).length,0);
console.log('JOURNEY_PASS approved_conversion_one_real_tiquet_job');
await checked('tiquet',jobPath,{method:'PUT',cookie:tc,body:{amount:1000,status:'estimation'}});
const portal='/api/portal/'+encodeURIComponent(job.secureToken);
await checked('tiquet',portal+'/approve-quote',{method:'POST',body:{}});
await checked('tiquet',portal+'/approve-quote',{method:'POST',body:{}});
const listed=await poll('FFPRO project from real approval outbox',async()=>{const xs=await jobProjects();assert.ok(xs.length<=1);return xs[0]});
const pp='/api/projects/'+encodeURIComponent(listed.id);
let project=(await json('ffpro',pp,foptions)).project;
assert.equal(project.data.tiquet.jobId,job.id);
assert.equal(project.data.tiquet.organizationId,'synthetic-customer-a');
assert.equal(project.data.tiquet.planningStatus,'in-planning');
assert.equal((await jobProjects()).length,1);
assert.equal((await payments()).length,0);
console.log('JOURNEY_PASS quote_approval_one_tenant_bound_project_no_cash');
await checked('ffpro',pp+'/ready-for-review',{...foptions,method:'POST',body:{approvedFileIds:[]}},[409]);
const data={...project.data,tasks:project.data.tasks.map(t=>({...t,completed:true}))};
await checked('ffpro',pp,{...foptions,method:'PUT',body:{data,expectedVersion:project.version}});
await checked('ffpro',pp+'/ready-for-review',{...foptions,method:'POST',body:{approvedFileIds:[]}});
await poll('Tiquet real review callback',async()=>{const j=await currentJob();return j.status==='review'&&j});
await checked('tiquet',jobPath,{method:'PUT',cookie:tc,body:{status:'invoiced'}},[409]);
const policy=await json('tiquet',jobPath+'/review-deposit-policy',{method:'POST',cookie:tc,body:{policy:'twenty_percent'}});
assert.equal(policy.terms.amount,200);
assert.equal((await payments()).length,0);
console.log('JOURNEY_PASS planning_review_deposit_gate_20_percent');
async function pay(amount,reference){
  return json('tiquet','/api/payments',{method:'POST',cookie:tc,body:{jobId:job.id,amount,method:'cash',reference}},[201]);
}
const deposit=await pay(200,'CI-deposit-'+key);
assert.equal(deposit.summary.paidAmount,200);assert.equal(deposit.summary.outstandingAmount,800);
assert.equal(deposit.summary.fullyPaid,false);
assert.ok(deposit.job.depositPaid);
const ledger=async()=>{const d=await json('ffpro','/api/data',foptions);return d.data?.transactions||[]};
async function synced(events){
  return poll('FFPRO cash event delivery',async()=>{
    const p=await payments(),t=await ledger();
    const matching=t.filter(x=>events.some(e=>x.id==='tiquet:'+e.ffproEventId));
    if(!events.every(e=>p.some(x=>x.id===e.id&&x.ffproSyncStatus==='sent')))return false;
    if(matching.length!==events.length)return false;
    for(const e of events){const row=matching.find(x=>x.id==='tiquet:'+e.ffproEventId);assert.equal(Number(row.amount),Number(e.amount));assert.equal(row.type,'income');assert.ok(row.notes.includes(job.id));}
    return matching;
  });
}
await synced([deposit.payment]);
await checked('tiquet',jobPath,{method:'PUT',cookie:tc,body:{status:'paid'}},[409]);
await checked('tiquet',jobPath,{method:'PUT',cookie:tc,body:{status:'invoiced'}});
const pdf=await checked('tiquet',jobPath+'/invoice.pdf',{cookie:tc});
assert.match(pdf.headers.get('content-type'),/application\/pdf/);
assert.equal(Buffer.from(await pdf.arrayBuffer()).subarray(0,5).toString(),'%PDF-');
await poll('FFPRO real invoice closure callback',async()=>{const p=(await json('ffpro',pp,foptions)).project;return p.data.tiquet.planningStatus==='closed'&&p});
assert.equal((await payments()).length,1,'invoicing must not create cash');
assert.equal((await synced([deposit.payment])).length,1);
console.log('JOURNEY_PASS invoice_pdf_project_closed_no_automatic_revenue');
const final=await pay(800,'CI-final-'+key);
assert.equal(final.summary.paidAmount,1000);assert.equal(final.summary.outstandingAmount,0);assert.equal(final.summary.fullyPaid,true);
assert.equal(final.job.status,'paid');
await checked('tiquet','/api/payments',{method:'POST',cookie:tc,body:{jobId:job.id,amount:1,method:'cash',reference:'CI-overpayment'}},[409]);
const entries=await synced([deposit.payment,final.payment]);
assert.equal(entries.reduce((sum,x)=>sum+Number(x.amount),0),1000);
assert.equal((await payments()).length,2);
assert.equal((await matchedJobs()).length,1);assert.equal((await jobProjects()).length,1);
console.log('JOURNEY_PASS deposit_final_payment_exact_ledger_balance_no_overpayment');
console.log('CUSTOMER_JOURNEY=PASS synthetic_cash_only no_provider_charge no_production_mutation');
