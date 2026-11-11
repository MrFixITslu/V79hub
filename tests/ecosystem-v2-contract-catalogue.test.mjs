import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const catalog=JSON.parse(readFileSync(new URL("../contracts/ecosystem-v2-events-v1.json",import.meta.url),"utf8"));
const ingress=readFileSync(new URL("../server/ecosystem-v2-event-ingress.mjs",import.meta.url),"utf8");

test("canonical events always preserve existing tested event names",()=>{
 assert.equal(catalog.schemaVersion,1);
 const names=new Set(catalog.events.map(e=>e.type));
 assert.equal(names.size,catalog.events.length);
 for(const s of ["lead.created","job.created","customer.created","job.status_changed",
  "job.paid","payment.recorded","customer.feedback_submitted","job.scope_acknowledged"])
   assert.ok(names.has(s),"Missing existing event "+s);
 assert.equal(names.has("job.signed"),false);
 assert.equal(names.has("lead.signed"),false);
});
test("ingress allows declared Tiquet versions and limited payloads",()=>{
 for(const event of catalog.events){
  assert.ok(["code_ci_only","isolated_staging_passed"].includes(event.status));
  assert.ok(["tiquet","website"].includes(event.source));
  assert.ok(Array.isArray(event.payload));
  if(event.source==="tiquet")assert.ok(ingress.includes('"' + event.type + '": ['));
 }
 assert.match(catalog.deliveryGuarantee,/at-least-once/);
 assert.match(catalog.security.payload,/no PII/);
});
test("no production claim or fictional payment settlement",()=>{
 assert.equal(catalog.deploymentStatus,"unverified");
 const paid=catalog.events.find(x=>x.type==="job.paid");
 assert.match(paid.notes,/Not a verified financial settlement/);
 assert.equal(catalog.ordering,"not_guaranteed_across_services");
});
