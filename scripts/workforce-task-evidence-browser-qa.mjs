import assert from "node:assert/strict";
import {chromium} from "playwright";
import fs from "node:fs";
const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
fs.mkdirSync("preview-artifacts/task-evidence",{recursive:true});
try{
 for(const [label,width,height] of [["desktop",1380,900],["tablet",768,1024],["mobile",390,844]]){
 const page=await browser.newPage({viewport:{width,height}}),errors=[];page.on("pageerror",e=>errors.push(e.message));page.on("dialog",d=>d.accept());
 const task={id:"synthetic-task",title:"Review commercial launch evidence",detail:"Synthetic task. Prepare the evidence register, identify unresolved merchant verification and customer acceptance, and save a draft for owner review.",status:"open",system:"hub",taskDigest:"a".repeat(64),reconciliationOptions:{creationTest:false,duplicateTaskIds:[]}};
 const test={id:"synthetic-test",title:"G2 supervised acceptance test",detail:"Record this acceptance task only.",status:"open",system:"hub",taskDigest:"b".repeat(64),reconciliationOptions:{creationTest:true,duplicateTaskIds:[]}};
 let stale=true,saved=0,accepted=0,reconciled=0;
 await page.route("**/api/**",async route=>{
 const p=new URL(route.request().url()).pathname.replace(/\/$/,""),m=route.request().method(),json=(body,status=200)=>route.fulfill({status,contentType:"application/json",body:JSON.stringify(body)});
 if(p==="/api/auth/me")return json({user:{id:"synthetic-owner",username:"test",fullName:"Synthetic Owner",role:"admin",platformOperator:true,ownerAgent:true,workspaceOwner:true,permissions:["overview","team","security","billing","assistant","admin"]},organization:{name:"Synthetic Workspace"}});
 if(p==="/api/ecosystem/apps"||p==="/api/users")return json([]);
 if(p==="/api/agent/work-actions"&&m==="GET")return json({enabled:true,paused:false,mode:"owner-approved-actions",specialistReviewsEnabled:true,specialists:[{id:"coo",name:"COO",skillSha:"c".repeat(40)}],jobs:[],tasks:[task,test]});
 if(p.endsWith("/deliverable")&&m==="POST"){const b=route.request().postDataJSON();assert.equal(b.taskDigest,task.taskDigest);saved++;task.deliverables=[{...b,id:"deliverable-1",sha256:"d".repeat(64),accepted:false,createdAt:new Date().toISOString()}];task.currentDeliverableId="deliverable-1";return json({task},201);}
 if(p.endsWith("/accept-deliverable")&&m==="POST"){if(stale){stale=false;return json({error:"A fresh owner MFA session is required."},403);}const b=route.request().postDataJSON();assert.equal(b.sha256,"d".repeat(64));accepted++;task.status="completed";task.deliverables[0].accepted=true;task.completion={kind:"owner-accepted-deliverable",reason:"Exact saved evidence accepted."};return json({task});}
 if(p.endsWith("/reconcile")&&m==="POST"){const b=route.request().postDataJSON();assert.equal(b.decision,"verify_creation_test");assert.equal(b.taskDigest,test.taskDigest);reconciled++;test.status="completed";test.completion={kind:"verified-task-creation-test",reason:b.reason};return json({task:test});}
 return json({error:"Synthetic unavailable source"},404);
 });
 await page.goto("http://127.0.0.1:4178/?view=assistant",{waitUntil:"domcontentloaded"});await page.getByRole("button",{name:"Tasks & approvals",exact:true}).click();
 const delivery=page.getByRole("region",{name:"Task delivery",exact:true});await delivery.getByText(task.title,{exact:true}).waitFor();
 const card=delivery.locator("div").filter({has:page.getByRole("heading",{name:task.title,exact:true})}).last();
 await delivery.getByText("Evidence and closure",{exact:true}).nth(0).click();
 const form=page.getByRole("form",{name:"Record deliverable for "+task.title});
 await form.getByLabel("Deliverable title",{exact:true}).fill("Launch evidence register for owner review");
 await form.getByLabel("Result and verification",{exact:true}).fill("Prepared the evidence register. Merchant verification and customer acceptance remain unresolved. This synthetic result does not authorise payments, deployments or external messages.");
 await form.getByLabel("Evidence links · one per line",{exact:true}).fill("https://github.com/MrFixITslu/V79hub/issues/113");
 await form.getByRole("button",{name:"Save deliverable draft",exact:true}).click();
 await page.getByText("Saved draft · awaiting owner review. Saving evidence does not complete the task.",{exact:true}).waitFor();assert.equal(saved,1);assert.equal(task.status,"open");
 await page.getByRole("button",{name:"Accept saved deliverable",exact:true}).click();await page.getByText("A fresh owner MFA session is required.",{exact:true}).waitFor();assert.equal(task.status,"open");assert.equal(accepted,0);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),"No horizontal overflow");await page.screenshot({path:"preview-artifacts/task-evidence/"+label+"-draft.png",fullPage:true});
 await page.getByRole("button",{name:"Refresh status",exact:true}).click();await delivery.getByText("Evidence and closure",{exact:true}).nth(0).click();await page.getByRole("button",{name:"Accept saved deliverable",exact:true}).click();await page.getByText("Owner accepted this saved deliverable.",{exact:true}).waitFor();assert.equal(accepted,1);
 await delivery.getByText("Evidence and closure",{exact:true}).nth(1).click();
 const reconcile=page.getByRole("form",{name:"Reconcile "+test.title});
 await reconcile.getByLabel("Reason and evidence",{exact:true}).fill("Verified original approved create_work_item job and recorded task identity in the synthetic fixture.");
 await reconcile.getByRole("button",{name:"Apply recorded decision",exact:true}).click();assert.equal(reconciled,1);await page.getByText(/2 completed/).waitFor();
 assert.deepEqual(errors,[]);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));await page.screenshot({path:"preview-artifacts/task-evidence/"+label+"-completed.png",fullPage:true});await page.close();
 }
}finally{await browser.close();}
console.log("TASK_EVIDENCE_SYNTHETIC_BROWSER=PASS");
