import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createPublicKey, verify } from 'node:crypto';
import { verifyPlatformRequest, signPlatformRequest } from '../server/platform-contract.mjs';
import WebSocket from 'ws';

const secret='test-shared-secret-long-enough-for-platform';
async function listen(server) { await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve)); return `http://127.0.0.1:${server.address().port}`; }

test('private data, retired embedded APIs and one-time app launch', {timeout:30000}, async t => {
  const dir=await mkdtemp(join(tmpdir(),'v79-hub-security-'));
  const storeFile=join(dir,'v79_store.json');
  await writeFile(storeFile,JSON.stringify({
    users:[],
    inventory:[{id:'legacy-stock-must-survive'}],
    settings:{companyName:'Legacy Organisation',taxRate:12.5},
    legacyCustomData:{keep:true}
  }));
  let provision;
  const pos=createServer(async(req,res)=>{
    if(req.url==='/health'){res.writeHead(200).end('ok');return;}
    let body='';for await(const chunk of req)body+=chunk;
    const ok=verifyPlatformRequest({method:req.method,pathname:req.url,timestamp:req.headers['x-v79-timestamp'],signature:req.headers['x-v79-signature'],body,secret});
    if(!ok){res.writeHead(401).end('{}');return;}
    if(body) provision=JSON.parse(body);
    res.setHeader('content-type','application/json');res.end('{"provisioned":true}');
  });
  const posOrigin=await listen(pos);
  const academyRequests=[];
  const academy=createServer(async(req,res)=>{
    if(req.url==='/healthz'){res.writeHead(200).end('ok');return;}
    let body='';for await(const chunk of req)body+=chunk;
    const ok=verifyPlatformRequest({method:req.method,pathname:new URL(req.url,'http://academy.test').pathname,timestamp:req.headers['x-v79-timestamp'],signature:req.headers['x-v79-signature'],body,secret});
    if(!ok){res.writeHead(401,{'content-type':'application/json'}).end('{"error":"bad signature"}');return;}
    academyRequests.push({method:req.method,url:req.url,body});
    res.setHeader('content-type','application/json');
    if(req.method==='GET' && req.url==='/api/courses'){res.end('[{"id":"academy-course-1","title":"Signed Academy Course"}]');return;}
    if(req.method==='GET' && req.url==='/api/platform/admin/stats'){res.end('{"totalCourses":4,"publishedCourses":2,"draftCourses":2,"totalLearners":3,"activeMemberships":2,"totalEnrolments":5,"certificates":1}');return;}
    if(req.method==='POST' && req.url==='/api/courses'){res.writeHead(201).end(body||'{}');return;}
    res.writeHead(404).end('{"error":"not found"}');
  });
  const academyOrigin=await listen(academy);
  const tiquetRequests=[];
  const tiquet=createServer(async(req,res)=>{
    if(req.url==='/health'){res.writeHead(200).end('ok');return;}
    let body='';for await(const chunk of req)body+=chunk;
    const pathname=new URL(req.url,'http://tiquet.test').pathname;
    const ok=verifyPlatformRequest({method:req.method,pathname,timestamp:req.headers['x-v79-timestamp'],signature:req.headers['x-v79-signature'],body:'',secret});
    if(!ok){res.writeHead(401).end('{}');return;}
    tiquetRequests.push({method:req.method,pathname,body});
    res.setHeader('content-type','application/json');
    if(pathname==='/api/platform/admin/stats'){res.end('{"totalAccounts":1}');return;}
    if(pathname==='/api/platform/admin/accounts/a1/suspend' && req.method==='PUT'){res.end('{"status":"suspended"}');return;}
    res.writeHead(404).end('{}');
  });
  const tiquetOrigin=await listen(tiquet);
  let financeSummaryCalls=0;
  const ffpro=createServer(async(req,res)=>{
    if(req.url==='/api/health'){res.writeHead(200).end('ok');return;}
    if(req.url?.startsWith('/api/platform/summary/')){
      financeSummaryCalls++;
      res.setHeader('content-type','application/json');
      res.end('{"metrics":{"currentMonthNet":123456,"currentMonthIncome":200000},"generatedAt":"2026-09-28T00:00:00Z"}');
      return;
    }
    res.writeHead(404).end('{}');
  });
  const ffproOrigin=await listen(ffpro);
  const probe=createServer();const origin=await listen(probe);await new Promise(resolve=>probe.close(resolve));
  const server=spawn(process.execPath,['--import','tsx','server.ts'],{cwd:process.cwd(),env:{...process.env,NODE_ENV:'production',DATA_DIR:dir,PORT:new URL(origin).port,APP_URL:origin,V79_HUB_ADMIN_PASSWORD:'a-unique-admin-password-1234',V79_HUB_ADMIN_EMAIL:'vision79slu@gmail.com',V79_PLATFORM_SHARED_SECRET:secret,V79_FFPRO_LAUNCH_SECRET:secret,V79_TIQUET_LAUNCH_SECRET:secret,V79_MARKETING_LAUNCH_SECRET:secret,POS_BASE_URL:posOrigin,POS_PUBLIC_URL:'https://pos.example.test',ACADEMY_INTERNAL_URL:academyOrigin,TIQUET_INTERNAL_URL:tiquetOrigin,FFPRO_INTERNAL_URL:ffproOrigin},stdio:['ignore','pipe','pipe']});
  let errors='';server.stderr.on('data',c=>errors+=c);
  server.stdout.on('data',c=>errors+=c);
  t.after(async()=>{
    if(server.exitCode===null){const exit=new Promise(resolve=>server.once('exit',resolve));server.kill();await Promise.race([exit,new Promise(resolve=>setTimeout(resolve,1500))]);}
    pos.closeAllConnections();await new Promise(resolve=>pos.close(resolve));
    academy.closeAllConnections();await new Promise(resolve=>academy.close(resolve));
    tiquet.closeAllConnections();await new Promise(resolve=>tiquet.close(resolve));
    ffpro.closeAllConnections();await new Promise(resolve=>ffpro.close(resolve));
    await rm(dir,{recursive:true,force:true});
  });
  const request=(path,options={})=>fetch(origin+path,{redirect:'manual',...options});
  for(let i=0;i<150;i++){try{if((await request('/api/health')).ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
  let health;try{health=await request('/api/health');}catch{throw new Error(`Hub failed to start: ${errors}`);}
  assert.equal(health.status,200,errors);
  assert.equal((await request('/api/inventory')).status,401);
  assert.equal((await request('/api/connections/status')).status,401);
  assert.equal((await request('/api/users')).status,401);
  assert.equal((await request('/api/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:'admin',password:'password123'})})).status,401);
  assert.equal((await request('/api/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:'x'.repeat(121),password:'wrong'})})).status,400);
  assert.equal((await request('/api/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:'admin',password:'x'.repeat(1025)})})).status,400);
  const login=await request('/api/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:'admin',password:'a-unique-admin-password-1234'})});
  assert.equal(login.status,200,errors);
  const preservedStore=JSON.parse(await readFile(storeFile,'utf8'));
  assert.equal(preservedStore.inventory[0].id,'legacy-stock-must-survive');
  assert.equal(preservedStore.settings.companyName,'Legacy Organisation');
  assert.equal(preservedStore.legacyCustomData.keep,true);
  assert.equal(preservedStore.workspace.companyName,'Legacy Organisation');
  assert.equal(preservedStore.organizations.length,1);
  assert.equal(preservedStore.organizations[0].name,'Legacy Organisation');
  assert.equal(preservedStore.memberships.length,1);
  assert.equal(preservedStore.memberships[0].role,'owner');
  const migrationBackup=JSON.parse(await readFile(join(dir,'v79_store_pre_organizations.json'),'utf8'));
  assert.equal(migrationBackup.legacyCustomData.keep,true);
  assert.equal(migrationBackup.organizations.length,0);
  const ownerIdentity=await login.clone().json();
  assert.equal('token' in ownerIdentity,false);
  assert.equal(ownerIdentity.user.platformOperator,true);
  const cookie=login.headers.get('set-cookie').split(';')[0];
  const headers={Cookie:cookie,Origin:origin,'content-type':'application/json'};
  const catalogPost=(body)=>request('/api/ecosystem/apps',{method:'POST',headers,body:JSON.stringify(body)});
  assert.equal((await catalogPost({name:'Bad link',appUrl:'javascript:alert(1)'})).status,400);
  assert.equal((await request('/api/users',{method:'POST',headers,body:JSON.stringify({username:'x'.repeat(121),password:'valid-password-1234'})})).status,400);
  assert.equal((await catalogPost({name:'Bad credentials',appUrl:'https://user:password@example.test/'})).status,400);
  const customApp=await catalogPost({name:'External tool',appUrl:'https://example.test/tool'});
  assert.equal(customApp.status,201);
  const custom=await customApp.json();
  assert.equal(custom.ssoSupported,false);
  assert.match(custom.id,/^app-custom-[a-f0-9-]+$/);
  const catalogPut=(id,body)=>request(`/api/ecosystem/apps/${id}`,{method:'PUT',headers,body:JSON.stringify(body)});
  assert.equal((await catalogPut(custom.id,{id:'app-ffpro'})).status,400);
  assert.equal((await catalogPut(custom.id,{appUrl:'javascript:alert(1)'})).status,400);
  assert.equal((await catalogPut('app-ffpro',{appUrl:'https://example.test/'})).status,403);
  const catalogAfterReject=JSON.parse(await readFile(storeFile,'utf8'));
  assert.equal(catalogAfterReject.ecosystemApps.find(app=>app.id===custom.id).appUrl,'https://example.test/tool');
  const ownerSummary=await (await request('/api/dashboard/summary',{headers:{Cookie:cookie}})).json();
  assert.equal(ownerSummary.apps.ffpro.metrics.currentMonthNet,123456);
  const connectionCheck=await (await request('/api/connections/status',{headers:{Cookie:cookie}})).json();
  assert.equal(connectionCheck.apps.ffpro.status,'online');
  assert.equal(connectionCheck.apps.academy.status,'online');
  assert.equal(connectionCheck.apps.marketing.status,'unavailable');
  assert.equal('metrics' in connectionCheck.apps.ffpro,false);
  const platformOverview=await request('/api/admin/platform/overview',{headers:{Cookie:cookie}});
  assert.equal(platformOverview.status,200);
  const overviewPayload=await platformOverview.json();
  assert.equal(overviewPayload.apps.academy.status,'ok');
  assert.equal(overviewPayload.apps.academy.metrics.totalCourses,4);
  assert.equal((await request('/api/admin/platform/tiquet/stats',{headers:{Cookie:cookie}})).status,200);
  const forwardedBefore=tiquetRequests.length;
  assert.equal((await request('/api/admin/platform/tiquet/accounts/a1/suspend',{method:'PUT',headers,body:'{}'})).status,404);
  assert.equal((await request('/api/admin/platform/tiquet/accounts/a1/plan/pro',{method:'PUT',headers,body:'{}'})).status,404);
  assert.equal((await request('/api/admin/platform/pos/tenants/t1/active/disabled',{method:'PUT',headers,body:'{}'})).status,404);
  assert.equal(tiquetRequests.length,forwardedBefore);
  assert.equal((await request('/api/admin/platform/tiquet/accounts/a1/private-data',{headers:{Cookie:cookie}})).status,404);
  assert.equal((await request('/api/admin/tiquet/accounts/a1/private-data',{headers:{Cookie:cookie}})).status,404);
  assert.equal(tiquetRequests.length,forwardedBefore);
  assert.equal((await request('/api/users',{headers})).status,200);
  assert.equal((await request('/api/users',{method:'POST',headers:{Cookie:cookie,'content-type':'application/json'},body:'{}'})).status,403);
  assert.equal((await request('/api/settings/reset',{method:'POST',headers})).status,410);
  const create=await request('/api/users',{method:'POST',headers,body:JSON.stringify({username:'viewer',password:'viewer-password-1234',role:'viewer'})});
  assert.equal(create.status,201);
  const createdUser=await create.clone().json();
  const afterInvite=JSON.parse(await readFile(storeFile,'utf8'));
  assert.equal(afterInvite.memberships.some(member=>member.userId===createdUser.id),true);
  const viewerLogin=await request('/api/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:'viewer',password:'viewer-password-1234'})});
  const viewerCookie=viewerLogin.headers.get('set-cookie').split(';')[0];
  const financeCallsBeforeViewer=financeSummaryCalls;
  const viewerSummary=await (await request('/api/dashboard/summary',{headers:{Cookie:viewerCookie}})).json();
  assert.equal(viewerSummary.apps.ffpro.status,'restricted');
  assert.deepEqual(viewerSummary.apps.ffpro.metrics,{});
  assert.equal(financeSummaryCalls,financeCallsBeforeViewer);
  assert.equal((await request('/api/users',{headers:{Cookie:viewerCookie}})).status,403);
  assert.equal((await request('/api/pos/checkout',{method:'POST',headers:{...headers,Cookie:viewerCookie},body:'{}'})).status,410);
  assert.equal((await request('/api/apps/pos/launch',{headers:{Cookie:viewerCookie}})).status,403);
  assert.equal((await request('/api/admin/academy/courses',{headers:{Cookie:viewerCookie}})).status,403);
  assert.equal((await request('/api/admin/platform/tiquet/stats',{headers:{Cookie:viewerCookie}})).status,403);
  const otherAdmin=await request('/api/users',{method:'POST',headers,body:JSON.stringify({username:'otheradmin',password:'another-admin-password-1234',role:'admin'})});
  assert.equal(otherAdmin.status,201);
  const otherAdminId=(await otherAdmin.json()).id;
  const updateOther=(body)=>request(`/api/users/${otherAdminId}`,{method:'PUT',headers,body:JSON.stringify(body)});
  assert.equal((await updateOther({username:'  '})).status,400);
  assert.equal((await updateOther({username:'VIEWER'})).status,409);
  assert.equal((await updateOther({username:42})).status,400);
  assert.equal((await updateOther({username:'x'.repeat(121)})).status,400);
  assert.equal((await updateOther({fullName:{unexpected:true}})).status,400);
  assert.equal((await request('/api/users',{method:'POST',headers,body:JSON.stringify({username:'bad-name',password:'valid-password-1234',fullName:{unexpected:true}})})).status,400);
  const persistedAfterRejects=JSON.parse(await readFile(storeFile,'utf8'));
  assert.equal(persistedAfterRejects.users.find(user=>user.id===otherAdminId).username,'otheradmin');
  const otherLogin=await request('/api/auth/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:'otheradmin',password:'another-admin-password-1234'})});
  assert.equal(otherLogin.status,200);
  assert.equal((await otherLogin.clone().json()).user.platformOperator,false);
  const otherCookie=otherLogin.headers.get('set-cookie').split(';')[0];
  assert.equal((await request('/api/admin/platform/overview',{headers:{Cookie:otherCookie}})).status,403);
  assert.equal((await request('/api/admin/platform/tiquet/stats',{headers:{Cookie:otherCookie}})).status,403);
  assert.equal((await request('/api/admin/academy/courses',{headers:{Cookie:otherCookie}})).status,403);
  assert.equal((await request('/api/apps/pos/launch',{headers:{Cookie:otherCookie}})).status,403);
  const academyList=await request('/api/admin/academy/courses',{headers:{Cookie:cookie}});
  assert.equal(academyList.status,200);
  assert.equal((await academyList.json())[0].title,'Signed Academy Course');
  const academyCreate=await request('/api/admin/academy/courses',{method:'POST',headers,body:JSON.stringify({title:'Created through Hub Admin'})});
  assert.equal(academyCreate.status,201);
  assert.equal((await academyCreate.json()).title,'Created through Hub Admin');
  assert.equal(academyRequests.some(row=>row.method==='POST' && JSON.parse(row.body).title==='Created through Hub Admin'),true);
  assert.equal((await request('/api/admin/academy/admin/change-password',{headers:{Cookie:cookie}})).status,404);
  for (const path of ['/api/inventory','/api/transactions','/api/ecosystem/tiquet/tickets','/api/ecosystem/ffpro/records','/api/ecosystem/marketing/campaigns']) {
    assert.equal((await request(path,{headers:{Cookie:cookie}})).status,410,`${path} should be retired from Hub`);
  }
  const launch=await request('/api/apps/pos/launch',{headers:{Cookie:cookie}});
  assert.equal(launch.status,302);
  assert.equal(provision.role,'owner');
  const url=new URL(launch.headers.get('location'));
  assert.equal(url.origin,'https://pos.example.test');
  assert.equal(url.search,'');
  const ticket=new URLSearchParams(url.hash.slice(1)).get('ticket');
  const body=JSON.stringify({product:'pos',ticket});const timestamp=String(Date.now());
  const serviceHeaders={'content-type':'application/json','x-v79-service-id':'v79-pos','x-v79-timestamp':timestamp,'x-v79-signature':signPlatformRequest({method:'POST',pathname:'/api/platform/session/consume',timestamp,body,secret})};
  const consume=await request('/api/platform/session/consume',{method:'POST',headers:serviceHeaders,body});
  assert.equal(consume.status,200);
  const {token,tenantId}=await consume.json();
  assert.equal(tenantId,provision.organization.id);
  const jwks=await (await request('/.well-known/jwks.json')).json();
  const [h,p,s]=token.split('.');
  assert.equal(verify(null,Buffer.from(`${h}.${p}`),createPublicKey({format:'jwk',key:jwks.keys[0]}),Buffer.from(s,'base64url')),true);
  assert.equal((await request('/api/platform/session/consume',{method:'POST',headers:serviceHeaders,body})).status,401);
  for (const [product,serviceId,host] of [['ffpro','v79-ffpro','ffpro.v79sl.com'],['tiquet','v79-tiquet','tiquet.v79sl.com'],['marketing','v79-marketing','marketing.v79sl.com']]) {
    assert.equal((await request(`/api/apps/${product}/launch`,{headers:{Cookie:viewerCookie}})).status,403);
    const launch=await request(`/api/apps/${product}/launch`,{headers:{Cookie:cookie}});
    assert.equal(launch.status,302);
    const url=new URL(launch.headers.get('location'));
    assert.equal(url.host,host);
    assert.equal(url.pathname,'/api/platform/launch');
    const ticket=url.searchParams.get('ticket');
    const payload=JSON.stringify({ticket,product});
    const time=String(Date.now());
    const signed={method:'POST',headers:{'content-type':'application/json','x-v79-service-id':serviceId,'x-v79-timestamp':time,'x-v79-signature':signPlatformRequest({method:'POST',pathname:'/api/platform/session/consume',timestamp:time,body:payload,secret})},body:payload};
    const consumed=await request('/api/platform/session/consume',signed);
    assert.equal(consumed.status,200);
    const identity=await consumed.json();
    assert.equal(identity.user.email,'vision79slu@gmail.com');
    assert.equal(identity.entitlement.product,product);
    assert.equal(identity.organization.id,provision.organization.id);
    assert.equal((await request('/api/platform/session/consume',signed)).status,401);
  }
  const ownerId=preservedStore.memberships[0].userId;
  assert.equal((await request(`/api/users/${ownerId}`,{method:'DELETE',headers})).status,400);
  assert.equal((await request(`/api/users/${ownerId}`,{method:'PUT',headers,body:JSON.stringify({role:'staff'})})).status,400);
  assert.equal((await request(`/api/users/${createdUser.id}`,{method:'DELETE',headers})).status,200);
  const otherSocket=new WebSocket(origin.replace(/^http/,'ws'),{headers:{Cookie:otherCookie,Origin:origin}});
  await new Promise((resolve,reject)=>{otherSocket.once('open',resolve);otherSocket.once('error',reject);});
  const closed=new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('Revoked WebSocket remained open')),3000);
    otherSocket.once('close',code=>{clearTimeout(timer);resolve(code);});
  });
  assert.equal((await request(`/api/users/${otherAdminId}`,{method:'DELETE',headers})).status,200);
  assert.equal(await closed,1008);
  const afterRemoval=JSON.parse(await readFile(storeFile,'utf8'));
  assert.equal(afterRemoval.memberships.some(member=>member.userId===createdUser.id),false);
});

test('administrator password recovery preserves Hub records and old hash is replaced', async t => {
  const dir=await mkdtemp(join(tmpdir(),'v79-hub-reset-'));
  t.after(()=>rm(dir,{recursive:true,force:true}));
  const old='scrypt:old-salt:old-hash';
  const file=join(dir,'v79_store.json');
  const {writeFile,readFile,readdir}=await import('node:fs/promises');
  await writeFile(file,JSON.stringify({users:[{id:'owner',username:'admin',role:'admin',password:old}],inventory:[{id:'record'}]}));
  execFileSync(process.execPath,['scripts/reset-admin-password.mjs'],{cwd:process.cwd(),env:{...process.env,DATA_DIR:dir,V79_HUB_ADMIN_USERNAME:'admin',V79_HUB_ADMIN_PASSWORD:'a-new-unique-password-2026'}});
  const updated=JSON.parse(await readFile(file,'utf8'));
  assert.equal(updated.inventory[0].id,'record');
  assert.match(updated.users[0].password,/^scrypt:[a-f0-9]{32}:[a-f0-9]{128}$/);
  assert.notEqual(updated.users[0].password,old);
  assert.equal((await readdir(dir)).filter(name=>name.includes('before-password-reset')).length,1);
});