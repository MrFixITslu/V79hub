import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const yaml=readFileSync(".github/workflows/v79-01-ephemeral-staging.yml","utf8");
const compose=readFileSync("staging/gha-compose.yml","utf8");
const seed=readFileSync("staging/gha-seed.mjs","utf8");

test("ephemeral staging uses GitHub-hosted runner and explicitly read-only repository access",()=>{
  assert.match(yaml,/runs-on: ubuntu-24\.04/g);
  assert.match(yaml,/permissions:\s*\n\s+contents: read/);
  assert.match(yaml,/pull_request:/);
  assert.match(yaml,/if: github\.event_name == 'pull_request'/);
  assert.doesNotMatch(yaml,/^\s*environment:\s*production|DEPLOY_SSH_KEY|TAILSCALE_AUTHKEY|ssh .*deploy/im);
});
test("all application builds are on separate matrix runners, with five explicit refs",()=>{
  for(const name of ["hub","pos","ffpro","tiquet","marketing"]){
    assert.match(yaml,new RegExp("service: "+name+"\\n"));
    assert.match(yaml,new RegExp("ephemeral-image-"+name+"|ephemeral-image-\\$\\{\\{ matrix.service \\}\\}"));
  }
  assert.match(yaml,/matrix:\s*\n\s+include:/);
  assert.match(yaml,/persist-credentials: false/);
  assert.match(yaml,/retention-days: 1/);
  assert.match(yaml,/needs: build/);
});
test("no staging application publishes ports or connects to external network",()=>{
  assert.match(compose,/internal: true/);
  assert.doesNotMatch(compose,/^\s+ports:/m);
  assert.doesNotMatch(compose,/^\s+external: true/m);
  assert.doesNotMatch(compose,/network_mode: host|privileged: true/);
  for(const name of ["v79-hub","pos","ffpro","tiquet","marketing"]){
    assert.match(compose,new RegExp("^  "+name+":","m"));
  }
});
test("Hub mail and reminder activation are disabled, no real customer snapshot is loaded",()=>{
  assert.match(compose,/RESEND_API_KEY: ""/);
  assert.match(compose,/V79_TRIAL_REMINDERS_ENABLED: "0"/);
  assert.match(compose,/V79_TRIAL_REMINDERS_WORKER_LEADER: "0"/);
  assert.match(compose,/STAGE_CUSTOMER_PASSWORD/);
  assert.doesNotMatch(compose,/\/opt\/v79|\.\/backups|ServerBackups|V79_BILLING_PROVIDER: live/);
  assert.match(seed,/example\.invalid/);
  assert.match(seed,/hub-db/);
  assert.match(seed,/V79_EPHEMERAL_CI/);
});
test("CI always removes volumes and never invokes production deploy workflows",()=>{
  assert.match(yaml,/if: always\(\)/);
  assert.match(yaml,/down --volumes --remove-orphans/);
  assert.doesNotMatch(yaml,/docker push|ghcr\.io|actions\/deploy|workflow_call/);
});

test("one-time synthetic seed and DB migrations cannot run twice during startup",()=>{
  assert.match(yaml,/stage run --rm hub-seed/);
  assert.match(yaml,/stage run --rm pos-migrate/);
  assert.match(yaml,/stage up --no-deps -d v79-hub pos ffpro tiquet marketing/);
});

test("synthetic Hub fixture includes an internal platform owner before customers",()=>{
  assert.match(seed,/synthetic-v79-internal/);
  assert.match(seed,/synthetic-founder/);
  assert.match(seed,/role:"owner",status:"active"/);
  assert.match(compose,/V79_POS_ORG_ID: synthetic-v79-internal/);
  assert.match(compose,/STAGE_ADMIN_PASSWORD/);
});

test("FFPRO test encryption key uses distinct 32-byte base64 material",()=>{
  assert.match(yaml,/STAGE_FFPRO_ENCRYPTION_KEY/);
  assert.match(yaml,/base64\.b64encode\(secrets\.token_bytes\(32\)\)/);
  assert.match(compose,/DATA_ENCRYPTION_KEY: "\$\{STAGE_FFPRO_ENCRYPTION_KEY/);
});

test("staging product entitlement identities use the Hub's scoped hash contract",()=>{
  const smoke=readFileSync("staging/gha-smoke.mjs","utf8");
  assert.match(smoke,/createHash\("sha256"\)\.update\(org\+":"\+user\)/);
  assert.doesNotMatch(smoke,/if\(product!=="pos"\)return user/);
});

test("staging login uses supported owner role and real auth endpoints",()=>{
  assert.match(seed,/role:"admin", permissions:/);
  assert.doesNotMatch(seed,/role:"user"/);
  const smoke=readFileSync("staging/gha-smoke.mjs","utf8");
  assert.match(smoke,/\/api\/auth\/me/);
  assert.match(smoke,/\/api\/admin\/customers/);
  assert.doesNotMatch(smoke,/\/api\/platform\/dashboard/);
  assert.match(smoke,/anonymous.status,401/);
});
