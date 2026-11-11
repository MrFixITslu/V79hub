import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

// This is the signed-off original Hub server.ts blob before V2. Never
// change it to match an arbitrary new build: any unrelated modifications
// must be audited separately, not hidden inside the V2 integration.
const ACCEPTED_SERVER_BLOB = "6784def9a38d018f87aa85e0d73ec10d65972daf";
const V2_IMPORTS = 'import { Pool } from "pg";\n'+
  'import { createEcosystemEventInbox, createTiquetEventHandler, createWebsiteEventHandler } from "./server/ecosystem-v2-event-ingress.mjs";\n';
const V2_HEADER="// Ecosystem v2: OFF by default. A dedicated signing secret is required.";
const AUTH_SEAM='app.use("/api", requireAuth);';

function shaBlob(content){
 const bytes=Buffer.from(content);
 return createHash("sha1").update(`blob ${bytes.length}\0`).update(bytes).digest("hex");
}
test("V2 Hub addition preserves every byte of the accepted core server",()=>{
 let current=readFileSync(new URL("../server.ts", import.meta.url),"utf8");
 assert.equal(current.split(V2_IMPORTS).length,2,"Exactly one V2 import addition");
 current=current.replace(V2_IMPORTS,"");
 const begin=current.indexOf(V2_HEADER),end=current.indexOf(AUTH_SEAM,begin);
 assert.ok(begin>=0&&end>begin,"Only the expected V2 route block was added");
 assert.equal(current.indexOf(V2_HEADER,begin+1),-1,"No duplicate V2 route block");
 const block=current.slice(begin,end);
 for(const marker of [
   'V79_ECOSYSTEM_V2_EVENTS_ENABLED',
   'V79_TIQUET_EVENT_SECRET',
   'V79_WEBSITE_EVENT_SECRET',
   'createTiquetEventHandler',
   'createWebsiteEventHandler',
   'requireAuth',
   'getStore: () => store',
 ])assert.ok(block.includes(marker),"Missing V2 guard: "+marker);
 assert.ok(block.includes('app.post("/api/platform/events"'),
   "Only signed service identities may reach event intake");
 assert.ok(block.includes('app.get("/api/ecosystem/v2/events"'),
   "Event receipts route must stay separately authenticated");
 current=current.slice(0,begin)+current.slice(end);
 assert.equal(shaBlob(current),ACCEPTED_SERVER_BLOB,
   "Changes outside the reviewed V2 additions are prohibited");
});
