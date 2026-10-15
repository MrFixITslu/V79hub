import { chromium } from "playwright";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

// Static Vite build + loopback API mocks; no V79 production backend, secrets or accounts.
const root = "http://127.0.0.1:4178";
const dir = resolve("preview-artifacts");
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
const user={id:"synthetic-preview-user",username:"previewowner",fullName:"Preview Operator",email:"preview@example.invalid",
  role:"admin",platformOperator:true,ownerAgent:false,workspaceOwner:true,
  permissions:["overview","connections","team","security","billing"],appIds:apps.map(a=>a.id)};
const summary={generatedAt:"2026-10-15T16:00:00-04:00",apps:{
  tiquet:{status:"ok",metrics:{jobsByStatus:{open:8,resolved:17},clients:13,jobs:25,teamMembers:4}},
  ffpro:{status:"ok",metrics:{currentMonthNet:2800,currentMonthIncome:9300,transactionCount:41}},
  marketing:{status:"ok",metrics:{activeCampaigns:3,customers:31,aiCreditsRemaining:100}},
  pos:{status:"ok",metrics:{revenue30d:19240,sales30d:86,openPurchaseOrders:2}},
  academy:{status:"not_configured",metrics:{}}
}};
const report={screens:[],errors:[],blockedExternal:[]};
function api(path,auth){
  if(path==="/api/auth/me")return [auth?200:401,auth?{user,organization:{name:"V79 Demo Workspace"}}:{error:"Not authenticated"}];
  if(path==="/api/auth/recovery-status")return [200,{emailRecoveryEnabled:false,supportEmail:"preview@example.invalid"}];
  if(path==="/api/ecosystem/apps")return [200,apps];
  if(path==="/api/dashboard/summary")return [200,summary];
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
const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
async function contextFor(w,h,auth){
  const context=await browser.newContext({viewport:{width:w,height:h},deviceScaleFactor:1,reducedMotion:"reduce"});
  await context.addInitScript(()=>{
    window.WebSocket=class OfflineSocket{constructor(){this.readyState=1;}close(){}send(){}addEventListener(){}removeEventListener(){}};
  });
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
async function shot(page,name,description){
  await page.waitForTimeout(650);
  await page.evaluate(()=>{
    if(document.getElementById("preview-badge"))return;
    const mark=document.createElement("aside");
    mark.id="preview-badge";mark.textContent="ISOLATED PREVIEW · SYNTHETIC DATA · NOT LIVE";
    mark.setAttribute("style","position:fixed;bottom:16px;right:16px;padding:8px 12px;border:1px solid #3779b5;border-radius:12px;background:#07111feF;color:#e3f4ff;z-index:999999;font:700 11px system-ui;pointer-events:none");
    document.body.appendChild(mark);
  });
  await page.screenshot({path:resolve(dir,name+".png"),fullPage:true,animations:"disabled"});
  const headings=await page.locator("h1").allTextContents();
  assert.ok(headings.length,name+" had no h1");
  report.screens.push({file:name+".png",description,width:page.viewportSize().width,headings});
  console.log("SCREEN_OK "+name);
}
function checkErrors(page,name){page.on("pageerror",e=>report.errors.push({screen:name,error:String(e).slice(0,500)}));}
try{
  for(const [width,height,name] of [[1440,900,"01-login-desktop"],[390,844,"02-login-mobile"]]){
    const context=await contextFor(width,height,false);const page=await context.newPage();checkErrors(page,name);
    await page.goto(root);await page.getByRole("heading",{name:/Sign in to your account/}).waitFor();
    await shot(page,name,"Uploaded-reference login ("+width+" px)");
    const google=page.getByRole("button",{name:/Continue with Google/});
    assert.equal(await google.isDisabled(),true,"Unconfigured Google OAuth must not appear functional");
    await page.getByRole("button",{name:"Forgot password?"}).click();
    await page.getByRole("heading",{name:"Reset your password"}).waitFor();
    await page.getByRole("button",{name:"Back to sign in"}).click();
    await page.getByRole("heading",{name:"Sign in to your account"}).waitFor();
    console.log("LOGIN_RECOVERY_AND_GOOGLE_SAFETY_OK "+name);
    await context.close();
  }
  const context=await contextFor(1440,900,true);const page=await context.newPage();checkErrors(page,"desktop");
  await page.goto(root);await page.locator(".hub-dashboard").waitFor();
  await shot(page,"03-overview-desktop","Overview desktop dark");
  const side=page.locator('aside[aria-label="Primary workspace navigation"]');
  for(const [button,heading,name] of [
    ["My Apps","Ecosystem app launcher","04-my-apps-desktop"],
    ["Team & Access","Workspace & team","05-team-desktop"],
    ["Security","Security & access","06-security-desktop"],
    ["Billing","Plans & billing","07-billing-desktop"],
    ["Platform Admin","V79 Platform Admin","08-admin-desktop"]]){
    await side.getByRole("button",{name:button,exact:true}).click();
    await page.getByRole("heading",{name:heading}).first().waitFor();
    await shot(page,name,button+" desktop");
  }
  await side.getByRole("button",{name:"Overview",exact:true}).click();
  await page.locator(".hub-dashboard").waitFor();
  await page.getByRole("button",{name:"Switch to light mode"}).click();
  await shot(page,"09-overview-light","Overview desktop light");await context.close();
  const tablet=await contextFor(768,1024,true);const tabletPage=await tablet.newPage();checkErrors(tabletPage,"tablet");
  await tabletPage.goto(root);await tabletPage.locator(".hub-dashboard").waitFor();
  await shot(tabletPage,"10-overview-tablet","Overview tablet");await tablet.close();
  const phone=await contextFor(390,844,true);const phonePage=await phone.newPage();checkErrors(phonePage,"mobile");
  await phonePage.goto(root);await phonePage.locator(".hub-dashboard").waitFor();
  await shot(phonePage,"11-overview-mobile","Overview phone");
  await phonePage.locator('nav[aria-label="Mobile workspace navigation"]').getByRole("button",{name:"My Apps"}).click();
  await phonePage.getByRole("heading",{name:"Ecosystem app launcher"}).waitFor();
  await shot(phonePage,"12-my-apps-mobile","My Apps phone");await phone.close();
}finally{await browser.close();}
const htmlHead='<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V79 Hub Isolated Browser Preview</title><style>body{font:16px system-ui;background:#07111f;color:#e9f6ff;margin:0;padding:26px}h1{margin:0 0 8px}p{color:#b7c8d9}.intro{max-width:820px;line-height:1.6}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(380px,100%),1fr));gap:22px;margin-top:24px}figure{margin:0;background:#091728;border:1px solid #284564;border-radius:16px;overflow:hidden}img{width:100%;height:360px;object-fit:cover;object-position:top;display:block}figcaption{padding:14px}a{color:#65c9ff}</style></head><body><h1>V79 Hub · Browser Preview</h1><p class="intro">Actual redesigned React UI with isolated, synthetic API data, captured at desktop, tablet and mobile sizes. This is NOT a production deployment. Click any screenshot for full size.</p><div class="grid">';
const gallery=htmlHead+report.screens.map(s=>'<figure><a href="'+s.file+'"><img alt="'+s.description+'" src="'+s.file+'"></a><figcaption><strong>'+s.description+'</strong> · '+s.width+' px · <a href="'+s.file+'">Full screenshot</a></figcaption></figure>').join("")+'</div></body></html>';
await writeFile(resolve(dir,"index.html"),gallery);
await writeFile(resolve(dir,"browser-report.json"),JSON.stringify(report,null,2));
console.log("SCREENS="+report.screens.length+" PAGE_ERRORS="+report.errors.length);
if(report.errors.length){console.error(JSON.stringify(report.errors,null,2));process.exitCode=1;}
