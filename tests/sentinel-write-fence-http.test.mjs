import test from "node:test";
import assert from "node:assert/strict";
import express from "express";
import {createServer,request} from "node:http";
import {EventEmitter} from "node:events";
import {createSentinelWriteFence} from "../server/sentinel-write-fence.mjs";

const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const tick=()=>new Promise(r=>setImmediate(r));
async function until(check) {
 for(let n=0;n<200;n++){if(check())return;await new Promise(r=>setTimeout(r,5));}
 assert.fail("condition did not settle");
}
async function harness(t) {
 const app=express(),fence=createSentinelWriteFence();
 app.use(fence.middleware);
 fence.installHandlerTracking(app);
 const server=createServer(app);
 await new Promise(r=>server.listen(0,"127.0.0.1",r));
 t.after(async()=>{server.closeAllConnections();await new Promise(r=>server.close(r));});
 const url="http://127.0.0.1:"+server.address().port;
 return {app,fence,url};
}
function disconnected(url,method,path) {
 const req=request(url+path,{method});
 req.on("error",()=>{});
 req.end();
 return req;
}
for(const operation of ["provision","membership"]) {
 test("disconnect keeps deferred "+operation+" tracked through completion and subsequent clone",async t=>{
  const {app,fence,url}=await harness(t);
  const entered=deferred(),upstream=deferred(),settled=deferred(),commit=deferred(),committing=deferred();
  let state={memberships:[{id:"existing",role:"staff"}],mappings:[],preserved:"customer"};
  let durable=structuredClone(state),external=null;
  app[operation==="provision"?"get":"put"](operation==="provision"?"/api/apps/pos/launch":"/api/users/existing",async(req,res)=>{
   const member=state.memberships[0];
   entered.resolve();await upstream.promise;
   external=operation;
   if(operation==="provision")state.mappings.push({id:"existing-app",tenant:"synthetic-upstream"});
   else member.role="manager";
   const release=fence.beginStoreSave();
   try {durable=structuredClone(state);}finally{release();}
   res.json({ok:true});settled.resolve();
  });
  app.post("/api/admin/sentinel-qa/organizations",async(req,res)=>{
   let release;
   try {release=fence.beginExclusive(req);}catch{return res.status(409).end();}
   try {
    const copy=structuredClone(state);
    committing.resolve();await commit.promise;
    copy.qa=true;state=copy;durable=structuredClone(copy);res.json({ok:true});
   }finally{release();}
  });
  const method=operation==="provision"?"GET":"PUT";
  const pending=disconnected(url,method,operation==="provision"?"/api/apps/pos/launch":"/api/users/existing");
  await entered.promise;
  pending.destroy();
  await tick();
  assert.equal((await fetch(url+"/api/admin/sentinel-qa/organizations",{method:"POST"})).status,409);
  assert.equal(external,null);
  // An attempted maintenance window cannot replace the captured membership.
  upstream.resolve();await settled.promise;
  await until(()=>fence.snapshot().activeHttpWrites===0);
  const expected=structuredClone(state);
  assert.deepEqual(durable,expected);
  assert.equal(external,operation);
  if(operation==="membership")assert.equal(state.memberships[0].role,"manager");
  else assert.equal(state.mappings.length,1);
  const maintenance=fetch(url+"/api/admin/sentinel-qa/organizations",{method:"POST"});
  await committing.promise;
  assert.equal((await fetch(url+(operation==="provision"?"/api/apps/pos/launch":"/api/users/existing"),{method})).status,423);
  commit.resolve();assert.equal((await maintenance).status,200);
  assert.deepEqual(state,{...expected,qa:true});
  assert.deepEqual(durable,state);
  assert.equal(state.preserved,"customer");
 });
}

test("response finish keeps an asynchronous handler tail tracked",async t=>{
 const {app,fence,url}=await harness(t),tail=deferred(),entered=deferred();
 app.post("/write",async(req,res)=>{res.end("done");entered.resolve();await tail.promise;});
 app.post("/api/admin/sentinel-qa/organizations",(req,res)=>{
  try{const release=fence.beginExclusive(req);release();res.sendStatus(200);}catch{res.sendStatus(409);}
 });
 assert.equal((await fetch(url+"/write",{method:"POST"})).status,200);await entered.promise;
 assert.equal((await fetch(url+"/api/admin/sentinel-qa/organizations",{method:"POST"})).status,409);
 tail.resolve();await until(()=>fence.snapshot().activeHttpWrites===0);
 assert.equal((await fetch(url+"/api/admin/sentinel-qa/organizations",{method:"POST"})).status,200);
});

test("aborted body parsing retires request without reaching a writable handler",async t=>{
 const {app,fence,url}=await harness(t);
 app.use(express.json());let writes=0;
 app.post("/write",(req,res)=>{writes++;res.end();});
 app.use((err,req,res,next)=>{assert.equal(err.type,"request.aborted");res.end();});
 const pending=request(url+"/write",{method:"POST",headers:{"Content-Type":"application/json","Content-Length":"100"}});
 pending.on("error",()=>{});pending.write('{"partial":');
 await until(()=>fence.snapshot().activeHttpWrites===1);
 pending.destroy();
 await until(()=>fence.snapshot().activeHttpWrites===0);
 assert.equal(writes,0);
});

test("callback dispatch after transport end is suppressed and cannot restart a write",()=>{
 const fence=createSentinelWriteFence(),req={method:"POST",path:"/write"},res=new EventEmitter();
 fence.middleware(req,res,()=>{});
 let resume,writes=0;
 fence.trackHandler((_req,_res,next)=>{resume=next;})(req,res,()=>{writes++;});
 res.emit("close");resume();
 assert.equal(writes,0);
 assert.equal(fence.snapshot().activeHttpWrites,0);
});

test("wrapped nested handlers preserve route skips, settings and error dispatch",async t=>{
 const {app,fence,url}=await harness(t);
 app.set("fixture-setting","retained");assert.equal(app.get("fixture-setting"),"retained");
 app.post("/skip",[(req,res,next)=>next("route"),()=>assert.fail("skipped route ran")]);
 app.post("/skip",(req,res)=>res.send("next route"));
 assert.equal(await (await fetch(url+"/skip",{method:"POST"})).text(),"next route");
 app.post("/error",[[async()=>{throw new Error("fixture");}]]);
 let errors=0;
 app.use((err,req,res,next)=>{errors++;res.status(500).send(err.message);});
 assert.equal(await (await fetch(url+"/error",{method:"POST"})).text(),"fixture");
 assert.equal(errors,1);
 const tail=deferred();
 app.post("/next-tail",async(req,res,next)=>{next();await tail.promise;throw new Error("after next");});
 app.post("/next-tail",(req,res)=>res.end("ok"));
 assert.equal((await fetch(url+"/next-tail",{method:"POST"})).status,200);
 tail.resolve();await until(()=>fence.snapshot().activeHttpWrites===0);
 assert.equal(errors,1);
});
