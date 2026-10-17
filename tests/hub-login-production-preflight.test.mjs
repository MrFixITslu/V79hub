import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const s=readFileSync(new URL("../scripts/hub-login-production-preflight.py",import.meta.url),"utf8");

test("login-only server inspection is intentionally read-only",()=>{
  assert.match(s,/NO_GO_PENDING_INDEPENDENT_RECOVERY_AND_IMAGE_EVIDENCE/);
  assert.match(s,/layered_g3_compose_order_and_files/);
  assert.match(s,/docker", "inspect"/);
  for(const banned of ["docker compose up", "docker rm", "docker restart", "docker build", "docker pull", "os.system(", "subprocess.Popen("]){
    assert.ok(!s.includes(banned), "unexpected destructive/side effect primitive: "+banned);
  }
});
test("preflight never emits env, binds, secret or volumes sources",()=>{
  assert.match(s,/mount_destinations/);
  assert.ok(!s.includes('meta.get("Config").get("Env")'));
  assert.match(s,/production_deployed_here": False/);
});

test("network gate requires exact Compose-scoped Hub and database network, never loosens safety",()=>{
  assert.match(s,/v79-hub_hub_data_network/);
  assert.match(s,/expected_internal_network in hub\.get\("network_names"/);
  assert.match(s,/expected_internal_network in db\.get\("network_names"/);
  assert.match(s,/"proxy_network" not in db\.get\("network_names"/);
});
