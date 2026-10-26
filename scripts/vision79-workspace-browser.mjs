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
const dir = resolve(process.env.V79_PREVIEW_OUTPUT || "preview-artifacts-v2");
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
  role:"admin",platformOperator:true,ownerAgent:false,workspaceOwner:true,
  permissions:["overview","connections","team","security","billing"],appIds:apps.map(a=>a.id)};
const summary={generatedAt:"2026-10-15T16:00:00-04:00",apps:{
  tiquet:{status:"ok",metrics:{jobsByStatus:{open:8,resolved:17},clients:13,jobs:25,teamMembers:4}},
  ffpro:{status:"ok",metrics:{currency:"XCD",currentMonthNet:2800,currentMonthIncome:9300,transactionCount:41}},
  marketing:{status:"ok",metrics:{activeCampaigns:3,customers:31,aiCreditsRemaining:100}},
  pos:{status:"ok",metrics:{currency:"XCD",revenue30d:19240,sales30d:86,openPurchaseOrders:2}},
  academy:{status:"not_configured",metrics:{}}
}};
const report={screens:[],errors:[],blockedExternal:[],checks:[]};
let scenario="normal";
function api(path,auth){
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
    const result=api(new URL(route.request().url()).pathname,auth);
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
try {
  if(process.env.V79_BASELINE === '1') {
    const ctx=await contextFor(1440,1000,true,'dark');const p=await ctx.newPage();
    await p.goto(root);await p.locator('.hub-dashboard').waitFor();await badge(p);await capture(p,'baseline-desktop');
    await ctx.close();
  } else {
    for(const [width,height,name,theme] of [[1440,1000,'desktop','light'],[1440,1000,'desktop-dark','dark'],[1024,900,'compact-desktop','light'],[768,1024,'tablet','light'],[390,844,'mobile','light'],[320,740,'small-mobile','light'],[1920,1080,'wide-desktop','light']]) {
      scenario='normal';const ctx=await contextFor(width,height,true,theme);const p=await ctx.newPage();
      p.on('pageerror',e=>report.errors.push(String(e)));
      await p.goto(root);await p.locator('.v79-app-card').first().waitFor();await p.getByText('8 open service jobs',{exact:true}).waitFor();
      assert.equal(await p.locator('.v79-app-card').count(),5);
      const links=await p.locator('.v79-app-card').evaluateAll(es=>es.map(e=>({product:e.dataset.product,href:e.getAttribute('href'),disabled:e.getAttribute('aria-disabled')})));
      assert.equal(links.find(e=>e.product==='tiquet').href,'/api/apps/tiquet/launch');
      assert.equal(links.find(e=>e.product==='academy').href,null);
      assert.equal(links.find(e=>e.product==='academy').disabled,'true');
      await checkLayout(p,name);
      const contrast=await p.evaluate(()=>{
        const lum=c=>{const a=(c.match(/[\d.]+/g)||[]).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return .2126*a[0]+.7152*a[1]+.0722*a[2]};
        const failures=[];
        for(const e of document.querySelectorAll('.v79-card-description,.v79-card-source,.v79-status,.v79-kpi h3,.v79-action p,.v79-availability>p,.v79-nav-link')) {
          if(!e.getClientRects().length)continue;
          let parent=e,bg;
          while(parent){bg=getComputedStyle(parent).backgroundColor;if(bg!=='rgba(0, 0, 0, 0)' && bg!=='transparent')break;parent=parent.parentElement;}
          if(!parent)continue;const fg=getComputedStyle(e).color;
          const ratio=(Math.max(lum(fg),lum(bg))+.05)/(Math.min(lum(fg),lum(bg))+.05);
          if(ratio<4.5)failures.push({text:e.textContent,ratio,fg,bg});
        }
        return failures;
      });
      assert.deepEqual(contrast,[],name+' readable text contrast');report.checks.push(name+': sampled body/status/navigation contrast >= 4.5:1');
      await p.getByRole('button',{name:'Explore my apps'}).focus();
      assert.ok(await p.getByRole('button',{name:'Explore my apps'}).evaluate(e=>parseFloat(getComputedStyle(e).outlineWidth)>=2));
      await badge(p);await capture(p,name);
      if(name==='desktop') {
        await p.getByRole('button',{name:'Open V79 app launcher'}).click();
        const launcher=p.getByRole('region',{name:'V79 application launcher'});await launcher.waitFor();
        await launcher.getByRole('searchbox').fill('Tiquet');assert.equal(await launcher.getByRole('link').count(),1);
        assert.equal(await launcher.getByRole('link').getAttribute('href'),'/api/apps/tiquet/launch');
        await capture(p,'app-switcher');
        await p.getByRole('button',{name:'Open V79 app launcher'}).click();
        report.checks.push('App switcher search and signed Tiquet link');
        await p.getByRole('button',{name:'Explore my apps'}).click();
        await p.getByRole('heading',{name:'Ecosystem app launcher'}).waitFor();
        await p.reload();await p.getByRole('heading',{name:'Ecosystem app launcher'}).waitFor();
        await p.locator('aside[aria-label="Primary workspace navigation"]').getByRole('button',{name:'Overview',exact:true}).click();
        await p.locator('.v79-app-card').first().waitFor();
        await p.getByRole('button',{name:'Switch to dark mode'}).click();
        await p.locator('.hub-theme-dark').waitFor();assert.equal(await p.locator('.hub-theme-dark').count(),1);await p.reload();await p.locator('.hub-theme-dark').waitFor();assert.equal(await p.locator('.hub-theme-dark').count(),1);
        await p.getByRole('button',{name:'Switch to light mode'}).click();
        report.checks.push('CTA, navigation reload, persisted light/dark toggle, signed launch href and disabled app semantics');
        await capture(p,'desktop-full',true);
      }
      if(name==='mobile') {
        await p.getByRole('button',{name:'More',exact:true}).click();await p.getByRole('dialog',{name:'More workspace options'}).waitFor();await capture(p,'mobile-menu');
        await p.getByRole('dialog').getByRole('button',{name:'Billing',exact:true}).click();await p.getByRole('heading',{name:'Plans & billing'}).waitFor();
        await p.locator('nav[aria-label="Mobile workspace navigation"]').getByRole('button',{name:'Overview',exact:true}).click();await p.locator('.v79-app-card').first().waitFor();
        report.checks.push('Mobile More menu and Billing/Overview navigation');await capture(p,'mobile-full',true);
      }
      await ctx.close();
    }
    for(const mode of ['failure','empty','restricted','missing']) {
      scenario=mode;const ctx=await contextFor(1440,1000,true);const p=await ctx.newPage();
      p.on('pageerror',e=>report.errors.push(String(e)));await p.goto(root);await p.locator('.v79-dashboard').waitFor();
      if(mode==='failure'){await p.getByRole('alert').waitFor();assert.equal(await p.locator('.v79-kpi-value').allTextContents().then(v=>v.every(x=>x==='—')),true);}
      if(mode==='empty'){await p.getByRole('heading',{name:'No enabled applications',exact:true}).last().waitFor();assert.equal(await p.locator('.v79-app-card').count(),0);}
      if(mode==='restricted'){await p.locator('.v79-app-card').waitFor();assert.equal(await p.locator('.v79-app-card').count(),1);assert.equal(await p.locator('.v79-kpi').count(),1);}
      if(mode==='missing'){await p.getByText('No metrics',{exact:true}).first().waitFor();assert.equal(await p.locator('.v79-kpi-value').allTextContents().then(v=>v.every(x=>x==='—')),true);}
      await checkLayout(p,mode);await badge(p);await capture(p,mode);await ctx.close();
    }
    scenario='normal';const ctx=await contextFor(1440,1000,false);const p=await ctx.newPage();await p.goto(root);
    await p.getByRole('heading',{name:'Sign in to your account'}).waitFor();assert.equal(await p.locator('.v79-dashboard').count(),0);
    await p.getByRole('button',{name:'Forgot password?'}).click();await p.getByRole('heading',{name:'Reset your password'}).waitFor();
    report.checks.push('Unauthenticated entry stays on login; recovery UI still available');await ctx.close();
  }
} finally {await browser.close();await new Promise(r=>server.close(r));}
await writeFile(resolve(dir,'browser-report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify(report,null,2));assert.equal(report.errors.length,0);assert.equal(report.blockedExternal.length,0);
