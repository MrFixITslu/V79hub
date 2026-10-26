import { chromium } from "playwright";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve, extname, sep } from "node:path";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { pricingCatalog } from "../shared/pricing-catalog.mjs";

// Static Vite build + loopback API mocks; no V79 production backend, secrets or accounts.
const root = process.env.V79_PREVIEW_ORIGIN || "http://127.0.0.1:4178";
assert.ok(/^http:\/\/127\.0\.0\.1:417[89]$/.test(root));
const dir = resolve(process.env.V79_PREVIEW_OUTPUT || "review-evidence/owner-admin-v3");
await mkdir(dir, {recursive:true});
const products = [
  ["app-tiquet","V79 Digital Tiquet","Tiquet","support","Headphones","https://tiquet.v79sl.com"],
  ["app-ffpro","FFPRO by V79","FFPRO","finance","Wallet","https://ffpro.v79sl.com"],
  ["app-marketing","V79 Digital Marketing","Marketing","marketing","Megaphone","https://marketing.v79sl.com"],
  ["app-v79pos","V79 Digital POS","V79 POS","operations","CreditCard","https://pos.v79sl.com"],
  ["app-academy","V79 Digital Academy","Academy","team","GraduationCap","https://academy.v79sl.com"]
];
const apps = products.map((a,i)=>({
  id:a[0],name:a[1],shortName:a[2],category:a[3],iconName:a[4],appUrl:a[5],
  tagline:"Preview demonstration",description:"Synthetic product card for visual review.",
  status:"active",ssoSupported:true,launchReady:i<4,features:[],
  colorScheme:{primary:"from-blue-600 to-cyan-500",bgGradient:"",badgeBg:"",badgeText:"",border:""}
}));
const user={id:"synthetic-preview-user",username:"previewowner",fullName:"Demo Owner",email:"preview@example.invalid",
  role:"admin",platformOperator:true,ownerAgent:true,workspaceOwner:true,
  permissions:["overview","connections","team","security","billing"],appIds:apps.map(a=>a.id)};
const summary={generatedAt:"2026-10-15T16:00:00-04:00",apps:{
  tiquet:{status:"ok",metrics:{jobsByStatus:{open:8,resolved:17},clients:13,jobs:25,teamMembers:4}},
  ffpro:{status:"ok",metrics:{currency:"XCD",currentMonthNet:2800,currentMonthIncome:9300,transactionCount:41}},
  marketing:{status:"ok",metrics:{activeCampaigns:3,customers:31,aiCreditsRemaining:100}},
  pos:{status:"ok",metrics:{currency:"XCD",revenue30d:19240,sales30d:86,openPurchaseOrders:2}},
  academy:{status:"not_configured",metrics:{}}
}};
const report={screens:[],errors:[],blockedExternal:[],checks:[],requests:[]};
let scenario="normal";
const jobs=[
 {id:'preview-invite',operation:'create_work_item',system:'hub',summary:'Review the invite-only pilot checklist',payload:{detail:'Review pilot readiness. No production changes.'},digest:'a'.repeat(64),revision:1,status:'pending',approval:null,result:null},
 {id:'preview-support',operation:'create_work_item',system:'tiquet',summary:'Review the customer support onboarding guide',payload:{detail:'Prepare recommendations for owner review.'},digest:'b'.repeat(64),revision:1,status:'pending',approval:null,result:null},
 {id:'preview-progress',operation:'create_work_item',system:'hub',summary:'Prepare the weekly delivery review',payload:{detail:'Summarize verified evidence.'},digest:'c'.repeat(64),revision:1,status:'running',approval:null,result:null},
 {id:'preview-uncertain',operation:'create_work_item',system:'hub',summary:'Reconcile an earlier work-item request',payload:{detail:'Check the recorded result before retrying.'},digest:'d'.repeat(64),revision:1,status:'uncertain',approval:null,result:null},
];
const adminData=()=>({generatedAt:new Date().toISOString(),hub:{customers:12,activeCustomers:11,suspendedCustomers:1,pendingInvitations:3,provisioningCustomers:2},apps:{
 pos:{status:'ok',metrics:{totalTenants:4,activeTenants:3,completedSales:86,openPurchaseOrders:2}},ffpro:{status:'ok',metrics:{totalAccounts:6,hubManagedAccounts:6,activeAccounts30d:5,accountsWithSavedData:4}},
 tiquet:{status:'ok',metrics:{totalAccounts:8,activeAccounts:7,totalUsers:19,totalJobs:42}},marketing:{status:'ok',metrics:{totalBusinesses:3,totalUsers:6,totalCampaigns:9,activeSubscriptions:3}},academy:{status:'error',metrics:null,error:'Synthetic statistics connection unavailable'}}});
