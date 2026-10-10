import test from "node:test";
import assert from "node:assert/strict";
import { analyzeAuthoritativeDns, parseAnswer } from "../scripts/resend-authoritative-dns.mjs";
const ns=["ns1.domain.com","ns2.domain.com"];
const good={hubA:["199.223.249.193"],hubCname:[],rsendCname:["rsend.forge.rmta.net."],
  sendCname:["send.forge.rmta.net."],dkimTxt:['"p=examplepublickey"'],dmarcTxt:['"v=DMARC1; p=none;"']};
const sample=()=>Object.fromEntries(ns.map(n=>[n,structuredClone(good)]));
test("safe authoritative A records and matched Resend DNS permit further verification",()=>{
  const r=analyzeAuthoritativeDns(sample());
  assert.equal(r.hubDnsSafe,true);
  assert.equal(r.readyForResendVerification,true);
  assert.deepEqual(r.problems,[]);
});
test("mixed A/CNAME on one nameserver is explicitly unsafe despite correct A",()=>{
  const rows=sample();
  rows[ns[0]].hubCname=["links2.resend-dns.com."];
  const r=analyzeAuthoritativeDns(rows);
  assert.equal(r.hubDnsSafe,false);
  assert.equal(r.checks[ns[0]].hubAValid,true);
  assert.ok(r.problems.includes(ns[0]+":hub_CNAME_conflicts_with_application"));
});
test("one stale authoritative server prevents Hub recovery readiness",()=>{
 const rows=sample();
 rows[ns[1]].hubA=[];
 rows[ns[1]].hubCname=["links2.resend-dns.com."];
 const r=analyzeAuthoritativeDns(rows);
 assert.equal(r.hubDnsSafe,false);
 assert.equal(r.readyForResendVerification,true);
 assert.equal(r.problems.filter(x=>x.includes(":hub_")).length,2);
});
test("wrong Resend CNAME on either authoritative server is detected",()=>{
 const rows=sample();
 rows[ns[0]].rsendCname=["wrong.example.net."];
 rows[ns[1]].sendCname=[];
 const r=analyzeAuthoritativeDns(rows);
 assert.equal(r.hubDnsSafe,true);
 assert.equal(r.readyForResendVerification,false);
 assert.ok(r.problems.includes(ns[0]+":rsend_CNAME_missing_or_wrong"));
 assert.ok(r.problems.includes(ns[1]+":send_CNAME_missing_or_wrong"));
});
test("absent DKIM and DMARC cannot be reported as ready",()=>{
 const rows=sample();
 rows[ns[1]].dkimTxt=[];
 rows[ns[0]].dmarcTxt=[];
 const r=analyzeAuthoritativeDns(rows);
 assert.equal(r.readyForResendVerification,false);
});

test("unexpected CNAME in A lookup response is not ignored",()=>{
  const response="hub.v79sl.com. 14400 IN CNAME links2.resend-dns.com.\n";
  assert.deepEqual(parseAnswer(response,"A","hub.v79sl.com"),[]);
  assert.deepEqual(parseAnswer(response,"CNAME","hub.v79sl.com"),["links2.resend-dns.com."]);
});
