import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {fileURLToPath} from "node:url";
import path from "node:path";

const dir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(dir,"..");
const server=fs.readFileSync(path.join(root,"server.ts"),"utf8");
const routes=fs.readFileSync(path.join(root,"server/sentinel-qa-routes.mjs"),"utf8");
const fence=fs.readFileSync(path.join(root,"server/sentinel-write-fence.mjs"),"utf8");

test("Sentinel endpoints cannot move before Hub login and platform operator authentication",()=>{
 const fenceIndex=server.indexOf("app.use(sentinelWriteFence.middleware)");
 const authIndex=server.indexOf('app.use("/api", requireAuth)');
 const sentinelIndex=server.indexOf("registerSentinelQaRoutes(app,");
 assert(fenceIndex>0,"Expected top-level write fence registration");
 assert(authIndex>fenceIndex,"Global write fence must be registered before protected routes");
 assert(sentinelIndex>authIndex,"Sentinel endpoints must be registered AFTER requireAuth");
 assert.match(server,/function requirePlatformOperator\(/);
 assert.match(server,/function isPlatformOperatorIdentity\(/);
 assert.match(server,/user\.id === posIdentity\.ownerUserId/);
 assert.match(server,/membership\?\.role === "owner"/);
});
test("Sentinel creation and deletion always require isolated feature flags",()=>{
 assert.match(routes,/V79_SENTINEL_QA_CREATE_ENABLED/);
 assert.match(routes,/V79_SENTINEL_QA_CLEANUP_ENABLED/);
 assert.match(routes,/function registerSentinelQaRoutes|export function registerSentinelQaRoutes/);
 assert.match(routes,/requirePlatformOperator/);
 assert.match(routes,/sameOriginMutation/);
 assert.match(routes,/beginExclusive/);
 assert.match(fence,/activeHttpWrites\.size !== 1/);
 assert.match(fence,/activeStoreWrites !== 0/);
});
test("Sentinel has no generic delete endpoint and no client-supplied user identities",()=>{
 assert.doesNotMatch(routes,/app\.delete\(/);
 assert.match(routes,/req\.body\?\.appIds !== undefined/);
 assert.match(routes,/req\.body\?\.userIds !== undefined/);
 assert.match(routes,/crypto\.randomUUID\(/);
});
