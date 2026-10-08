import test from "node:test";
import assert from "node:assert/strict";
import {analyzeResendDns,queryResendDns} from "../scripts/resend-dns-preflight.mjs";

const base={
 domain:"v79sl.com",nameservers:["ns1.domain.com."],rootTxt:["google-site-verification=public"],
 dmarcTxt:[],returnPathTxt:[],returnPathMx:[],dkimTxt:[],dkimHost:null,
};
test("preconfiguration reports missing DNS without inventing verification",()=>{
 const r=analyzeResendDns(base);
 assert.equal(r.verified,false);
 assert.equal(r.checks.returnPathSpfPresent,false);
 assert.equal(r.checks.dmarcPresent,false);
 assert.equal(r.checks.dkimPresent,null);
 assert.equal(r.checks.nameservers[0],"ns1.domain.com");
});
test("the presence of required DNS is not mistaken for verified Resend account",()=>{
 const r=analyzeResendDns({...base,rootTxt:["v=spf1 include:provider ~all"],dmarcTxt:["v=DMARC1; p=none"],
  returnPathTxt:["v=spf1 include:amazonses.com ~all"],returnPathMx:[{exchange:"feedback-smtp.us-east-1.amazonses.com",priority:10}],
  dkimTxt:["v=DKIM1; k=rsa; p=publickey"],dkimHost:"resend._domainkey.v79sl.com"});
 assert.equal(r.checks.dmarcPresent,true);
 assert.equal(r.checks.returnPathSpfPresent,true);
 assert.equal(r.checks.returnPathMxPresent,true);
 assert.equal(r.checks.dkimPresent,true);
 assert.equal(r.verified,false);
});
test("duplicate SPF records are reported",()=>{
 const r=analyzeResendDns({...base,rootTxt:["v=spf1 include:a ~all","v=spf1 include:b ~all"]});
 assert.equal(r.checks.rootSpfRecords,2);
 assert.match(r.warnings.join(","),/Duplicate SPF/);
});
test("DNS preflight denies arbitrary hostnames",async()=>{
 await assert.rejects(()=>queryResendDns({returnPath:"arbitrary-example.com"}),/Only public/);
 await assert.rejects(()=>queryResendDns({domain:"example.com"}),/Only public/);
});

test("a reserved Hub application hostname pointing to Resend tracking is a critical configuration conflict",()=>{
 const r=analyzeResendDns({...base,appCnames:["links2.resend-dns.com."]});
 assert.equal(r.checks.hubApplicationDnsConflictsWithEmailTracking,true);
 assert.match(r.warnings.join(" "),/CRITICAL.*Restore the application origin/);
});
test("other legitimate application DNS does not generate tracking warning",()=>{
 const r=analyzeResendDns({...base,appCnames:[]});
 assert.equal(r.checks.hubApplicationDnsConflictsWithEmailTracking,false);
});
