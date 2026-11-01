import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";

const BASELINE="2e5f872914bb85f98651ce00a4a90b1880e44076";
const HUB_IMAGE_SOURCE="24813fbd89377bdac4b45e3d0d2b5291698b3dd1";
const AGENT_IMAGE_SOURCE="674d210bd4bdb7061add04250271025403220736";
const EXPECTED=new Set([
 ".github/workflows/hub-isolated-browser-preview.yml",
 ".github/workflows/workforce-skill-manager-browser.yml",
 ".github/workflows/workforce-skill-manager-isolated.yml",
 ".github/workflows/workforce-skill-paired-images.yml",
 ".github/workflows/workforce-skill-production-baseline.yml",
 "agent-service/Dockerfile",
 "agent-service/src/index.ts",
 "agent-service/src/managed-skills.ts",
 "agent-service/src/skill-advisory.ts",
 "agent-service/tests/image-runtime-skill-pins.mjs",
 "agent-service/tests/managed-skills.test.ts",
 "agent-service/tests/skill-advisory.test.ts",
 "docs/workforce-skill-manager-20261101.md",
 "scripts/hub-isolated-browser-preview.mjs",
 "scripts/skill-manager-browser-qa.mjs",
 "scripts/skill-manager-prod-baseline-attestation.mjs",
 "server.ts",
 "server/workforce-builtins.mjs",
 "server/workforce-skill-registry.mjs",
 "server/workforce-skill-routes.mjs",
 "src/components/OwnerAssistant.tsx",
 "src/components/WorkforceSkillManager.tsx",
 "tests/workforce-builtins.test.mjs",
 "tests/workforce-skill-registry.test.mjs",
 "tests/workforce-skill-routes.test.mjs",
]);
function git(...args){return execFileSync("git",args,{encoding:"utf8"}).trim();}
const ref="refs/remotes/origin/release/v79-hub-prod-baseline-20261101";
assert.equal(git("rev-parse",ref),BASELINE,"Production reference branch cannot drift");
const changed=git("diff","--name-only",BASELINE,"HEAD").split("\n").filter(Boolean);
assert.deepEqual(new Set(changed),EXPECTED,"Only reviewed Skill Manager files may differ from LIVE production");
git("diff","--check",BASELINE,"HEAD");
const protectedLegacy=[
 "tests/r18-reconciled-candidate.test.mjs",
 "tests/vision79-admin-owner.test.mjs",
 ".github/workflows/r18-reconciled-candidate.yml",
 ".github/workflows/vision79-visual-release.yml",
 ".github/workflows/v79-ci-cd.yml",
 "src/components/Login.tsx",
 "src/App.tsx",
 "src/components/PlatformAdminOverview.tsx",
 "src/components/OwnerToday.tsx",
 "src/components/AgentApprovalInbox.tsx",
 "src/lib/hubNavigation.ts",
 "src/lib/appLaunch.ts",
];
for(const file of protectedLegacy){
 const old=execFileSync("git",["show",BASELINE+":"+file]);
 const now=readFileSync(file);
 assert.equal(createHash("sha256").update(now).digest("hex"),
              createHash("sha256").update(old).digest("hex"),
              "Legacy security or dashboard contract changed: "+file);
}
const hubRuntime=git("diff","--name-only",HUB_IMAGE_SOURCE,"HEAD","--","server.ts","server","src","Dockerfile","package.json","package-lock.json");
assert.equal(hubRuntime,"","Hub runtime differs from staged tested image revision");
const agentRuntime=git("diff","--name-only",AGENT_IMAGE_SOURCE,"HEAD","--","agent-service/src","agent-service/Dockerfile","agent-service/workforce","agent-service/package.json","agent-service/package-lock.json");
assert.equal(agentRuntime,"","Agent runtime differs from staged final image revision");
console.log("V79_SKILL_MANAGER_PROD_BASELINE_ATTESTATION=PASS");
console.log("BASELINE_LIVE_SHA="+BASELINE);
console.log("ALLOWLISTED_CHANGED_FILES="+changed.length);
console.log("LEGACY_CONTRACT_FILES_UNCHANGED="+protectedLegacy.length);
console.log("HUB_AND_AGENT_CODE_MATCH_STAGED_IMAGE_REVISIONS=PASS");
console.log("BUILTIN_CATALOG_ROUTING_AND_TESTS_WHITELISTED=PASS");
console.log("HISTORICAL_SOURCE_PINS_NOT_DISABLED_OR_REWRITTEN=PASS");
console.log("RELEASE_SCOPE_ONLY_NO_DEPLOY=YES");
