import {chromium} from 'playwright';
import {strict as assert} from 'node:assert';
import {mkdir,writeFile} from 'node:fs/promises';
const base='http://127.0.0.1:4178';
const dir='preview-artifacts/studio-approvals';
await mkdir(dir,{recursive:true});
const fake={id:'synthetic-owner',role:'admin',username:'Synthetic Owner',fullName:'Synthetic Team Owner',
 platformOperator:false,workspaceOwner:true,ownerAgent:false,
 permissions:['overview','connections','team','security','billing','marketing-approvals'],appIds:['app-marketing']};
const reviews=[{packageId:'81ebfd64-d6cd-4df2-a198-5fc1fba42622',campaignId:'campaign-synthetic',
 creatorUserId:'creator-synthetic',exactDigest:'f'.repeat(64),
 caption:'Synthetic Caribbean document organisation. No real service claims.',
 channel:'facebook',scheduledAt:'2026-11-08T13:00:00.000Z',
 accountId:'synthetic-personal-account',providerAccountId:'synthetic-facebook-page',
 assets:[{id:'46f97b4c-815a-492b-aaed-ed7335a0db73',sha256:'e'.repeat(64),
  kind:'image',mime:'image/png'}]}];
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
let attempted=0;
const results=[];
try{
 for(const [width,height,label] of [[1440,900,'desktop'],[390,844,'mobile']]){
  const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:1,isMobile:width<500,
   hasTouch:width<500,reducedMotion:'reduce'});
  await context.addInitScript(()=>{
   window.WebSocket=class {close(){}send(){}addEventListener(){}};
  });
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.origin!==base)return route.abort('blockedbyclient');
    if(route.request().method()==='POST'&&url.pathname==='/api/studio/marketing/approve'){
      attempted++;return route.fulfill({status:503,contentType:'application/json',body:'{"error":"Disabled"}'});
    }
    const api={
      '/api/auth/me':{user:fake,organization:{name:'Synthetic Workspace'}},
      '/api/ecosystem/apps':[],
      '/api/studio/marketing/inbox':{packages:reviews,approvalEnabled:false},
      '/api/studio/marketing/history':{deliveries:[]},
      '/api/dashboard/summary':{generatedAt:'2026-10-31T00:00:00Z',apps:{}},
      '/api/connections/status':{apps:{}},
    };
    if(url.pathname.startsWith('/api/'))
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(api[url.pathname]||{})});
    return route.continue();
  });
  const page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/?view=marketing-approvals',{waitUntil:'domcontentloaded'});
  await page.getByRole('heading',{name:/Review before anything goes live/i}).waitFor({timeout:25000});
  await page.getByText('Synthetic Caribbean document organisation. No real service claims.').waitFor();
  await page.getByText(/Publishing remains disabled/i).waitFor();
  await page.getByRole('button',{name:/Review exact publishing consent/}).click();
  await page.getByRole('checkbox',{name:/I authorise this exact reviewed package/}).check();
  assert.equal(await page.getByRole('button',{name:/Approve with fresh Hub MFA/}).isDisabled(),true);
  assert.equal(attempted,0);
  const dimensions=await page.evaluate(()=>({
    scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
  assert(dimensions.scroll<=dimensions.client,'Mobile or desktop page overflows');
  assert.deepEqual(errors,[],'No browser runtime errors');
  await page.screenshot({path:dir+'/'+label+'.png',fullPage:true,animations:'disabled'});
  results.push({width,label,dimensions,locked:true,approvalRequests:attempted});
  await context.close();
 }
}finally{await browser.close();}
await writeFile(dir+'/results.json',JSON.stringify(results,null,2));
console.log('STUDIO_HUB_APPROVAL_BROWSER='+JSON.stringify(results));
