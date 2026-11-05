import assert from "node:assert/strict";
import {chromium} from "playwright";
import fs from "node:fs";
const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
fs.mkdirSync("preview-artifacts/specialist-delivery",{recursive:true});
try{
 for(const [label,width,height] of [["desktop",1380,900],["tablet",768,1024],["mobile",390,844]]){
  const page=await browser.newPage({viewport:{width,height}});const errors=[];page.on("pageerror",e=>errors.push(e.message));page.on("dialog",d=>d.accept());
  let jobs=[],accepted=0,proposals=0,integrationsAvailable=true;
  const task={id:"task-synthetic",title:"Review customer support handoff",status:"open",system:"tiquet",taskDigest:"a".repeat(64)};
  const specialists=[{id:"coo",name:"COO",skillSha:"b".repeat(40)},{id:"customer-service",name:"Customer Service",skillSha:"c".repeat(40)}];
  await page.route("**/api/**",async route=>{
   const url=new URL(route.request().url()),path=url.pathname.replace(/\/$/,""),method=route.request().method();
   const json=(body,status=200)=>route.fulfill({status,contentType:"application/json",body:JSON.stringify(body)});
   if(path==="/api/auth/me")return json({user:{id:"synthetic-owner",username:"test",fullName:"Synthetic Owner",role:"admin",platformOperator:true,ownerAgent:true,workspaceOwner:true,permissions:["overview","team","security","billing","assistant","admin"]},organization:{name:"Synthetic Review Workspace"}});
   if(path==='/api/agent/specialist-integrations')return integrationsAvailable?json({kind:'specialist-integration-report',mode:'read-only',collectedAt:new Date().toISOString(),receiptSha256:'f'.repeat(64),roles:['ceo','coo','finance','strategy','marketing','customer-service','technical-security','sales'].map(id=>({id,name:'V79 '+id,status:'available',systems:['tiquet'],skillSha:'a'.repeat(40),limitations:['Synthetic aggregate data only.'],sources:[{system:'tiquet',name:'Tiquet',state:'available',reportedAt:new Date().toISOString(),metricKeys:['jobs']}]}))}):json({error:'Verified sources unavailable'},502);
   if(path==="/api/ecosystem/apps"||path==="/api/users")return json([]);
   if(path==="/api/agent/work-actions"&&method==="GET")return json({mode:"owner-approved-actions",enabled:true,paused:false,specialistReviewsEnabled:true,specialists,jobs,tasks:[task]});
   if(path==="/api/agent/work-actions"&&method==="POST"){
    const input=route.request().postDataJSON();assert.equal(input.operation,"run_specialist_review");assert.equal(input.payload.specialist,"customer-service");assert.equal(input.payload.taskId,task.id);assert.equal(input.payload.taskDigest,task.taskDigest);proposals++;
    jobs=[{...input,id:"review-synthetic",revision:1,digest:"d".repeat(64),status:"pending",approval:null,result:null}];return json({job:jobs[0]},201);
   }
   if(path.endsWith("/decision")&&method==="POST"){
    const input=route.request().postDataJSON();assert.equal(input.digest,"d".repeat(64));jobs[0].revision=4;jobs[0].status="succeeded";jobs[0].approval={expiresAt:new Date(Date.now()+3600000).toISOString()};jobs[0].result={kind:"specialist-review-draft",output:"DRAFT ADVICE — Review the support handoff and identify missing evidence. No action has been performed.",outputSha256:"e".repeat(64),ownerAccepted:false,model:"synthetic-local-model"};return json({job:jobs[0]});
   }
   if(path.endsWith("/accept-review")&&method==="POST"){
    const input=route.request().postDataJSON();assert.equal(input.outputSha256,"e".repeat(64));assert.equal(input.expectedRevision,4);accepted++;jobs[0].result.ownerAccepted=true;task.status="completed";return json({job:jobs[0]});
   }
   return json({error:"Synthetic unavailable source"},404);
  });
  await page.goto("http://127.0.0.1:4178/?view=assistant",{waitUntil:"domcontentloaded"});
  await page.getByRole("button",{name:"Tasks & approvals",exact:true}).click();
  const delivery=page.getByRole("region",{name:"Task delivery",exact:true});await delivery.getByText(task.title,{exact:true}).waitFor();
  await page.selectOption("#specialist-task-synthetic","customer-service");await delivery.getByRole("button",{name:"Queue specialist review"}).click();
  await page.getByRole("button",{name:"Approve exact action",exact:true}).click();
  await page.getByRole("button",{name:"All (1)",exact:true}).click();
  await page.getByRole("heading",{name:"Saved specialist result"}).waitFor();
  assert.equal(task.status,"open");await page.screenshot({path:"preview-artifacts/specialist-delivery/"+label+"-draft.png",fullPage:true});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),"No horizontal page overflow");
  await page.getByRole("button",{name:"Accept advisory review as task deliverable"}).click();
  await delivery.getByText(/Deliverable accepted/).waitFor();assert.equal(accepted,1);assert.equal(proposals,1);assert.deepEqual(errors,[]);
  await page.screenshot({path:"preview-artifacts/specialist-delivery/"+label+"-accepted.png",fullPage:true});
  await page.getByRole('button',{name:'Tools & reports',exact:true}).click();await page.getByRole('button',{name:'Specialist integrations',exact:true}).click();
  const integrations=page.getByRole('region',{name:'Specialist integrations',exact:true});await integrations.getByText(/8 of 8 specialists/).waitFor();
  assert.equal(await integrations.getByRole('article').count(),8);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  await page.screenshot({path:'preview-artifacts/specialist-delivery/'+label+'-integrations.png',fullPage:true});
  integrationsAvailable=false;await integrations.getByRole('button',{name:'Refresh sources',exact:true}).click();await integrations.getByRole('alert').waitFor();assert.equal(await integrations.getByRole('article').count(),0);assert.deepEqual(errors,[]);await page.close();
 }
}finally{await browser.close();}
console.log("SPECIALIST_DELIVERY_SYNTHETIC_BROWSER=PASS");