function api(path,auth){
  if(path==='/api/agent/work-actions')return [200,{mode:'owner-approved-actions',enabled:true,paused:false,jobs}];
  if(path==='/api/agent/chat')return [200,{output:'Review the pilot checklist and resolve the uncertain work-item request before assigning more work. These are recommendations only.',specialist:'Operations'}];
  if(path==='/api/agent/proposals')return [200,{executionEnabled:false,proposals:[],totalProposals:0}];
  if(path==='/api/agent/workforce-briefings')return [200,{mode:'read-only',status:'incomplete',reports:[{slot:'preview-am',ranAt:new Date().toISOString(),state:'incomplete',report:{priority:'attention',coverage:'incomplete',findings:[{id:'preview-open',system:'tiquet',metric:'open_jobs',value:8,severity:'attention'}],missingSources:['academy']}}]}];
  if(path==='/api/agent/coo-workboard')return [200,{mode:'read-only',source:'github-issue-pr-register',collectedAt:new Date().toISOString(),connection:'PARTIAL_OR_COMPLETE',lanes:['Hub'],repositories:[{repo:'V79hub',fetchState:'COMPLETE'}],tracked:[{lane:'Hub',repo:'V79hub',number:209,kind:'pull',label:'Premium workspace visual review',nextStep:'Review browser evidence before any release',githubState:'OPEN_IN_GITHUB',url:'https://github.com/MrFixITslu/V79hub/pull/209'}],runtimeHealth:'UNKNOWN',deployedRevision:'UNKNOWN',customerLaunchGo:'NOT_ESTABLISHED',sentinelCoverage:'NOT_ESTABLISHED',approvalGranted:false,executionEnabled:false,caveat:'Synthetic read-only delivery record'}];
  if(path==='/api/agent/executive-structure')return [200,{mode:'read-only',actionsEnabled:false,roles:[{id:'ceo',name:'CEO · Direction',accountability:'Review priorities and tradeoffs.',mode:'read-only',approvalAuthority:'none'},{id:'coo',name:'COO · Delivery',accountability:'Review delivery evidence and blockers.',mode:'read-only',approvalAuthority:'none'}]}];
  if(path==='/api/admin/platform/overview')return [200,adminData()];
  if(path==='/api/admin/platform/pos/tenants')return [200,[]];
  if(path==='/api/admin/platform/pos/stats')return [200,{...adminData().apps.pos.metrics,inactiveTenants:1,activeMemberships:6,activeLocations:4,products:24}];
  if(path==='/api/admin/academy/courses')return [200,[]];
  if(path==='/api/admin/audit')return [200,{events:[]}];
  if(path==="/api/billing/pricing/catalog")return [200,pricingCatalog()];
  if(path==="/api/billing/pricing/requests"||path==="/api/admin/pricing/requests")return [200,{requests:[]}];
  if(path==="/api/billing/orders"||path==="/api/admin/billing/manual/orders")return [200,{orders:[]}];
  if(path==="/api/admin/customers")return [200,{customers:[],invited:[],assignableApps:apps}];
  if(path==="/api/auth/me")return [auth?200:401,auth?{user,organization:{name:"Vision79 · Demo workspace"}}:{error:"Not authenticated"}];
  if(path==="/api/auth/recovery-status")return [200,{emailRecoveryEnabled:false,supportEmail:"preview@example.invalid"}];
  if(path==="/api/ecosystem/apps")return [200,scenario==="empty"?[]:scenario==="restricted"?apps.slice(0,1):apps];
  if(path==="/api/dashboard/summary") {
    if(scenario==="failure") return [503,{error:"Synthetic outage"}];
    if(scenario==="empty" || scenario==="restricted") return [200,{generatedAt:summary.generatedAt,apps:{}}];
    if(scenario==="missing") return [200,{generatedAt:summary.generatedAt,apps:Object.fromEntries(Object.keys(summary.apps).map(k=>[k,{status:"ok",metrics:{}}]))}];
    return [200,summary];
  }
  if(path==="/api/users")return [200,[user]];
  if(path==="/api/connections/status")return [200,{checkedAt:summary.generatedAt,apps:Object.fromEntries(["tiquet","ffpro","marketing","pos"].map(k=>[k,{status:"online",responseMs:18}]))}];
  if(path.includes("mfa")||path.includes("security"))return [200,{enabled:true,mandatory:true}];
  if(/^\/api\/apps\/[^/]+\/launch/.test(path))return [409,{error:"Preview launch disabled"}];
  if(path==="/api/billing/summary")return [200,{
    organization:"V79 Demo Workspace",planName:"Synthetic pilot plan",status:"trial",
    accessStatus:"trial_active",trialStartedAt:"2026-10-15T12:00:00-04:00",
    trialEndsAt:"2026-10-29T12:00:00-04:00",paidThroughAt:null,billingCycle:"monthly",
    enabledApps:apps.slice(0,4).map(a=>({id:a.id,name:a.name})),
    pricing:{currency:"XCD",monthly:49,annual:490,custom:null},
    renewalDate:null,billingManagedBy:"V79 Digital",supportEmail:"preview@example.invalid",
    selfServicePaymentsEnabled:false,sandboxTestPaymentsEnabled:false,manualPaymentAvailable:false
  }];
  if(path.includes("subscriptions")||path.includes("billing"))return [200,{status:"trial",products:[],invoices:[],subscriptions:[]}];
  return [200,{}];
}
const distRoot=resolve(process.env.V79_PREVIEW_DIST || "dist");
const server=createServer(async(req,res)=>{
  try {
    const pathname=decodeURIComponent(new URL(req.url,root).pathname);
    const file=resolve(distRoot,pathname.slice(1) || "index.html");
    if(!file.startsWith(distRoot+sep)) {res.writeHead(403);res.end();return;}
    let bytes;try {bytes=await readFile(file);} catch {bytes=await readFile(resolve(distRoot,"index.html"));}
    res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml'})[extname(file)] || 'text/html');res.end(bytes);
  } catch {res.writeHead(500);res.end();}
});
await new Promise(r=>server.listen(Number(new URL(root).port),'127.0.0.1',r));
const browser=await chromium.launch({headless:true,executablePath:process.env.V79_CHROMIUM_PATH || undefined,args:["--no-sandbox","--disable-dev-shm-usage","--use-gl=angle","--use-angle=swiftshader","--enable-unsafe-swiftshader"]});
async function contextFor(w,h,auth,theme="light"){
  const context=await browser.newContext({viewport:{width:w,height:h},deviceScaleFactor:1,reducedMotion:"reduce"});
  await context.addInitScript((theme)=>{
    if(!localStorage.getItem("v79-hub-theme")) localStorage.setItem("v79-hub-theme",theme);
    window.WebSocket=class OfflineSocket{constructor(){this.readyState=1;}close(){}send(){}addEventListener(){}removeEventListener(){}};
  },theme);
  await context.route("**/*",route=>{
    const url=new URL(route.request().url());
    if(url.origin!==root){report.blockedExternal.push(url.origin);return route.abort("blockedbyclient");}
    return route.continue();
  });
  await context.route("**/api/**",route=>{
    const req=route.request();report.requests.push({path:new URL(req.url()).pathname,method:req.method()});
    const result=api(new URL(req.url()).pathname,auth);
    return route.fulfill({status:result[0],contentType:"application/json",body:JSON.stringify(result[1])});
  });
  return context;
}

