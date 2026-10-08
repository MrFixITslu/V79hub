import test from "node:test";
import assert from "node:assert/strict";
import { createResendTransactionalSender, validateResendSenderConfig } from "../server/resend-transactional.mjs";

const options={
  apiKey:"re_test_not_real_sending_key_123456789",
  from:"V79 Digital <notifications@v79sl.com>",
  replyTo:"vision79slu@gmail.com",
  hubUrl:"https://hub.v79sl.com",
};
const exampleReminder={key:"customer-01:2026-11-01T00:00:00Z:one_day",
  kind:"one_day",email:"trial-owner@example.test",trialEndsAt:"2026-11-15T00:00:00Z"};
test("rejects unverified sender domain, invalid recovery links and secrets",async()=>{
  for(const from of ["V79 Digital <noreply@example.com>","notifications@other.com",
                     "V79 <notifications@v79sl.com>\nBcc: malicious@example.test",
                     "notifications@v79sl.com>"]){
    assert.throws(()=>validateResendSenderConfig({...options,from}));
  }
  assert.throws(()=>validateResendSenderConfig({...options,apiKey:""}));
  assert.throws(()=>validateResendSenderConfig({...options,hubUrl:"http://hub.v79sl.com"}));
  assert.throws(()=>validateResendSenderConfig({...options,hubUrl:"https://email-links.v79sl.com"}));
});
test("mock provider receives proper password reset payload with canonical URL",async()=>{
  const sent=[];
  const sender=createResendTransactionalSender({...options,
    fetchImpl:async (url,request)=>{
      sent.push({url,request});return new Response(JSON.stringify({id:"staging-only"}),{status:200});
    }});
  const link="https://hub.v79sl.com/?reset=opaque-staging-only";
  assert.equal(await sender.sendPasswordReset("test-recipient@example.test",link),true);
  assert.equal(sent.length,1);
  assert.equal(sent[0].url,"https://api.resend.com/emails");
  assert.equal(sent[0].request.headers.authorization,"Bearer "+options.apiKey);
  const payload=JSON.parse(sent[0].request.body);
  assert.deepEqual(payload.to,["test-recipient@example.test"]);
  assert.equal(payload.from,options.from);
  assert.equal(payload.reply_to,options.replyTo);
  assert.match(payload.text,/within 30 minutes/);
  assert.ok(payload.text.includes(link));
  assert.ok(!sent[0].request.body.includes(options.apiKey));
  await assert.rejects(()=>sender.sendPasswordReset("test-recipient@example.test",
    "https://evil.example.test/?reset=token"),/canonical/);
  assert.equal(sent.length,1);
});
test("trial reminder provider idempotency is stable for repeated logical reminder",async()=>{
  const captured=[];
  const sender=createResendTransactionalSender({...options,
    fetchImpl:async (_url,request)=>{
      captured.push(request);
      return new Response(JSON.stringify({id:"mock-id"}),{status:200});
    }});
  assert.equal(await sender.sendTrialReminder(exampleReminder),true);
  assert.equal(await sender.sendTrialReminder(exampleReminder),true);
  const a=captured[0].headers["Idempotency-Key"];
  const b=captured[1].headers["Idempotency-Key"];
  assert.equal(a,b);
  assert.match(a,/^v79trial-[a-f0-9]{64}$/);
  const payload=JSON.parse(captured[0].body);
  assert.match(payload.subject,/ends tomorrow/i);
  assert.ok(payload.text.includes("https://hub.v79sl.com"));
  assert.ok(!captured[0].body.includes(exampleReminder.key));
});
test("different reminder stage receives separate idempotency key",async()=>{
 const captured=[];
 const sender=createResendTransactionalSender({...options,
   fetchImpl:async(_url,request)=>{
     captured.push(request.headers["Idempotency-Key"]);
     return new Response(null,{status:202});
   }});
 assert.equal(await sender.sendTrialReminder(exampleReminder),true);
 const next={...exampleReminder,kind:"expired",
   key:"customer-01:2026-11-01T00:00:00Z:expired"};
 assert.equal(await sender.sendTrialReminder(next),true);
 assert.notEqual(captured[0],captured[1]);
});
test("provider rejection fails closed and unexpected outage propagates to retry coordinator",async()=>{
 const reject=createResendTransactionalSender({...options,
   fetchImpl:async()=>new Response(JSON.stringify({error:"forbidden"}),{status:403})});
 assert.equal(await reject.sendTrialReminder(exampleReminder),false);
 const offline=createResendTransactionalSender({...options,
   fetchImpl:async()=>{throw Error("mock transport unavailable")}});
 await assert.rejects(()=>offline.sendTrialReminder(exampleReminder),/unavailable/);
});
test("invalid trial reminder metadata and recipient never go to provider",async()=>{
 let calls=0;
 const sender=createResendTransactionalSender({...options,
   fetchImpl:async()=>{calls++;return new Response(null,{status:200})}});
 await assert.rejects(()=>sender.sendTrialReminder({...exampleReminder,kind:"unknown"}));
 await assert.rejects(()=>sender.sendTrialReminder({...exampleReminder,trialEndsAt:"bad"}));
 await assert.rejects(()=>sender.sendTrialReminder({...exampleReminder,email:"bad-address"}));
 assert.equal(calls,0);
});

test("diagnostic sends exactly one neutral message with stable dedupe key",async()=>{
  const captured=[];
  const sender=createResendTransactionalSender({...options,fetchImpl:async(_url,request)=>{
    captured.push(request);return new Response(null,{status:200});
  }});
  assert.equal(await sender.sendDiagnostic("vision79slu@gmail.com"),true);
  assert.equal(captured.length,1);
  const payload=JSON.parse(captured[0].body);
  assert.match(payload.subject,/Isolated Resend Integration Check/);
  assert.match(payload.text,/No account access, subscription, or trial status was changed/);
  assert.equal(captured[0].headers["Idempotency-Key"],"v79-staging-resend-diagnostic-20261008");
  assert.doesNotMatch(payload.text,/reset=/);
});
