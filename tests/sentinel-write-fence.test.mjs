import test from "node:test";
import assert from "node:assert/strict";
import {EventEmitter} from "node:events";
import {createSentinelWriteFence, SentinelWriteFenceError} from "../server/sentinel-write-fence.mjs";

function request(method,path) {
  const req={method,path};
  const res=new EventEmitter();
  res.statusCode=200;
  res.headers={};
  res.setHeader=(name,value)=>{res.headers[name.toLowerCase()]=value;};
  res.status=(code)=>{res.statusCode=code;return res;};
  res.json=(body)=>{res.body=body;res.emit("finish");return res;};
  let passed=false;
  const next=()=>{passed=true;};
  return {req,res,next,wasPassed:()=>passed};
}

test("mutation fence permits normal traffic while idle and releases tracked HTTP writes",()=>{
 const f=createSentinelWriteFence();
 const post=request("POST","/api/tickets");
 f.middleware(post.req,post.res,post.next);
 assert.equal(post.wasPassed(),true);
 assert.equal(f.snapshot().activeHttpWrites,1);
 post.res.emit("finish");
 assert.equal(f.snapshot().activeHttpWrites,0);
 post.res.emit("close");
 assert.equal(f.snapshot().activeHttpWrites,0);
});
test("existing non-Sentinel HTTP mutation prevents exclusive cleanup",()=>{
 const f=createSentinelWriteFence();
 const existing=request("POST","/api/other");
 const cleanup=request("POST","/api/admin/sentinel-qa/organizations/clean");
 f.middleware(existing.req,existing.res,existing.next);
 f.middleware(cleanup.req,cleanup.res,cleanup.next);
 assert.throws(()=>f.beginExclusive(cleanup.req),SentinelWriteFenceError);
 existing.res.emit("finish");
 const release=f.beginExclusive(cleanup.req);
 assert.equal(f.snapshot().exclusive,true);
 release();
 cleanup.res.emit("finish");
 assert.equal(f.snapshot().activeHttpWrites,0);
});
test("during Sentinel cleanup other writes blocked, read-only GET allowed",()=>{
 const f=createSentinelWriteFence();
 const cleanup=request("POST","/api/admin/sentinel-qa/organizations/synthetic");
 f.middleware(cleanup.req,cleanup.res,cleanup.next);
 const release=f.beginExclusive(cleanup.req);
 const other=request("POST","/api/other");
 f.middleware(other.req,other.res,other.next);
 assert.equal(other.res.statusCode,423);
 assert.equal(other.wasPassed(),false);
 assert.equal(f.snapshot().activeHttpWrites,1);
 const read=request("GET","/api/health");
 f.middleware(read.req,read.res,read.next);
 assert.equal(read.wasPassed(),true);
 assert.throws(()=>f.beginStoreSave(),SentinelWriteFenceError);
 const finishSave=f.beginStoreSave({sentinel:true});
 assert.equal(f.snapshot().activeStoreWrites,1);
 finishSave();
 release();
 cleanup.res.emit("finish");
 assert.equal(f.snapshot().exclusive,false);
});
test("pending store save prevents acquiring Sentinel exclusive lock",()=>{
 const f=createSentinelWriteFence();
 const finish=f.beginStoreSave();
 const req=request("POST","/api/admin/sentinel-qa/organizations");
 f.middleware(req.req,req.res,req.next);
 assert.throws(()=>f.beginExclusive(req.req),SentinelWriteFenceError);
 finish();
 const release=f.beginExclusive(req.req);
 release();
 req.res.emit("finish");
 assert.deepEqual(f.snapshot(),{activeHttpWrites:0,activeStoreWrites:0,exclusive:false});
});