async function badge(page){
  await page.evaluate(()=>{
    if(document.getElementById("preview-badge"))return;
    const mark=document.createElement("div");mark.id="preview-badge";
    mark.textContent="VISUAL REVIEW · SAMPLE DATA · NOT PRODUCTION";
    mark.style.cssText="position:fixed;bottom:86px;right:16px;z-index:999999;background:#fff;color:#1c3a65;border:1px solid #8fa8ce;padding:9px 12px;border-radius:8px;font:600 11px system-ui;pointer-events:none";
    document.body.appendChild(mark);
  });
}
async function capture(page,name,full=false){
  await badge(page);
  if(full) await page.addStyleTag({content:'.v79-shell {height:auto!important;overflow:visible!important} .v79-shell>main {overflow:visible!important} .v79-sidebar {position:sticky;top:0}'});
  await page.screenshot({path:resolve(dir,name+'.png'),fullPage:full,animations:'disabled'});
  report.screens.push({file:name+'.png',viewport:page.viewportSize(),fullPage:full});
}
async function checkLayout(page,label){
  const issues=await page.evaluate(()=>{
    const main=document.querySelector('main');
    const overflowing=main.scrollWidth>main.clientWidth+1 || document.documentElement.scrollWidth>innerWidth+1;
    const bad=[...document.querySelectorAll('.v79-app-card,.v79-kpi,.v79-hero,.v79-focus')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.className);
    return {overflowing,bad};
  });
  assert.equal(issues.overflowing,false,label+' horizontal page overflow');
  assert.deepEqual(issues.bad,[],label+' clipped card contents');
  const numbers=await page.locator('.v79-kpi-value,.v79-card-metrics dd').evaluateAll(es=>es.map(e=>({text:e.textContent,width:e.clientWidth,scroll:e.scrollWidth,height:e.clientHeight,line:parseFloat(getComputedStyle(e).lineHeight)})));
  assert.ok(numbers.every(n=>n.scroll<=n.width+1 && n.height<=n.line+1),label+' currency totals must fit one line');
  if(page.viewportSize().width<1024){
    const bg=await page.locator('.v79-mobile-nav').evaluate(e=>getComputedStyle(e).backgroundColor);
    assert.equal(bg,'rgb(16, 33, 58)',label+' navy mobile navigation must survive theme bridge');
  }
  report.checks.push(label+': no horizontal overflow, clipped card contents or wrapped totals; mobile nav contrast preserved');
}
async function areaLayout(p,label){
 await checkLayout(p,label);
 const overflow=await p.locator('.v79-area-hero,.v79-admin-app,.v79-owner-metric,.v79-area-card,.v79-admin-metric').evaluateAll(es=>es.filter(e=>e.getClientRects().length&&e.scrollWidth>e.clientWidth+1).map(e=>e.className));
 assert.deepEqual(overflow,[],label+' no clipped area cards');
 const contrast=await p.evaluate(()=>{
  const lum=c=>{const a=c.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*a[0]+.7152*a[1]+.0722*a[2]};const fails=[];
  for(const e of document.querySelectorAll('.v79-area-heading p,.v79-owner-metric>span,.v79-owner-metric p,.v79-admin-app>p,.v79-admin-app dt,.v79-source-note,.v79-data-status,.v79-legacy-panel .text-slate-400')){
   if(!e.getClientRects().length)continue;let parent=e,bg;while(parent){bg=getComputedStyle(parent).backgroundColor;if(bg!=='rgba(0, 0, 0, 0)'&&bg!=='transparent')break;parent=parent.parentElement;}if(!parent)continue;
   const fg=getComputedStyle(e).color,ratio=(Math.max(lum(bg),lum(fg))+.05)/(Math.min(lum(bg),lum(fg))+.05);if(ratio<4.5)fails.push({text:e.textContent,ratio,fg,bg});
  }return fails;
 });assert.deepEqual(contrast,[],label+' readable body/label contrast');report.checks.push(label+': cards fit; sampled text contrast >= 4.5:1');
}
try {
 for(const [w,h,device,theme] of [[1440,1000,'desktop','light'],[1440,1000,'desktop-dark','dark'],[1024,900,'compact-desktop','light'],[768,1024,'tablet','light'],[390,844,'mobile','light'],[320,740,'small-mobile','light']]){
  for(const view of ['assistant','admin']){
   const ctx=await contextFor(w,h,true,theme);const p=await ctx.newPage();p.setDefaultTimeout(10000);p.on('pageerror',e=>report.errors.push(String(e)));
   await p.goto(root+'/?view='+view);await p.locator(view==='assistant'?'.v79-owner-metric strong':'.v79-admin-app').first().waitFor();
   if(view==='assistant')await p.getByText('Review the invite-only pilot checklist',{exact:true}).waitFor();else await p.getByText('Statistics available',{exact:true}).first().waitFor();
   await areaLayout(p,view+'-'+device);await capture(p,view+'-'+device);
   if(view==='assistant'){
    await p.getByRole('button',{name:'Ask Assistant',exact:true}).click();await p.getByRole('button',{name:/CEO · Direction/}).click();
    const composer=p.getByRole('textbox',{name:'Message to your agents'});assert.match(await composer.inputValue(),/CEO review/);await areaLayout(p,'chat-'+device);
    if(['desktop','mobile','desktop-dark'].includes(device))await capture(p,'chat-'+device);
    await p.getByRole('button',{name:'New task',exact:true}).click();await p.getByRole('form',{name:'New work item'}).waitFor();
    await p.getByRole('button',{name:'Ask Assistant',exact:true}).click();assert.match(await composer.inputValue(),/CEO review/);
    if(device==='desktop'){
     await p.getByRole('button',{name:'Send message',exact:true}).click();await p.getByText('Review the pilot checklist and resolve the uncertain work-item request before assigning more work. These are recommendations only.',{exact:true}).waitFor();
     await p.getByRole('button',{name:'Prepare as task',exact:true}).click();await p.getByText('Draft prepared only. Review it and choose Queue for review; your approval is still required.',{exact:true}).waitFor();
     assert.match(await p.locator('#workspace-tasks input[minlength="8"]').inputValue(),/CEO review/);await capture(p,'tasks-desktop');await areaLayout(p,'tasks-desktop');
     await p.getByRole('button',{name:'Delivery board',exact:true}).click();await p.getByText('Premium workspace visual review',{exact:true}).waitFor();await capture(p,'delivery-desktop');
     await p.getByRole('button',{name:'Tools & reports',exact:true}).click();await areaLayout(p,'tools-desktop');
     await p.getByRole('button',{name:'Executive review',exact:true}).click();await p.locator('#workspace-tools').getByText('CEO · Direction',{exact:true}).waitFor();await capture(p,'executive-desktop');
     await p.getByRole('button',{name:'Today',exact:true}).click();await p.getByRole('button',{name:'Load briefing history',exact:true}).click();await p.getByText('Evidence is incomplete',{exact:true}).waitFor();await capture(p,'assistant-full',true);
    }report.checks.push(device+': prompts do not auto-send; chat draft survives navigation; task editor remains reachable');
   }else if(device==='desktop'){
    await p.getByRole('button',{name:/Customers awaiting provisioning/}).click();await p.getByRole('heading',{name:'Customers',exact:true}).waitFor();await capture(p,'customers-desktop');
    await p.getByRole('navigation',{name:'Platform administration'}).getByRole('button',{name:'Applications',exact:true}).click();
    await p.getByRole('button',{name:'Academy',exact:true}).click();await p.getByRole('heading',{name:'Academy workspace'}).waitFor();
    await p.getByRole('button',{name:'Back to applications',exact:true}).click();
    await p.getByRole('navigation',{name:'Platform administration'}).getByRole('button',{name:'Overview',exact:true}).click();await p.getByText('Statistics available',{exact:true}).first().waitFor();
    await capture(p,'admin-full',true);report.checks.push('Provisioning routes to customers; Academy reached via Applications and back');
   }await ctx.close();
  }
 }
 const ctx=await contextFor(1440,1000,true);const p=await ctx.newPage();p.on('pageerror',e=>report.errors.push(String(e)));
 await p.goto(root+'/?view=admin');await p.getByText('Statistics available',{exact:true}).first().waitFor();
 await ctx.route('**/api/admin/platform/overview',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Synthetic refresh failure'})}));
 await p.getByRole('button',{name:'Refresh',exact:true}).click();await p.getByText('Synthetic refresh failure',{exact:true}).waitFor();assert.equal(await p.locator('.v79-data-status').filter({hasText:'Stale snapshot'}).count(),5);await capture(p,'admin-stale');
 await ctx.route('**/api/admin/platform/overview',r=>r.fulfill({status:403,contentType:'application/json',body:'{}'}));
 await p.getByRole('button',{name:'Refresh',exact:true}).click();await p.getByText('Sign in with an authorized platform administrator session.',{exact:true}).waitFor();assert.deepEqual(await p.locator('.v79-admin-metric strong').allTextContents(),['—','—','—','—','—']);await capture(p,'admin-access-denied');
 await ctx.route('**/api/admin/platform/overview',r=>{const data=adminData();data.apps=Object.fromEntries(Object.keys(data.apps).map(k=>[k,{status:'ok',metrics:{}}]));return r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});});
 await p.getByRole('button',{name:'Refresh',exact:true}).click();await p.getByText('Partial statistics',{exact:true}).first().waitFor();assert.ok((await p.locator('.v79-admin-app dd').allTextContents()).every(x=>x==='—'));await capture(p,'admin-missing');
 await ctx.route('**/api/agent/work-actions',r=>r.fulfill({status:403,contentType:'application/json',body:'{}'}));await p.goto(root+'/?view=assistant');await p.getByText('An MFA-verified owner session is required to view actions.',{exact:true}).waitFor();assert.deepEqual(await p.locator('.v79-owner-metric strong').allTextContents(),['—','—','—']);await capture(p,'assistant-access-denied');await ctx.close();
 report.checks.push('Failed refresh visibly stale; 403 removes private counts; absent metrics stay unknown; owner MFA denial displays unknown');
 const writes=report.requests.filter(r=>r.method!=='GET');assert.equal(writes.length,1);assert.equal(writes[0].path,'/api/agent/chat');assert.deepEqual(report.errors,[]);assert.deepEqual(report.blockedExternal,[]);
 report.checks.push('Only explicit chat POST; no approvals, execution, provisioning or deployment requests');
} finally {await browser.close();await new Promise(r=>server.close(r));await writeFile(resolve(dir,'browser-report.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify({screens:report.screens.length,checks:report.checks.length,errors:report.errors,blockedExternal:report.blockedExternal}));
