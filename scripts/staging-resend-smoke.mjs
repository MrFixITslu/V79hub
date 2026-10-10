import { readFileSync, statSync } from "node:fs";
import { createResendTransactionalSender } from "../server/resend-transactional.mjs";

// Standalone one-off diagnostic. Never starts the Hub webserver,
// never loads or writes production Hub state, and never sends to customers.
const allowedInbox="vision79slu@gmail.com";
if(process.env.V79_STAGING_RESEND_SMOKE!=="I_APPROVE_ONE_TEST_EMAIL" ||
  process.env.NODE_ENV==="production") {
  console.error("STAGING SAFETY GUARD: explicit test-send approval missing");
  process.exit(2);
}
const inbox=process.argv.find(a=>a.startsWith("--to="))?.slice(5);
if(inbox!==allowedInbox) {
  console.error("STAGING SAFETY GUARD: only the designated test inbox is allowed");
  process.exit(2);
}
const keyFile="/home/firelion/v79-staging-v79-01-20261008/secrets/resend-staging.key";
const stat=statSync(keyFile);
if ((stat.mode&0o077)!==0 || !stat.isFile()) {
  console.error("STAGING SAFETY GUARD: secret file must be private");
  process.exit(2);
}
const apiKey=readFileSync(keyFile,"utf8").trim();
const sender=createResendTransactionalSender({
  apiKey,
  from:"V79 Digital <notifications@v79sl.com>",
  replyTo:"vision79slu@gmail.com",
  hubUrl:"https://hub.v79sl.com",
});
try {
  const deliveredToProvider=await sender.sendDiagnostic(inbox);
  console.log(JSON.stringify({testOnly:true,providerAccepted:deliveredToProvider,
    recipient:inbox,productionChanged:false}));
  if(!deliveredToProvider)process.exitCode=1;
} catch {
  console.error("STAGING EMAIL TEST FAILED: delivery provider unavailable or rejected request");
  process.exitCode=1;
}
