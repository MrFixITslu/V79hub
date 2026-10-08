import test from "node:test";
import assert from "node:assert/strict";
import {createResendTransactionalSender} from "../server/resend-transactional.mjs";

const config={apiKey:"re_test_not_real_sending_key_123456789",
  from:"V79 Digital <notifications@v79sl.com>",
  replyTo:"vision79slu@gmail.com",hubUrl:"https://hub.v79sl.com"};
const expiresAt="2026-11-07T18:00:00.000Z";
const invitationId="a2424252-6ae4-4a78-b210-dc1d4e870d24";

test("authenticated owner and team invitation transport has consistent recipient and provider deduplication",async()=>{
  const calls=[];
  const sender=createResendTransactionalSender({...config,fetchImpl:async(url,options)=>{
    calls.push({url,options});return new Response(null,{status:200});
  }});
  for(const kind of ["owner","team"]){
    const inviteUrl="https://hub.v79sl.com/#"+(kind==="owner"?"invite=":"teamInvite=")+"test-invitation-link-value-123456789";
    assert.equal(await sender.sendInvitation({
      to:"test-recipient@example.test",inviteUrl,invitationId,kind,expiresAt}),true);
    const last=calls.at(-1);
    const message=JSON.parse(last.options.body);
    assert.equal(message.to[0],"test-recipient@example.test");
    assert.match(message.subject,/invitation/);
    assert.ok(message.text.includes(inviteUrl));
    assert.match(last.options.headers["Idempotency-Key"],/^v79invite-[a-f0-9]{64}$/);
    assert.ok(!last.options.headers["Idempotency-Key"].includes("test-invitation-link-value"));
  }
  assert.notEqual(calls[0].options.headers["Idempotency-Key"],
    calls[1].options.headers["Idempotency-Key"]);
});
test("noncanonical invitation links and invalid identifiers never reach the sender",async()=>{
  let calls=0;
  const sender=createResendTransactionalSender({...config,fetchImpl:async()=>{
    calls++;return new Response(null,{status:200});
  }});
  const valid="https://hub.v79sl.com/#invite=test-invitation-link-value-123456789";
  await assert.rejects(()=>sender.sendInvitation({
    to:"test-recipient@example.test",inviteUrl:"https://example.invalid/#invite=test-invitation-link-value-123456789",
    invitationId,kind:"owner",expiresAt}),/Invalid Hub/);
  await assert.rejects(()=>sender.sendInvitation({
    to:"test-recipient@example.test",inviteUrl:valid,
    invitationId:"wrong",kind:"owner",expiresAt}),/Invalid invitation/);
  await assert.rejects(()=>sender.sendInvitation({
    to:"test-recipient@example.test",inviteUrl:valid,
    invitationId,kind:"owner",expiresAt:"bad-date"}),/Invalid Hub/);
  assert.equal(calls,0);
});
